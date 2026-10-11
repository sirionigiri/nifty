"""
amfi_navall_scraper.py — one-time historical NAV scrape (month-end, 2006 → today)

Source: AMFI's NAVAll history endpoint (one request returns EVERY scheme,
every AMC, every category for a single date):

    https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?frmdt=DD-Mon-YYYY

Output: a single long-format Parquet file, one row per (date, scheme_code):
    date, scheme_code, scheme_name, amc, main_type, category, plan, option,
    isin_payout_or_growth, isin_reinvest, nav

Designed to be queried directly with DuckDB, e.g.:
    duckdb.sql("SELECT * FROM 'amfi_nav_monthend.parquet' WHERE date = '2026-08-31'")

    pip install requests pandas pyarrow tqdm
    python amfi_navall_scraper.py
"""

import requests
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import re
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

# ── Config ───────────────────────────────────────────────────────────────────

START_DATE = date(2006, 1, 1)
END_DATE   = date.today()

BASE_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx"

OUTPUT_PARQUET = Path("amfi_nav_monthend.parquet")
RAW_DIR        = Path("raw_monthend")     # raw text per accepted date — handy if you ever need to re-parse
CHECKPOINT     = Path("navall_checkpoint.json")
ERROR_LOG      = Path("navall_errors.jsonl")

MAX_BACKTRACK    = 10     # trading-day search window from month-end
MAX_RETRIES      = 6
BACKOFF_BASE     = 2.0
BACKOFF_JITTER   = 1.0
RATE_LIMIT_SLEEP = 45
MIN_DELAY, MAX_DELAY = 0.5, 1.2   # politeness delay between requests

# Accept a candidate day only if it returned at least this fraction of the
# row count we last saw on a good day (adaptive — schema/coverage grows a lot
# between 2006 and today, so a fixed absolute floor doesn't work well).
ROW_COUNT_RATIO = 0.5
MIN_ROWS_FLOOR  = 200     # never require fewer rows than this, even in 2006

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/plain, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.amfiindia.com/",
    "Connection": "keep-alive",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("navall_scraper.log")],
)
log = logging.getLogger(__name__)

RAW_DIR.mkdir(exist_ok=True)

# ── Date helpers ─────────────────────────────────────────────────────────────

def month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])

def all_months_reverse(start: date, end: date):
    y, m = end.year, end.month
    while (y, m) >= (start.year, start.month):
        yield y, m
        m -= 1
        if m == 0:
            m, y = 12, y - 1

# ── Fetch ────────────────────────────────────────────────────────────────────

def fetch_navall(session: requests.Session, d: date) -> Optional[str]:
    """GET the raw NAVAll history text for one date. Returns None on failure
    or if the response is clearly not real NAV data (holiday/weekend pages
    are usually near-empty or an error/HTML page instead of the report)."""
    params = {"frmdt": d.strftime("%d-%b-%Y")}

    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(BASE_URL, params=params, headers=HEADERS, timeout=30)

            if r.status_code == 429:
                tqdm.write(f"  🚦 Rate limited — sleeping {RATE_LIMIT_SLEEP}s")
                time.sleep(RATE_LIMIT_SLEEP)
                continue

            if r.status_code in (502, 503, 504):
                wait = BACKOFF_BASE ** attempt + random.uniform(0, BACKOFF_JITTER)
                tqdm.write(f"  ⚠️  Server {r.status_code}, retry {attempt+1} in {wait:.1f}s")
                time.sleep(wait)
                continue

            r.raise_for_status()
            text = r.text

            if not text or len(text.strip()) < 50:
                return None

            # A real report is plain text starting with the CSV-ish header or a
            # "Scheme Code;" column line somewhere near the top. If AMFI serves
            # back an HTML error/holiday page instead, bail out.
            if "<html" in text[:200].lower():
                return None

            return text

        except requests.exceptions.Timeout:
            wait = BACKOFF_BASE ** attempt + random.uniform(0, BACKOFF_JITTER)
            tqdm.write(f"  ⏱️  Timeout, retry {attempt+1} in {wait:.1f}s")
            time.sleep(wait)

        except requests.exceptions.ConnectionError:
            wait = BACKOFF_BASE ** attempt + random.uniform(0, BACKOFF_JITTER)
            tqdm.write(f"  🔌 Connection error, retry {attempt+1} in {wait:.1f}s")
            time.sleep(wait)

        except requests.exceptions.HTTPError as e:
            tqdm.write(f"  ❌ HTTP error for {d}: {e}")
            time.sleep(BACKOFF_BASE ** attempt)

    tqdm.write(f"  ❌ Exhausted retries for {d}")
    return None

