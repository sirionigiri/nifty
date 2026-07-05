"""
AMFI Fund Performance Scraper - Monthly End
- Scrapes last valid trading day of each month (newest → oldest)
- Backtracks up to 15 days if month-end is weekend/holiday
- Builds daily CSV + Parquet with forward-filled values for all calendar days
- Long format: one row per (date, scheme)

    pip install requests pandas pyarrow tqdm
    python amfi_scraper.py
"""

import requests
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import json
import time
import random
import sys
import logging
from datetime import date, timedelta
from calendar import monthrange
from pathlib import Path
from typing import Optional
from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────

START_DATE = date(2016, 1, 1)
END_DATE   = date(2026, 7, 2)

OUTPUT_CSV          = Path("amfi_fund_performance_daily_.csv")
OUTPUT_PARQUET      = Path("amfi_fund_performance_daily_.parquet")
RAW_CSV             = Path("amfi_raw_monthend_.csv")       # scraped month-end rows only
CHECKPOINT          = Path("amfi_checkpoint_monthly_.json")
ERROR_LOG           = Path("amfi_checkpoint_monthly_.jsonl")

API_URL     = "https://www.amfiindia.com/gateway/pollingsebi/api/amfi/fundperformance"
SESSION_URL = "https://www.amfiindia.com/polling/amfi/fund-performance"

COMBOS = [
    (1, 1,  1),  # Equity - Large Cap
    (1, 1,  2),  # Equity - Large & Mid Cap
    (1, 1,  3),  # Equity - Flexicap
    (1, 1,  4),  # Equity - Multi Cap
    (1, 1,  5),  # Equity - Mid Cap
    (1, 1,  6),  # Equity - Small Cap
    (1, 1,  7),  # Equity - Value
    (1, 1,  8),  # Equity - ELSS
    (1, 1,  9),  # Equity - Contra
    (1, 1, 10),  # Equity - Dividend Yield
    (1, 1, 11),  # Equity - Focused
    (1, 1, 12),  # Equity - Quant/Passive
    (1, 2, 13),  # Debt - Long Duration
    (1, 2, 14),  # Debt - Income
    (1, 2, 15),  # Debt - Short Term
    (1, 2, 16),  # Debt - Medium Term
    (1, 2, 17),  # Debt - Money Market
    (1, 2, 18),  # Debt - Low Duration
    (1, 2, 19),  # Debt - Ultra Short Duration
    (1, 2, 20),  # Debt - Liquid
    (1, 2, 21),  # Debt - Overnight
    (1, 2, 22),  # Debt - Dynamic Bond
    (1, 2, 23),  # Debt - Corporate Bond
    (1, 2, 24),  # Debt - Credit Risk
    (1, 2, 25),  # Debt - Banking & PSU
    (1, 2, 26),  # Debt - Floater
    # (1, 2, 27),  # Debt - unknown, try anyway
    (1, 2, 28),  # Debt - Gilt
    (1, 2, 29),  # Debt - Gilt 10yr Constant Duration
    (1, 3, 30),  # Hybrid - Aggressive Hybrid
    (1, 3, 31),  # Hybrid - Conservative Hybrid
    (1, 3, 32),  # Hybrid - Equity Savings
    (1, 3, 33),  # Hybrid - Arbitrage
    (1, 3, 34),  # Hybrid - Multi Asset Allocation
    (1, 3, 35),  # Hybrid - Balanced Advantage
    # (1, 3, 40),  # Hybrid - Balanced Hybrid
    (1, 4, 36),  # Solution Oriented - Children's Fund
    (1, 4, 37),  # Solution Oriented - Retirement Fund
    # (1, 4, 39),  # Solution Oriented - Other
    (1, 5, 38),  # Other - Index/Passive
    (1, 5, 39),  # Other - Gold/Silver ETF FOF
]

MAX_RETRIES      = 6
BACKOFF_BASE     = 2.0
BACKOFF_JITTER   = 1.0
RATE_LIMIT_SLEEP = 60
MIN_DELAY        = 0.2
MAX_DELAY        = 0.6
MAX_BACKTRACK    = 4   # days to backtrack from month-end

HEADERS = {
    "User-Agent":        "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
    "sec-ch-ua":         '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
    "sec-ch-ua-mobile":  "?1",
    "sec-ch-ua-platform": '"Android"',
    "sec-fetch-dest":    "empty",
    "sec-fetch-mode":    "cors",
    "sec-fetch-site":    "same-origin",
    "Accept-Encoding":   "gzip, deflate, br, zstd",
    "Accept-Language":   "en-US,en;q=0.9",
    "Referer":           SESSION_URL,
    "Origin":            "https://www.amfiindia.com",
    "Accept":            "application/json, text/plain, */*",
    "Content-Type":      "application/json",
}

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("amfi_scraper.log"),
    ],
)
log = logging.getLogger(__name__)

