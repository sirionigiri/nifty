"""
AMFI Fund Performance Bulk Scraper
Scrapes daily data from Jan 2006 to today across all maturityType/category/subCategory combos.
Handles rate limiting, retries, session refresh, checkpointing, and saves to CSV + Parquet.
"""

import requests
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import json
import time
import logging
import random
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────

START_DATE = date(2006, 1, 1)
END_DATE   = date.today()

OUTPUT_CSV     = Path("amfi_fund_performance.csv")
OUTPUT_PARQUET = Path("amfi_fund_performance.parquet")
CHECKPOINT     = Path("amfi_checkpoint.json")   # tracks last completed date
ERROR_LOG      = Path("amfi_errors.jsonl")       # skipped dates go here

BASE_URL      = "https://www.amfiindia.com"
SESSION_URL   = f"{BASE_URL}/polling/amfi/fund-performance"
API_URL       = f"{BASE_URL}/gateway/pollingsebi/api/amfi/fundperformance"

# All known dimension combos — expand if AMFI adds more
MATURITY_TYPES   = [1, 2, 3]      # 1=Open, 2=Close, 3=Interval  (adjust as needed)
CATEGORIES       = [1, 2, 3, 4, 5]
SUB_CATEGORIES   = [1, 2, 3, 4, 5]

# Retry / rate-limit knobs
MAX_RETRIES          = 6
BACKOFF_BASE         = 2.0          # seconds; doubles each retry
BACKOFF_JITTER       = 1.0          # random extra seconds
RATE_LIMIT_SLEEP     = 60           # seconds to sleep when 429 is received
SESSION_REFRESH_EVERY = 50          # re-establish session every N successful requests

# Politeness: pause between requests
MIN_DELAY = 0.3  # seconds
MAX_DELAY = 0.8

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("amfi_scraper.log"),
    ],
)
log = logging.getLogger(__name__)

# ── Session management ─────────────────────────────────────────────────────────

HEADERS_BASE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": SESSION_URL,
    "Origin":  BASE_URL,
}


def make_session() -> requests.Session:
    """Create a fresh requests.Session with cookies established."""
    s = requests.Session()
    s.headers.update(HEADERS_BASE)
    for attempt in range(4):
        try:
            r = s.get(SESSION_URL, timeout=20)
            r.raise_for_status()
            log.debug("Session established (cookies: %s)", dict(s.cookies))
            return s
        except Exception as e:
            wait = BACKOFF_BASE ** attempt + random.uniform(0, BACKOFF_JITTER)
            log.warning("Session init failed (%s), retry %d in %.1fs", e, attempt + 1, wait)
            time.sleep(wait)
    raise RuntimeError("Could not establish AMFI session after 4 attempts")


# ── Core fetch ────────────────────────────────────────────────────────────────

def fetch_one(
    session: requests.Session,
    report_date: date,
    maturity_type: int,
    category: int,
    sub_category: int,
) -> Optional[list[dict]]:
    """
    Fetch one (date, maturity_type, category, sub_category) combo.
    Returns list of row dicts, or None if the combo has no data (empty / 404-style).
    Raises on unrecoverable errors.
    """
    date_str = report_date.strftime("%d-%b-%Y")  # e.g. "23-Jun-2026"
    payload = {
        "maturityType": maturity_type,
        "category":     category,
        "subCategory":  sub_category,
        "mfid":         0,
        "reportDate":   date_str,
    }
    api_headers = {
        **HEADERS_BASE,
        "Accept":       "application/json, text/plain, */*",
        "Content-Type": "application/json",
    }

    for attempt in range(MAX_RETRIES):
        try:
            r = session.post(API_URL, json=payload, headers=api_headers, timeout=30)

            if r.status_code == 429:
                log.warning("Rate limited (429). Sleeping %ds …", RATE_LIMIT_SLEEP)
                time.sleep(RATE_LIMIT_SLEEP)
                continue

            if r.status_code in (502, 503, 504):
                wait = BACKOFF_BASE ** attempt + random.uniform(0, BACKOFF_JITTER)
                log.warning("Server error %d, retry %d in %.1fs", r.status_code, attempt + 1, wait)
                time.sleep(wait)
                continue

            if r.status_code == 404:
                return None  # combo genuinely doesn't exist for this date

            r.raise_for_status()

            text = r.text.strip()
            if not text:
                return None  # API returned empty body → no data for this combo

            data = r.json()

            rows = data.get("data") or data.get("Data") or data.get("result") or []
            if isinstance(rows, list):
                # Tag each row with its dimensions so we know where it came from
                for row in rows:
                    row["_date"]          = report_date.isoformat()
                    row["_maturityType"]  = maturity_type
                    row["_category"]      = category
                    row["_subCategory"]   = sub_category
                return rows if rows else None

            return None  # unexpected shape

        except requests.exceptions.Timeout:
            wait = BACKOFF_BASE ** attempt + random.uniform(0, BACKOFF_JITTER)
            log.warning("Timeout, retry %d in %.1fs", attempt + 1, wait)
            time.sleep(wait)

        except requests.exceptions.ConnectionError as e:
            wait = BACKOFF_BASE ** attempt + random.uniform(0, BACKOFF_JITTER)
            log.warning("Connection error (%s), retry %d in %.1fs", e, attempt + 1, wait)
            time.sleep(wait)

        except requests.exceptions.HTTPError as e:
            log.error("HTTP error (non-retryable): %s", e)
            raise

        except json.JSONDecodeError:
            log.warning("JSON decode error for %s mt=%d cat=%d sub=%d (attempt %d)",
                        date_str, maturity_type, category, sub_category, attempt + 1)
            if attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF_BASE ** attempt)
            else:
                return None  # give up silently, log it

    log.error("Exhausted retries for %s mt=%d cat=%d sub=%d", date_str, maturity_type, category, sub_category)
    return None


