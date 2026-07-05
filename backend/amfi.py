"""
AMFI Fund Performance Bulk Scraper
Scrapes newest → oldest, saves to CSV + Parquet with checkpointing.

Usage:
    pip install requests pandas pyarrow tqdm
    python amfi_scraper.py

Tune COMBOS below once you know which (maturityType, category, subCategory)
combos actually return data for your use case.
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
from pathlib import Path
from typing import Optional
from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────

START_DATE = date(2026, 1, 1)
END_DATE   = date(2026, 7, 2)

OUTPUT_CSV     = Path("amfi_fund_performance.csv")
# OUTPUT_PARQUET = Path("amfi_fund_performance.parquet")
CHECKPOINT     = Path("amfi_checkpoint.json")
ERROR_LOG      = Path("amfi_errors.jsonl")

API_URL     = "https://www.amfiindia.com/gateway/pollingsebi/api/amfi/fundperformance"
SESSION_URL = "https://www.amfiindia.com/polling/amfi/fund-performance"

# ── TUNE THIS: only the combos that actually return data ─────────────────────
# From your network tab: (1,1,1) = Open-ended / Equity / Large Cap etc.
# Add more tuples as you discover which ones have data.
# Format: (maturityType, category, subCategory)
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
    "Referer":      SESSION_URL,
    "Origin":       "https://www.amfiindia.com",
    "Accept":       "application/json, text/plain, */*",
    "Content-Type": "application/json",
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

# ── Checkpoint ────────────────────────────────────────────────────────────────

def load_checkpoint() -> Optional[date]:
    if CHECKPOINT.exists():
        d = date.fromisoformat(json.loads(CHECKPOINT.read_text())["last_completed_date"])
        log.info("📌 Checkpoint: resuming before %s", d)
        return d
    return None

def save_checkpoint(d: date):
    CHECKPOINT.write_text(json.dumps({"last_completed_date": d.isoformat()}))

# ── Writers ───────────────────────────────────────────────────────────────────

class ParquetWriter:
    def __init__(self, path):
        self.path    = path
        self._writer = self._schema = None

    def write_batch(self, rows):
        if not rows: return
        table = pa.Table.from_pandas(pd.DataFrame(rows), preserve_index=False)
        if self._writer is None:
            self._schema = table.schema
            self._writer = pq.ParquetWriter(self.path, self._schema, compression="snappy")
        self._writer.write_table(table.cast(self._schema))

    def close(self):
        if self._writer:
            self._writer.close()

class CsvWriter:
    def __init__(self, path):
        self.path    = path
        self._header = path.exists() and path.stat().st_size > 0

    def write_batch(self, rows):
        if not rows: return
        pd.DataFrame(rows).to_csv(self.path, mode="a", index=False, header=not self._header)
        self._header = True

# ── Date helpers ──────────────────────────────────────────────────────────────

def date_range_reverse(start, end):
    d = end
    while d >= start:
        yield d
        d -= timedelta(days=1)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    checkpoint = load_checkpoint()
    actual_end = (checkpoint - timedelta(days=1)) if checkpoint else END_DATE

    if actual_end < START_DATE:
        log.info("Nothing to do — all dates already scraped.")
        return

    log.info("Scraping %s → %s (%d combos/day)", actual_end, START_DATE, len(COMBOS))

    session        = requests.Session()
    # parquet_writer = ParquetWriter(OUTPUT_PARQUET)
    csv_writer     = CsvWriter(OUTPUT_CSV)
    error_fh       = open(ERROR_LOG, "a")
    total_rows     = 0
    total_dates    = (actual_end - START_DATE).days + 1

    date_bar = tqdm(
        date_range_reverse(START_DATE, actual_end),
        total=total_dates,
        desc="dates",
        unit="day",
    )

    try:
        for current_date in date_bar:
            day_rows       = []
            date_had_error = False
            date_bar.set_postfix(date=str(current_date), rows=total_rows)

            for (mt, cat, sub) in COMBOS:
                time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
                try:
                    rows = fetch_one(session, current_date, mt, cat, sub)
                except Exception as e:
                    tqdm.write(f"  ❌ Fatal {current_date} ({mt},{cat},{sub}): {e}")
                    error_fh.write(json.dumps({
                        "date": current_date.isoformat(), "mt": mt, "cat": cat, "sub": sub, "error": str(e)
                    }) + "\n")
                    error_fh.flush()
                    date_had_error = True
                    rows = None

                if rows:
                    day_rows.extend(rows)

            if day_rows:
                # parquet_writer.write_batch(day_rows)
                csv_writer.write_batch(day_rows)
                total_rows += len(day_rows)
                tqdm.write(f"  ✅ {current_date} → {len(day_rows):,} rows  (total: {total_rows:,})")
            else:
                tqdm.write(f"  ─  {current_date} → no data (weekend/holiday)")

            if not date_had_error:
                save_checkpoint(current_date)

    except KeyboardInterrupt:
        tqdm.write("\n⛔ Interrupted — progress saved.")

    finally:
        # parquet_writer.close()
        error_fh.close()
        date_bar.close()
        log.info("Done. %d total rows | CSV: %s | Parquet: %s", total_rows, OUTPUT_CSV, 
                #  OUTPUT_PARQUET
                 )

if __name__ == "__main__":
    main()