# ── Date helpers ──────────────────────────────────────────────────────────────

def month_end(year: int, month: int) -> date:
    """Last calendar day of the given month."""
    return date(year, month, monthrange(year, month)[1])

def all_months_reverse(start: date, end: date):
    """Yield (year, month) tuples from end month down to start month."""
    y, m = end.year, end.month
    while (y, m) >= (start.year, start.month):
        yield y, m
        m -= 1
        if m == 0:
            m = 12
            y -= 1

def all_calendar_days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)

# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_one(session: requests.Session, report_date: date, mt: int, cat: int, sub: int) -> Optional[list]:
    date_str = report_date.strftime("%d-%b-%Y")
    payload  = {"maturityType": mt, "category": cat, "subCategory": sub, "mfid": 0, "reportDate": date_str}

    for attempt in range(MAX_RETRIES):
        try:
            r = session.post(API_URL, json=payload, headers=HEADERS, timeout=30)

            if r.status_code == 429:
                tqdm.write(f"  🚦 Rate limited — sleeping {RATE_LIMIT_SLEEP}s")
                time.sleep(RATE_LIMIT_SLEEP)
                continue

            if r.status_code in (502, 503, 504):
                wait = BACKOFF_BASE ** attempt + random.uniform(0, BACKOFF_JITTER)
                tqdm.write(f"  ⚠️  Server {r.status_code}, retry {attempt+1} in {wait:.1f}s")
                time.sleep(wait)
                continue

            if r.status_code == 404:
                return None

            r.raise_for_status()

            if not r.text.strip():
                return None

            data = r.json()
            if data.get("validationStatus") != "SUCCESS":
                return None

            rows = data.get("data") or []
            if not rows:
                return None

            for row in rows:
                row["_date"]         = report_date.isoformat()
                row["_maturityType"] = mt
                row["_category"]     = cat
                row["_subCategory"]  = sub
            return rows

        except requests.exceptions.Timeout:
            wait = BACKOFF_BASE ** attempt + random.uniform(0, BACKOFF_JITTER)
            tqdm.write(f"  ⏱️  Timeout, retry {attempt+1} in {wait:.1f}s")
            time.sleep(wait)

        except requests.exceptions.ConnectionError:
            wait = BACKOFF_BASE ** attempt + random.uniform(0, BACKOFF_JITTER)
            tqdm.write(f"  🔌 Connection error, retry {attempt+1} in {wait:.1f}s")
            time.sleep(wait)

        except requests.exceptions.HTTPError as e:
            tqdm.write(f"  ❌ HTTP error: {e}")
            raise

        except json.JSONDecodeError:
            tqdm.write(f"  ⚠️  Bad JSON for {date_str} ({mt},{cat},{sub}) attempt {attempt+1}")
            time.sleep(BACKOFF_BASE ** attempt)
            if attempt == MAX_RETRIES - 1:
                return None

    tqdm.write(f"  ❌ Exhausted retries for {date_str} ({mt},{cat},{sub})")
    return None



def fetch_month(session: requests.Session, year: int, month: int) -> tuple[list, dict]:
    """
    For every AMFI combo independently, search backwards from month-end and
    choose the date having the maximum number of rows.

    If multiple dates have the same maximum row count, the latest date wins.

    Returns:
        rows, combo_dates
    """

    month_last = month_end(year, month)
    if month_last > END_DATE:
        month_last = END_DATE

    all_rows = []
    combo_dates = {}

    for (mt, cat, sub) in COMBOS:

        best_rows = None
        best_count = -1
        best_date = None

        candidate = month_last

        while (
            candidate.month == month
            and (month_last - candidate).days < MAX_BACKTRACK
        ):

            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

            try:
                rows = fetch_one(session, candidate, mt, cat, sub)
            except Exception as e:
                tqdm.write(
                    f"  ❌ Fatal {candidate} ({mt},{cat},{sub}): {e}"
                )
                rows = None

            count = len(rows) if rows else 0

            # strictly greater so the latest date wins ties
            if count > best_count:
                best_count = count
                best_rows = rows
                best_date = candidate

            candidate -= timedelta(days=1)

        if best_rows:
            all_rows.extend(best_rows)
            combo_dates[(mt, cat, sub)] = best_date
        else:
            tqdm.write(
                f"  ⚠️ No data for combo ({mt},{cat},{sub}) in {year}-{month:02d}"
            )

    return all_rows, combo_dates

# ── Checkpoint ────────────────────────────────────────────────────────────────

def load_checkpoint() -> Optional[tuple[int, int]]:
    """Returns (year, month) of last completed month, or None."""
    if CHECKPOINT.exists():
        data = json.loads(CHECKPOINT.read_text())
        ym = (data["year"], data["month"])
        log.info("📌 Checkpoint: last completed month = %d-%02d", *ym)
        return ym
    return None

def save_checkpoint(year: int, month: int):
    CHECKPOINT.write_text(json.dumps({"year": year, "month": month}))