# ── Checkpoint ────────────────────────────────────────────────────────────────

def load_checkpoint() -> Optional[date]:
    if CHECKPOINT.exists():
        with open(CHECKPOINT) as f:
            data = json.load(f)
        d = date.fromisoformat(data["last_completed_date"])
        log.info("Resuming from checkpoint: last completed date = %s", d)
        return d
    return None


def save_checkpoint(d: date):
    with open(CHECKPOINT, "w") as f:
        json.dump({"last_completed_date": d.isoformat()}, f)


# ── Parquet writer (streaming append) ─────────────────────────────────────────

class ParquetWriter:
    """Appends batches of rows to a Parquet file without holding everything in RAM."""

    def __init__(self, path: Path):
        self.path = path
        self._writer: Optional[pq.ParquetWriter] = None
        self._schema: Optional[pa.Schema] = None

    def write_batch(self, rows: list[dict]):
        if not rows:
            return
        df = pd.DataFrame(rows)
        table = pa.Table.from_pandas(df, preserve_index=False)
        if self._writer is None:
            self._schema = table.schema
            self._writer = pq.ParquetWriter(self.path, self._schema, compression="snappy")
        else:
            # Cast to original schema to keep columns consistent
            table = table.cast(self._schema)
        self._writer.write_table(table)

    def close(self):
        if self._writer:
            self._writer.close()
            self._writer = None


# ── CSV writer (streaming append) ─────────────────────────────────────────────

class CsvWriter:
    def __init__(self, path: Path):
        self.path = path
        self._header_written = path.exists() and path.stat().st_size > 0

    def write_batch(self, rows: list[dict]):
        if not rows:
            return
        df = pd.DataFrame(rows)
        df.to_csv(
            self.path,
            mode="a",
            index=False,
            header=not self._header_written,
        )
        self._header_written = True


# ── Date helpers ──────────────────────────────────────────────────────────────

def date_range(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("AMFI bulk scraper starting: %s → %s", START_DATE, END_DATE)

    # Determine start date (skip already-done dates)
    checkpoint = load_checkpoint()
    if checkpoint:
        actual_start = checkpoint + timedelta(days=1)
        log.info("Skipping to %s (checkpoint found)", actual_start)
    else:
        actual_start = START_DATE

    if actual_start > END_DATE:
        log.info("Nothing to do — all dates already scraped.")
        return

    parquet_writer = ParquetWriter(OUTPUT_PARQUET)
    csv_writer     = CsvWriter(OUTPUT_CSV)

    session       = make_session()
    request_count = 0
    error_log_fh  = open(ERROR_LOG, "a")

    total_dates = (END_DATE - actual_start).days + 1
    dates_done  = 0

    try:
        for current_date in date_range(actual_start, END_DATE):
            day_rows = []
            date_had_error = False

            for mt in MATURITY_TYPES:
                for cat in CATEGORIES:
                    for sub in SUB_CATEGORIES:
                        # Polite delay
                        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

                        # Periodic session refresh
                        if request_count > 0 and request_count % SESSION_REFRESH_EVERY == 0:
                            log.info("Refreshing session after %d requests …", request_count)
                            try:
                                session = make_session()
                            except Exception as e:
                                log.error("Session refresh failed: %s", e)

                        try:
                            rows = fetch_one(session, current_date, mt, cat, sub)
                        except Exception as e:
                            log.error("Unrecoverable error for %s mt=%d cat=%d sub=%d: %s",
                                      current_date, mt, cat, sub, e)
                            error_log_fh.write(json.dumps({
                                "date": current_date.isoformat(),
                                "maturityType": mt, "category": cat, "subCategory": sub,
                                "error": str(e)
                            }) + "\n")
                            error_log_fh.flush()
                            date_had_error = True
                            rows = None

                        if rows:
                            day_rows.extend(rows)

                        request_count += 1

            # Write entire day's rows to disk
            if day_rows:
                parquet_writer.write_batch(day_rows)
                csv_writer.write_batch(day_rows)
                log.info("[%d/%d] %s → %d rows saved",
                         dates_done + 1, total_dates, current_date, len(day_rows))
            else:
                log.info("[%d/%d] %s → no data (weekend/holiday or empty combos)",
                         dates_done + 1, total_dates, current_date)

            # Save checkpoint only if no errors for this date
            if not date_had_error:
                save_checkpoint(current_date)

            dates_done += 1

    except KeyboardInterrupt:
        log.info("Interrupted by user. Progress saved up to last checkpoint.")

    finally:
        parquet_writer.close()
        error_log_fh.close()
        log.info("Done. %d dates processed.", dates_done)
        log.info("Output → %s  |  %s", OUTPUT_CSV, OUTPUT_PARQUET)
        if ERROR_LOG.exists() and ERROR_LOG.stat().st_size > 0:
            log.info("Some errors were logged to %s — re-run to retry those dates.", ERROR_LOG)


if __name__ == "__main__":
    main()