# ── Parse ────────────────────────────────────────────────────────────────────

CATEGORY_RE = re.compile(
    r"^(Open|Close|Interval)\s+Ended\s+Schemes\s*\(\s*(.+?)\s*\)\s*$",
    re.IGNORECASE,
)

def parse_navall(text: str, expected_date: date) -> list[dict]:
    """
    Line-by-line state machine over the AMFI NAVAll format:

        Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Date

        Open Ended Schemes ( Equity Scheme - Multi Cap Fund )      <- category header (no ';')

        Aditya Birla Sun Life Mutual Fund                          <- AMC header (no ';')
        148921;Aditya Birla Sun Life Multi-Cap Fund-Direct Growth;Direct Plan;GROWTH;INF209KB1Y49;;23.01;02-Sep-2026

    A data row is identified by its first field being numeric (the scheme code) —
    this is more reliable than counting ';' since header lines are irregular.
    """
    rows = []
    main_type = None
    category = None
    amc = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Column header line — skip
        if line.lower().startswith("scheme code"):
            continue

        m = CATEGORY_RE.match(line)
        if m:
            main_type = f"{m.group(1)} Ended Schemes"
            category = m.group(2).strip()
            continue

        first_field = line.split(";", 1)[0].strip()

        if first_field.isdigit():
            parts = [p.strip() for p in line.split(";")]
            # Pad defensively in case a field is missing
            while len(parts) < 8:
                parts.append("")
            scheme_code, nav_name, plan, option, isin_pg, isin_ri, nav_str, date_str = parts[:8]

            try:
                row_date = pd.to_datetime(date_str, format="%d-%b-%Y").date()
            except (ValueError, TypeError):
                row_date = None

            try:
                nav = float(nav_str)
            except (ValueError, TypeError):
                nav = None  # "N.A." etc.

            rows.append({
                "date": row_date,
                "scheme_code": scheme_code,
                "scheme_name": nav_name,
                "amc": amc,
                "main_type": main_type,
                "category": category,
                "plan": plan,
                "option": option,
                "isin_payout_or_growth": isin_pg,
                "isin_reinvest": isin_ri,
                "nav": nav,
            })
            continue

        # No ';' and not a category header and not a data row -> AMC name line
        if ";" not in line:
            amc = line
            continue

    # Keep only rows that actually carry the date we asked for (defends
    # against AMFI silently serving stale/cached data for a bad date).
    if rows:
        good_rows = [r for r in rows if r["date"] == expected_date]
        # If literally nothing matches the expected date, treat as invalid.
        return good_rows

    return rows

# ── Per-month: find the accepted trading day and parse it ─────────────────────

def fetch_month(session: requests.Session, year: int, month: int, min_rows: int) -> tuple[Optional[date], list[dict]]:
    candidate = month_end(year, month)
    if candidate > END_DATE:
        candidate = END_DATE

    for _ in range(MAX_BACKTRACK):
        if candidate.month != month:
            break  # backtracked into the previous month — give up on this month

        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
        text = fetch_navall(session, candidate)

        if text:
            rows = parse_navall(text, candidate)
            if len(rows) >= min_rows:
                (RAW_DIR / f"{candidate.isoformat()}.txt").write_text(text)
                return candidate, rows
            else:
                tqdm.write(f"  ↩️  {candidate}: only {len(rows)} rows (need {min_rows}) — backtracking")
        else:
            tqdm.write(f"  ↩️  {candidate}: no/invalid response — backtracking")

        candidate -= timedelta(days=1)

    return None, []

# ── Checkpoint ───────────────────────────────────────────────────────────────