# ── Raw CSV writer (month-end rows only) ──────────────────────────────────────

class RawCsvWriter:
    def __init__(self, path):
        self.path    = path
        self._header = path.exists() and path.stat().st_size > 0

    def write_batch(self, rows):
        if not rows: return
        pd.DataFrame(rows).to_csv(self.path, mode="a", index=False, header=not self._header)
        self._header = True

# ── Phase 2: build daily output with forward fill ─────────────────────────────

def build_daily_output():
    log.info("📅 Building daily output with forward fill …")

    if not RAW_CSV.exists():
        log.error("Raw CSV not found — run scraping phase first.")
        return

    raw = pd.read_csv(RAW_CSV)
    raw["_date"] = pd.to_datetime(raw["_date"])

    # All calendar days
    all_days = pd.DataFrame(
        {"date": pd.date_range(start=START_DATE, end=END_DATE, freq="D")}
    )

    # All unique schemes across entire dataset
    all_schemes = raw[["schemeName", "_maturityType", "_category", "_subCategory"]].drop_duplicates()

    # Cross join: every scheme × every calendar day
    all_days["_key"] = 1
    all_schemes["_key"] = 1
    full = all_days.merge(all_schemes, on="_key").drop(columns="_key")
    full = full.rename(columns={"date": "_date"})

    # Merge in scraped values on (date, schemeName)
    raw_renamed = raw.rename(columns={"_date": "_date"})
    full = full.merge(raw_renamed, on=["_date", "schemeName", "_maturityType", "_category", "_subCategory"], how="left")

    # Sort ascending by scheme then date, then forward fill
    value_cols = [c for c in full.columns if c not in ["_date", "schemeName", "_maturityType", "_category", "_subCategory"]]
    full = full.sort_values(["schemeName", "_maturityType", "_category", "_subCategory", "_date"])
    full[value_cols] = full.groupby(
        ["schemeName", "_maturityType", "_category", "_subCategory"]
    )[value_cols].ffill()

    # Save
    log.info("💾 Saving daily CSV …")
    full.to_csv(OUTPUT_CSV, index=False)

    log.info("💾 Saving daily Parquet …")
    table = pa.Table.from_pandas(full, preserve_index=False)
    pq.write_table(table, OUTPUT_PARQUET, compression="snappy")

    log.info("✅ Daily output: %s rows | %s schemes | %s → %s",
             f"{len(full):,}", f"{full['schemeName'].nunique():,}",
             full["_date"].min().date(), full["_date"].max().date())

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # ── Phase 1: scrape month-ends ────────────────────────────────────────────
    checkpoint = load_checkpoint()

    # Build list of (year, month) to scrape, newest first
    months = list(all_months_reverse(START_DATE, END_DATE))

    # Skip already-done months
    if checkpoint:
        cy, cm = checkpoint
        months = [(y, m) for (y, m) in months if (y, m) < (cy, cm)]

    if months:
        log.info("Scraping %d months (%d combos/month) …", len(months), len(COMBOS))
        session    = requests.Session()
        raw_writer = RawCsvWriter(RAW_CSV)
        error_fh   = open(ERROR_LOG, "a")
        total_rows = 0

        month_bar = tqdm(months, desc="months", unit="month")
        try:
            for (year, month) in month_bar:
                month_bar.set_postfix(month=f"{year}-{month:02d}", rows=total_rows)

                rows, combo_dates = fetch_month(session, year, month)

                if rows:
                    raw_writer.write_batch(rows)
                    total_rows += len(rows)

                    unique_dates = sorted(set(combo_dates.values()), reverse=True)

                    if len(unique_dates) == 1:
                        date_info = unique_dates[0]
                    else:
                        from collections import Counter

                        c = Counter(combo_dates.values())
                        summary = ", ".join(
                            f"{d}: {c[d]} combos"
                            for d in sorted(c.keys(), reverse=True)
                        )
                        date_info = f"{len(unique_dates)} dates ({summary})"

                    tqdm.write(
                        f"  ✅ {year}-{month:02d} → {date_info} → "
                        f"{len(rows):,} rows (total: {total_rows:,})"
                    )
                else:
                    tqdm.write(f"  ─  {year}-{month:02d} → no data found within {MAX_BACKTRACK} days")
                    error_fh.write(json.dumps({"year": year, "month": month, "error": "no data"}) + "\n")
                    error_fh.flush()

                save_checkpoint(year, month)

        except KeyboardInterrupt:
            tqdm.write("\n⛔ Interrupted — progress saved.")
        finally:
            error_fh.close()
            month_bar.close()
            log.info("Scraping done. %d total raw rows saved to %s", total_rows, RAW_CSV)
    else:
        log.info("All months already scraped — skipping to daily build.")

    # ── Phase 2: build daily output ───────────────────────────────────────────
    build_daily_output()


if __name__ == "__main__":
    main()