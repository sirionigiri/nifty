"""
AMFI Fund Performance Scraper - Monthly End
- Scrapes last valid trading day of each month (newest → oldest)
- Backtracks up to MAX_BACKTRACK days if month-end is weekend/holiday
- Accepts a candidate day only if a strong majority of combos reported data
  (adaptive threshold — prevents one "stale" combo from locking in a bad day)
- Builds daily CSV + Parquet with forward-filled values for all calendar days,
  plus a `_days_stale` column so silently-old values stay visible/filterable
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

START_DATE = date(2006, 1, 1)
END_DATE   = date(2026, 6, 30)

OUTPUT_CSV     = Path("amfi_fund_performance_daily_v3.csv")
OUTPUT_PARQUET = Path("amfi_fund_performance_daily_v3.parquet")
RAW_CSV        = Path("amfi_raw_monthend_v3.csv")       # scraped month-end rows only
CHECKPOINT     = Path("amfi_checkpoint_v3.json")
ERROR_LOG      = Path("amfi_errors_v3.jsonl")

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
    (1, 2, 27),  # Debt - unknown, try anyway
    (1, 2, 28),  # Debt - Gilt
    (1, 2, 29),  # Debt - Gilt 10yr Constant Duration
    (1, 3, 30),  # Hybrid - Aggressive Hybrid
    (1, 3, 31),  # Hybrid - Conservative Hybrid
    (1, 3, 32),  # Hybrid - Equity Savings
    (1, 3, 33),  # Hybrid - Arbitrage
    (1, 3, 34),  # Hybrid - Multi Asset Allocation
    (1, 3, 35),  # Hybrid - Balanced Advantage
    (1, 3, 40),  # Hybrid - Balanced Hybrid
    (1, 4, 36),  # Solution Oriented - Children's Fund
    (1, 4, 37),  # Solution Oriented - Retirement Fund
    (1, 4, 39),  # Solution Oriented - Other
    (1, 5, 38),  # Other - Index/Passive
    (1, 5, 39),  # Other - Gold/Silver ETF FOF
]

MAX_RETRIES      = 6
BACKOFF_BASE     = 2.0
BACKOFF_JITTER   = 1.0
RATE_LIMIT_SLEEP = 60
MIN_DELAY        = 0.2
MAX_DELAY        = 0.6
MAX_BACKTRACK    = 15   # days to backtrack from month-end

# Acceptance threshold for "is this candidate day a real trading day":
# require at least this fraction of the combos that were active last month
# to report data. Prevents a single stale/cached combo response from
# falsely ending the backtrack on a holiday/weekend.
ACTIVE_COMBO_RATIO = 0.7
MIN_ACTIVE_COMBOS_FLOOR = 5   # never require fewer than this many, even early in history

# Forward-fill safety cap: don't carry a value forward more than this many
# days without a real observation (closed/delisted schemes shouldn't get
# fabricated "current" values indefinitely). Rows beyond this are still
# written, but flagged via `_days_stale` so you can filter/exclude them.
FFILL_HARD_CAP_DAYS = 45   # ~1.5 months; tune to taste

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


def fetch_month(
    session: requests.Session,
    year: int,
    month: int,
    min_active_combos: int,
) -> tuple[Optional[date], list, int]:
    """
    Find one shared candidate day for the whole month by backtracking from
    month-end. A day is accepted only once at least `min_active_combos`
    distinct combos report data on it — not just any single combo — so a
    stale/cached response from one category can't falsely end the search.

    Returns (accepted_date, all_rows, combos_with_data) or (None, [], 0).
    """
    candidate = month_end(year, month)
    if candidate > END_DATE:
        candidate = END_DATE

    for _ in range(MAX_BACKTRACK):
        if candidate.month != month:
            break  # backtracked into the previous month — give up

        all_rows = []
        combos_with_data = 0

        for (mt, cat, sub) in COMBOS:
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            try:
                rows = fetch_one(session, candidate, mt, cat, sub)
            except Exception as e:
                tqdm.write(f"  ❌ Fatal {candidate} ({mt},{cat},{sub}): {e}")
                rows = None
            if rows:
                all_rows.extend(rows)
                combos_with_data += 1

        if combos_with_data >= min_active_combos:
            return candidate, all_rows, combos_with_data

        tqdm.write(
            f"  ↩️  {candidate}: only {combos_with_data}/{len(COMBOS)} combos "
            f"reported (need {min_active_combos}) — backtracking"
        )
        candidate -= timedelta(days=1)

    return None, [], 0

# ── Checkpoint ────────────────────────────────────────────────────────────────

def load_checkpoint() -> Optional[dict]:
    """Returns {"year", "month", "last_good_combo_count"} or None."""
    if CHECKPOINT.exists():
        data = json.loads(CHECKPOINT.read_text())
        log.info("📌 Checkpoint: last completed month = %d-%02d (last_good_combo_count=%s)",
                  data["year"], data["month"], data.get("last_good_combo_count"))
        return data
    return None

def save_checkpoint(year: int, month: int, last_good_combo_count: int):
    CHECKPOINT.write_text(json.dumps({
        "year": year,
        "month": month,
        "last_good_combo_count": last_good_combo_count,
    }))

# ── Raw CSV writer (month-end rows only) ──────────────────────────────────────

class RawCsvWriter:
    def __init__(self, path):
        self.path    = path
        self._header = path.exists() and path.stat().st_size > 0

    def write_batch(self, rows):
        if not rows:
            return
        pd.DataFrame(rows).to_csv(self.path, mode="a", index=False, header=not self._header)
        self._header = True

# ── Phase 2: build daily output with stale-aware forward fill ─────────────────

def build_daily_output():
    log.info("📅 Building daily output with forward fill …")

    if not RAW_CSV.exists():
        log.error("Raw CSV not found — run scraping phase first.")
        return

    raw = pd.read_csv(RAW_CSV)
    raw["_date"] = pd.to_datetime(raw["_date"])
    raw = raw.drop_duplicates(
        subset=["_date", "schemeName", "_maturityType", "_category", "_subCategory"]
    )

    key_cols = ["schemeName", "_maturityType", "_category", "_subCategory"]
    value_cols = [c for c in raw.columns if c not in key_cols + ["_date"]]

    full_range = pd.date_range(START_DATE, END_DATE, freq="D")
    pieces = []

    groups = raw.groupby(key_cols)
    for keys, g in tqdm(groups, desc="schemes", unit="scheme"):
        g = g.drop_duplicates(subset="_date").set_index("_date").sort_index()

        # Reindex onto full calendar range
        g = g.reindex(full_range)

        # Track days since last real observation BEFORE filling
        has_data = g[value_cols[0]].notna() if value_cols else g.notna().any(axis=1)
        # group index of most recent real observation, forward-filled
        last_real_idx = pd.Series(g.index.where(has_data), index=g.index).ffill()
        days_stale = (g.index.to_series() - last_real_idx).dt.days
        days_stale = days_stale.fillna(-1).astype(int)  # -1 = never observed yet (before first data point)

        # Forward fill values, but only up to FFILL_HARD_CAP_DAYS
        g[value_cols] = g[value_cols].ffill(limit=FFILL_HARD_CAP_DAYS)

        g["_days_stale"] = days_stale
        g[key_cols[0]], g[key_cols[1]], g[key_cols[2]], g[key_cols[3]] = keys
        g.index.name = "_date"
        pieces.append(g.reset_index())

    full = pd.concat(pieces, ignore_index=True)

    # Drop rows that predate the scheme's first real observation entirely
    # (days_stale == -1 means "no data yet", not "stale" — usually you want
    # these dropped rather than shown as NaN rows; comment out if you want them kept)
    full = full[full["_days_stale"] != -1].reset_index(drop=True)

    log.info("💾 Saving daily CSV …")
    full.to_csv(OUTPUT_CSV, index=False)

    log.info("💾 Saving daily Parquet …")
    table = pa.Table.from_pandas(full, preserve_index=False)
    pq.write_table(table, OUTPUT_PARQUET, compression="snappy")

    n_stale_beyond_cap = (full["_days_stale"] > FFILL_HARD_CAP_DAYS).sum()
    log.info(
        "✅ Daily output: %s rows | %s schemes | %s → %s | %s rows beyond %sd stale cap (values left NaN)",
        f"{len(full):,}", f"{full['schemeName'].nunique():,}",
        full["_date"].min().date(), full["_date"].max().date(),
        f"{n_stale_beyond_cap:,}", FFILL_HARD_CAP_DAYS,
    )

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    checkpoint = load_checkpoint()

    months = list(all_months_reverse(START_DATE, END_DATE))

    last_good_combo_count = len(COMBOS)  # optimistic default; adapts downward for older history
    if checkpoint:
        cy, cm = checkpoint["year"], checkpoint["month"]
        months = [(y, m) for (y, m) in months if (y, m) < (cy, cm)]
        last_good_combo_count = checkpoint.get("last_good_combo_count", len(COMBOS))

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

                min_required = max(
                    MIN_ACTIVE_COMBOS_FLOOR,
                    int(last_good_combo_count * ACTIVE_COMBO_RATIO),
                )

                actual_date, rows, n_combos = fetch_month(session, year, month, min_required)

                if rows:
                    raw_writer.write_batch(rows)
                    total_rows += len(rows)
                    last_good_combo_count = n_combos
                    tqdm.write(
                        f"  ✅ {year}-{month:02d} → {actual_date} → {len(rows):,} rows "
                        f"across {n_combos}/{len(COMBOS)} combos (total: {total_rows:,})"
                    )
                else:
                    tqdm.write(f"  ─  {year}-{month:02d} → no acceptable day found within {MAX_BACKTRACK} days")
                    error_fh.write(json.dumps({
                        "year": year, "month": month, "error": "no data",
                        "min_required": min_required,
                    }) + "\n")
                    error_fh.flush()

                save_checkpoint(year, month, last_good_combo_count)

        except KeyboardInterrupt:
            tqdm.write("\n⛔ Interrupted — progress saved.")
        finally:
            error_fh.close()
            month_bar.close()
            log.info("Scraping done. %d total raw rows saved to %s", total_rows, RAW_CSV)
    else:
        log.info("All months already scraped — skipping to daily build.")

    build_daily_output()


if __name__ == "__main__":
    main()