def load_checkpoint() -> Optional[dict]:
    if CHECKPOINT.exists():
        data = json.loads(CHECKPOINT.read_text())
        log.info("📌 Resuming from checkpoint: last completed month = %d-%02d", data["year"], data["month"])
        return data
    return None

def save_checkpoint(year: int, month: int, last_good_row_count: int):
    CHECKPOINT.write_text(json.dumps({
        "year": year, "month": month, "last_good_row_count": last_good_row_count,
    }))

# ── Parquet writer (append month-by-month, then merge at the end) ────────────

class MonthlyParquetWriter:
    """Writes one parquet file per accepted month into a staging dir, then
    concatenates everything at the end. Avoids holding the full 2006-today
    dataset in memory while scraping, and makes each month's write atomic —
    if you Ctrl-C mid-run, completed months are already safely on disk."""

    def __init__(self, staging_dir: Path):
        self.staging_dir = staging_dir
        self.staging_dir.mkdir(exist_ok=True)

    def write(self, accepted_date: date, rows: list[dict]):
        if not rows:
            return
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        out = self.staging_dir / f"{accepted_date.isoformat()}.parquet"
        df.to_parquet(out, index=False)

def merge_staged_parquets(staging_dir: Path, output_path: Path):
    files = sorted(staging_dir.glob("*.parquet"))
    if not files:
        log.warning("No staged parquet files found — nothing to merge.")
        return
    log.info("📦 Merging %d monthly parquet files …", len(files))
    dfs = [pd.read_parquet(f) for f in tqdm(files, desc="merging", unit="file")]
    full = pd.concat(dfs, ignore_index=True)
    full = full.drop_duplicates(subset=["date", "scheme_code"]).sort_values(["date", "scheme_code"])
    table = pa.Table.from_pandas(full, preserve_index=False)
    pq.write_table(table, output_path, compression="snappy")
    log.info(
        "✅ %s rows | %s schemes | %s → %s → %s",
        f"{len(full):,}", f"{full['scheme_code'].nunique():,}",
        full["date"].min().date(), full["date"].max().date(), output_path,
    )

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    staging_dir = Path("staging_monthend")

    checkpoint = load_checkpoint()
    months = list(all_months_reverse(START_DATE, END_DATE))

    last_good_row_count = 15000  # optimistic default for recent months; adapts down for older history
    if checkpoint:
        cy, cm = checkpoint["year"], checkpoint["month"]
        months = [(y, m) for (y, m) in months if (y, m) < (cy, cm)]
        last_good_row_count = checkpoint.get("last_good_row_count", last_good_row_count)

    if months:
        log.info("Scraping %d months …", len(months))
        session = requests.Session()
        writer  = MonthlyParquetWriter(staging_dir)
        error_fh = open(ERROR_LOG, "a")
        total_rows = 0

        month_bar = tqdm(months, desc="months", unit="month")
        try:
            for (year, month) in month_bar:
                month_bar.set_postfix(month=f"{year}-{month:02d}", rows=total_rows)

                min_rows = max(MIN_ROWS_FLOOR, int(last_good_row_count * ROW_COUNT_RATIO))
                accepted_date, rows = fetch_month(session, year, month, min_rows)

                if rows:
                    writer.write(accepted_date, rows)
                    total_rows += len(rows)
                    last_good_row_count = len(rows)
                    tqdm.write(f"  ✅ {year}-{month:02d} → {accepted_date} → {len(rows):,} rows (total: {total_rows:,})")
                else:
                    tqdm.write(f"  ─  {year}-{month:02d} → no acceptable trading day found within {MAX_BACKTRACK} days")
                    error_fh.write(json.dumps({"year": year, "month": month, "error": "no data", "min_rows": min_rows}) + "\n")
                    error_fh.flush()

                save_checkpoint(year, month, last_good_row_count)

        except KeyboardInterrupt:
            tqdm.write("\n⛔ Interrupted — progress saved, re-run to resume.")
        finally:
            error_fh.close()
            month_bar.close()
    else:
        log.info("All months already scraped per checkpoint — skipping straight to merge.")

    merge_staged_parquets(staging_dir, OUTPUT_PARQUET)


if __name__ == "__main__":
    main()