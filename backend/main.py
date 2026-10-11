"""
NSE Screener Backend — FastAPI
Endpoints: /api/config, /api/summary, /api/metrics, /api/valuation-data,
           /api/nav-data, /api/scatter-data, /api/calendar-returns,
           /api/rankings, /api/generate-report, /api/mf-config, /api/mf-data,
           /api/health, /api/admin/reload
"""

# ── Standard Library ──────────────────────────────────────────────────────────
from http import client
import io
import logging
import os
import re
import time
import bisect
import random
import asyncio
import traceback

# ── Third-Party ───────────────────────────────────────────────────────────────
import httpx
import numpy as np
import pandas as pd
import duckdb
import xlsxwriter
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from typing import List, Optional
import matplotlib
matplotlib.use("Agg")  # headless backend — avoids GUI/font-cache overhead on cold start
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from xlsxwriter.utility import xl_rowcol_to_cell

# ── Internal ──────────────────────────────────────────────────────────────────
from analytics import (
    CATEGORY_MAP,
    _calc_yearly,
    build_table,
    calc_beta,
    calc_cagr,
    calc_mdd,
    calc_rolling3_metric,
    calc_vol,
    get_start_date,
    load_and_prepare,
    _get_last
)

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE URLS (raw GitHub — mirrored through jsDelivr at fetch time, see below)
# ─────────────────────────────────────────────────────────────────────────────

URL_RETURNS = "https://raw.githubusercontent.com/sirionigiri/nse-data-v2/main/nifty_all_indices_tri.parquet"
URL_INTL = "https://raw.githubusercontent.com/sirionigiri/nse-data-v2/main/data/international_data.parquet"
URL_VALUATION = "https://raw.githubusercontent.com/sirionigiri/nse-data-v2/main/nifty_all_indices_valuation.parquet"
URL_MF = "https://raw.githubusercontent.com/sirionigiri/mf-data/main/amfi_fund_performance_daily.parquet"

FETCH_TIMEOUT = 60
MAX_RETRIES_PER_HOST = 3

# ─────────────────────────────────────────────────────────────────────────────
# APP & MIDDLEWARE
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(default_response_class=ORJSONResponse)

# Allow overriding CORS origins via env var in production without a code
# change; defaults to "*" to preserve existing behavior.
_allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in _allowed_origins.split(",")] if _allowed_origins != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":          # ← let preflight pass through
            return await call_next(request)
        response = await call_next(request)
        if request.method == "GET" and "/api/" in request.url.path:
            response.headers["Cache-Control"] = "public, max-age=3600"
        return response


app.add_middleware(CacheControlMiddleware)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter()
    logger.info(f"🚀 INCOMING: {request.method} {request.url.path}")
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    logger.info(f"✅ COMPLETED: {request.url.path} in {process_time:.4f}s")
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Global safety net: any exception that escapes an endpoint (a bug we didn't
# anticipate, a third-party library raising something unexpected, etc.)
# gets logged with a full traceback and turned into a clean JSON 500
# instead of crashing the worker or leaking a raw stack trace to the client.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"UNHANDLED EXCEPTION on {request.method} {request.url.path}: {exc}")
    logger.error(traceback.format_exc())
    return JSONResponse(status_code=500, content={"error": "internal_server_error", "detail": str(exc)})


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# In-memory data store populated at startup
DATA = {}

# Per-dataset load status, surfaced via /api/health so failures are
# observable instead of silently leaving stale/empty data in place.
DATA_STATUS = {}

_startup_lock = asyncio.Lock()

# Local path where the MF parquet file is downloaded once at startup.
# DuckDB queries this file directly on every request — it reads only the
# columns/rows a given query asks for (columnar + predicate pushdown), so
# the full multi-million-row file is NEVER materialized into a pandas
# DataFrame in process memory. Only small per-request result sets
# (a single day's snapshot, or a filtered/paginated slice of it) ever
# exist in memory, and only for the duration of that request.
MF_PARQUET_PATH = "/tmp/mf_data.parquet"

# Columns returned by MF queries (mirrors what the frontend/report consume)
MF_SELECT_COLS = [
    "schemeName",
    "benchmark",
    "riskometerScheme",
    "navRegular",
    "return1YearRegular",
    "return3YearRegular",
    "return5YearRegular",
    "return10YearRegular",
    "_category",
    "_subCategory",
]

# Sort column can't be parameterized in SQL (placeholders only work for
# values, not identifiers), so any user-supplied sort_by must be checked
# against this whitelist before being interpolated into the query string.
ALLOWED_MF_SORT_COLS = {
    "schemeName", "benchmark", "riskometerScheme", "navRegular",
    "return1YearRegular", "return3YearRegular", "return5YearRegular", "return10YearRegular",
}

# Optional token to protect the manual reload endpoint. If unset, the
# endpoint is open — fine for internal/staging use, but set RELOAD_TOKEN
# in production.
RELOAD_TOKEN = os.environ.get("RELOAD_TOKEN")

# Maps index names to human-readable sector/type labels used in the Excel report
REPORT_SECTOR_MAP = {
    "NIFTY 500": "Benchmark",
    "NIFTY ENERGY": "Energy",
    "NIFTY AUTO": "Auto",
    "NIFTY INDIA MFG": "Manufacturing",
    "NIFTY BANK": "Banks",
    "NIFTY CAPITAL MKT": "Capital Market",
    "NIFTY FINSEREXBNK": "Finserv",
    "NIFTY CPSE": "Energy",
    "NIFTY CEMENT": "Infra",
    "NIFTY CHEMICALS": "Chemicals",
    "NIFTY METAL": "Metals",
    "NIFTY MNC": "MNC",
    "NIFTY HEALTHCARE": "Pharma",
    "NIFTY IT": "IT",
    "NIFTY IPO": "IPO",
    "NIFTY IND DEFENCE": "Defence",
    "NIFTY IND TOURISM": "Tourism",
    "NIFTY INFRA": "Infra",
    "NIFTY REALTY": "Real Estate",
}

# Static factor ranking table (2016–2025) written into the Excel Factor sheet
FACTOR_RANKS_STATIC = [
    ["Rank", "2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025"],
    ["1", "Value", "Momentum", "Low Vol", "NIFTY 500", "Quality", "Momentum", "Value", "Value", "Momentum", "Value"],
    ["2", "NIFTY 500", "Equal Weight", "NIFTY 500", "Momentum", "Equal Weight", "Value", "Low Vol", "Momentum", "Quality", "Low Vol"],
    ["3", "Momentum", "Value", "Quality", "Low Vol", "Low Vol", "Equal Weight", "NIFTY 500", "Equal Weight", "Equal Weight", "NIFTY 500"],
    ["4", "Low Vol", "NIFTY 500", "Momentum", "Quality", "Momentum", "NIFTY 500", "Equal Weight", "Quality", "Value", "Equal Weight"],
    ["5", "Quality", "Quality", "Equal Weight", "Equal Weight", "NIFTY 500", "Quality", "Quality", "Low Vol", "NIFTY 500", "Quality"],
    ["6", "Value", "Low Vol", "Value", "Value", "Value", "Low Vol", "Momentum", "NIFTY 500", "Low Vol", "Momentum"],
]


INTL_CURRENCY_MAP = {
    "S&P 500": "USD",
    "NIFTY 50": "INR",
    "Nasdaq 100 Futures": "USD",
    "KOSPI": "KRW",
    "Shanghai Composite": "CNY",
    "EEM": "USD",
    "TAIEX": "TWD",
    "Bovespa": "BRL",
    "Mexico IPC": "MXP",
    "S&P Europe 350": "EUR",
    "Gold": "USD",
    "Silver": "USD",
    "Bitcoin": "USD"
}

INTL_REPORT_LIST = [
    "S&P 500", "NIFTY 50", "Nasdaq 100 Futures", "KOSPI", "Shanghai Composite",
    "EEM", "TAIEX", "Bovespa", "Mexico IPC", "S&P Europe 350", "Gold", "Silver", "Bitcoin"
]

MF_MAP = {
    1: {"name": "Equity", "subs": {1: "Large Cap", 2: "Large & Mid Cap", 3: "Flexicap", 4: "Multi Cap", 5: "Mid Cap", 6: "Small Cap", 7: "Value", 8: "ELSS", 9: "Contra", 10: "Dividend Yield", 11: "Focused", 12: "Sectoral/Thematic"}},
    2: {"name": "Debt", "subs": {13: "Long Duration", 14: "Income", 15: "Short Term", 16: "Medium Term", 17: "Money Market", 18: "Low Duration", 19: "Ultra Short Duration", 20: "Liquid", 21: "Overnight", 22: "Dynamic Bond", 23: "Corporate Bond", 24: "Credit Risk", 25: "Banking & PSU", 26: "Floater", 28: "Gilt", 29: "Gilt 10yr Constant Duration"}},
    3: {"name": "Hybrid", "subs": {30: "Aggressive Hybrid", 31: "Conservative Hybrid", 32: "Equity Savings", 33: "Arbitrage", 34: "Multi Asset Allocation", 35: "Balanced Advantage"}},
    4: {"name": "Solution Oriented", "subs": {36: "Children's Fund", 37: "Retirement Fund"}},
    5: {"name": "Other", "subs": {38: "Index/Passive", 39: "Gold/Silver ETF FOF"}}
}

URL_MF_NAV = "https://raw.githubusercontent.com/sirionigiri/nse-data-v2/main/data/mf_monthly_growth_nav.parquet"

MF_CLASS_DEFAULTS = {
    "Large-Cap": {"benchmark": "NIFTY 100", "extras": ["NIFTY 50", "NIFTY100 QUALITY 30", "NIFTY200 MOMENTUM 30"]},
    "Mid-Cap": {"benchmark": "NIFTY MIDCAP 150", "extras": ["NIFTY MIDCAP150 QUALITY 50", "NIFTY MIDCAP150 MOMENTUM 50"]},
    "Small-Cap": {"benchmark": "NIFTY SMALLCAP 250", "extras": ["NIFTY SMALLCAP250 QUALITY 50", "NIFTY SMALLCAP250 MOMENTUM QUALITY 100"]},
    "Flexi-Cap & Multi-Cap": {"benchmark": "NIFTY 500", "extras": ["NIFTY500 MULTICAP 50:25:25", "NIFTY500 FLEXICAP QUALITY 30"]},
    "Thematic": {"benchmark": "NIFTY 500", "extras": []},
    "ELSS": {"benchmark": "NIFTY 500", "extras": []},
    "International": {"benchmark": "S&P 500", "extras": ["Nasdaq 100 Futures"]},
}


class MFAnalysisRequest(BaseModel):
    fund_class: str
    benchmark_index: Optional[str] = None
    extra_indices: Optional[List[str]] = None       # None -> class defaults
    reference_date: Optional[str] = None
    n_years: int = 12
    min_history_months: int = 12
    include_partial_in_rank: bool = False
    rank_with_indices: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST MODELS
# ─────────────────────────────────────────────────────────────────────────────

class MetricsRequest(BaseModel):
    metric: str
    periods: List[str]
    indices: List[str]
    benchmark: str
    reference_date: Optional[str] = None
    include_mf: Optional[bool] = False
    # Optional MF filters for the report's "Mutual Funds" sheet.
    mf_search: Optional[str] = ""
    mf_subcategories: Optional[List[int]] = []
    mf_riskometers: Optional[List[str]] = []
    mf_benchmarks: Optional[List[str]] = []


class MFDataRequest(BaseModel):
    search: Optional[str] = ""
    subcategories: List[int] = []      # flat list of _subCategory ids, e.g. [1,2,5]
    riskometers: List[str] = []        # e.g. ["Very High", "High"]
    benchmarks: List[str] = []         # e.g. ["Nifty 100 TRI"]
    compare_index: Optional[str] = None  # OUR index name (global benchmark) to compare against
    reference_date: Optional[str] = None
    page: int = 1
    page_size: int = 100
    sort_by: str = "return1YearRegular"
    sort_dir: str = "desc"


# ─────────────────────────────────────────────────────────────────────────────
# NETWORK HELPERS — retry, fallback, validation
# ─────────────────────────────────────────────────────────────────────────────

def to_jsdelivr(raw_url: str) -> str:
    """Convert a raw.githubusercontent.com URL into its jsDelivr GitHub-CDN
    equivalent. jsDelivr fronts GitHub content behind a real CDN and is far
    less prone to the 429s that raw.githubusercontent.com hands out —
    especially from shared IP ranges like Vercel's, where you get rate
    limited by *other* tenants' traffic, not just your own."""
    m = re.match(r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)", raw_url)
    if not m:
        return raw_url
    user, repo, branch, path = m.groups()
    return  raw_url


def build_source_urls(raw_url: str) -> list:
    """Ordered list of candidate URLs for a file: jsDelivr first (CDN,
    rate-limit resistant), falling back to the original raw GitHub URL if
    jsDelivr ever fails, is stale, or hasn't picked up a brand-new file yet."""
    jsdelivr_url = to_jsdelivr(raw_url)
    return [jsdelivr_url, raw_url] if jsdelivr_url != raw_url else [raw_url]


async def fetch_parquet_bytes(
    client: httpx.AsyncClient,
    candidate_urls: list,
    timeout: int = FETCH_TIMEOUT,
    max_retries: int = MAX_RETRIES_PER_HOST,
) -> bytes:
    """Fetch a parquet file, trying each candidate URL in turn with
    retry+backoff on transient failures (429s, timeouts, connection errors).
    Validates the response actually looks like parquet (size + magic bytes)
    before returning it, so a rate-limit page or CDN error page fails loudly
    and clearly here instead of crashing deep inside pyarrow with a cryptic
    'magic bytes not found in footer' error."""
    last_exc = None
    for url in candidate_urls:
        for attempt in range(max_retries):
            try:
                res = await client.get(url, timeout=timeout)
                if res.status_code == 429:
                    retry_after = res.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else (2 ** attempt) + random.random()
                    logger.warning(f"429 from {url} (attempt {attempt + 1}/{max_retries}), waiting {wait:.1f}s")
                    await asyncio.sleep(wait)
                    continue
                res.raise_for_status()
                content = res.content
                if len(content) < 1024 or not content.startswith(b"PAR1"):
                    raise ValueError(
                        f"Response from {url} doesn't look like valid parquet "
                        f"({len(content)} bytes) — likely rate-limited or an error page."
                    )
                return content
            except (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException, ValueError) as e:
                last_exc = e
                wait = (2 ** attempt) + random.random()
                logger.warning(f"Fetch failed for {url} (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait)
        logger.warning(f"Exhausted retries for {url}, trying next source if any remain")
    raise RuntimeError(f"Failed to fetch parquet from all candidates: {candidate_urls}") from last_exc


def _mark_status(key: str, ok: bool, error: Exception = None):
    DATA_STATUS[key] = {
        "ok": ok,
        "loaded_at": pd.Timestamp.utcnow().isoformat(),
        "error": f"{type(error).__name__}: {error}" if error else None,
    }
    

async def load_mf_nav_data(client: httpx.AsyncClient):
    content = await fetch_parquet_bytes(client, build_source_urls(URL_MF_NAV))
    df = pd.read_parquet(io.BytesIO(content))
    df["month"] = pd.to_datetime(df["month"])
    df = df.drop_duplicates(["scheme_code", "month"], keep="last")

    wide = df.pivot(index="month", columns="scheme_code", values="nav").sort_index()
    full_idx = pd.period_range(wide.index.min(), wide.index.max(), freq="M").to_timestamp(how="end").normalize()
    raw = wide.reindex(full_idx)                    # real observations only
    DATA["mf_nav_raw"] = raw
    DATA["mf_nav_wide"] = raw.ffill(limit=1)        # bridge 1-month holes for the maths
    wide = DATA["mf_nav_wide"]                      # keep the log line below working
    
    DATA["mf_nav_meta"] = (
        df.sort_values("month").drop_duplicates("scheme_code", keep="last")
        .set_index("scheme_code")[["scheme_name", "amc", "fund_class"]]
    )
    _mark_status("mf_nav", True)
    logger.info(f"✅ MF NAV ready: {wide.shape[1]} schemes x {wide.shape[0]} months.")


# ─────────────────────────────────────────────────────────────────────────────
# GENERAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_perf_row_data(idx, ed, periods, benchmark):
    """Gathers performance data for a single index across multiple periods."""
    results = []
    for p in periods:
        try:
            if p == "Rolling 3-Yr Avg":
                val = calc_rolling3_metric(DATA['rebased'], DATA['returns'], 'cagr', [idx], benchmark, ed)[idx]
            else:
                sd = get_start_date(p, ed)
                if p == "MTD":
                    sd_calc = pd.Timestamp(f"{ed.year}-{ed.month:02d}-01")
                elif p == "YTD":
                    sd_calc = pd.Timestamp(f"{ed.year}-01-01")
                else:
                    sd_calc = sd
                val = calc_cagr(DATA['rebased'], sd_calc, ed, [idx], label=p)[idx]
            results.append(clean_float(val))
        except:
            results.append(None)
    return results


def get_effective_end_date(req_date: Optional[str]):
    """Return a normalized Timestamp for the requested reference date,
    falling back to the dataset's last available date."""
    if req_date:
        try:
            return pd.to_datetime(req_date).normalize()
        except Exception:
            pass
    return DATA.get("end_date")


def clean_float(val) -> Optional[float]:
    """Convert a value to a JSON-safe float (NaN / Inf → None)."""
    if val is None or not np.isfinite(val):
        return None
    return round(float(val), 2)


def require_data(*keys: str):
    """Raise a clear, specific 503 naming exactly which dataset is missing,
    instead of a generic 'service unavailable'. Use at the top of any
    endpoint that depends on startup-loaded data."""
    missing = [k for k in keys if k not in DATA]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"Data not ready: {', '.join(missing)}. Check /api/health.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# DUCKDB HELPERS — mutual fund data lives entirely on disk, queried on demand
# ─────────────────────────────────────────────────────────────────────────────

def mf_query(sql: str, params: list = None) -> pd.DataFrame:
    """Run a SQL query against the MF parquet file via a fresh, lightweight
    DuckDB connection. DuckDB reads parquet column-by-column with predicate
    pushdown, so this only materializes the columns/rows the query actually
    asks for — never the full multi-million-row file — keeping memory flat
    regardless of how large the underlying dataset grows. A fresh connection
    per call keeps this safe to run concurrently across request threads."""
    con = duckdb.connect()
    try:
        return con.execute(sql, params or []).df()
    except Exception as e:
        logger.error(f"DuckDB query failed: {e}\nSQL: {sql}\nParams: {params}")
        raise
    finally:
        con.close()


def find_mf_snapshot_date(effective_ed: pd.Timestamp):
    """Return the most recent MF snapshot date on or before effective_ed."""
    dates = DATA.get('mf_dates')
    if not dates:
        return None
    idx = bisect.bisect_right(dates, effective_ed) - 1
    if idx < 0:
        return None
    return dates[idx]


def build_mf_where_clause(search, subcategories, riskometers, benchmarks, snap_date):
    """Shared WHERE-clause builder for /api/mf-data and the report's MF
    sheet, so filter semantics can't drift between the two call sites."""
    clauses = ["_date = ?"]
    params = [snap_date]

    if search:
        clauses.append("schemeName ILIKE ?")
        params.append(f"%{search}%")
    if subcategories:
        placeholders = ",".join(["?"] * len(subcategories))
        clauses.append(f"_subCategory IN ({placeholders})")
        params.extend(subcategories)
    if riskometers:
        placeholders = ",".join(["?"] * len(riskometers))
        clauses.append(f"riskometerScheme IN ({placeholders})")
        params.extend(riskometers)
    if benchmarks:
        placeholders = ",".join(["?"] * len(benchmarks))
        clauses.append(f"benchmark IN ({placeholders})")
        params.extend(benchmarks)

    return " AND ".join(clauses), params


# ─────────────────────────────────────────────────────────────────────────────
# STARTUP — per-dataset loaders, isolated so one failure can't sink the rest
# ─────────────────────────────────────────────────────────────────────────────

async def load_market_data(client: httpx.AsyncClient):
    """NIFTY (required) + International (best-effort) -> rebased/returns/yearly."""
    content = await fetch_parquet_bytes(client, build_source_urls(URL_RETURNS))
    df_nifty_raw = pd.read_parquet(io.BytesIO(content))
    df_nifty_raw['Date'] = pd.to_datetime(df_nifty_raw['Date'])
    df_nifty_raw.columns = [c.strip() for c in df_nifty_raw.columns]

    prep = load_and_prepare(df_nifty_raw)
    nifty_wide = prep['rebased']
    combined_wide = nifty_wide

    try:
        intl_content = await fetch_parquet_bytes(client, build_source_urls(URL_INTL))
        df_intl_raw = pd.read_parquet(io.BytesIO(intl_content))

        if isinstance(df_intl_raw.columns, pd.MultiIndex):
            df_intl_raw.columns = df_intl_raw.columns.get_level_values(-1)

        df_intl_raw.index = pd.to_datetime(df_intl_raw.index)
        df_intl_raw.index.name = 'Date'

        df_intl_rebased = df_intl_raw.apply(
            lambda col: col / col.dropna().iloc[0] * 100 if col.dropna().size > 0 else col
        )

        combined_wide = pd.concat([nifty_wide, df_intl_rebased], axis=1).sort_index()
        combined_wide = combined_wide.loc[:, ~combined_wide.columns.duplicated()].copy()
        combined_wide = combined_wide.ffill()
        logger.info("✅ International data merged.")
    except Exception as intl_err:
        logger.warning(f"⚠️ International data unavailable, continuing with NIFTY-only universe: {intl_err}")

    DATA['rebased'] = combined_wide
    DATA['returns'] = (combined_wide.pct_change(fill_method=None).ffill() * 100).round(4)
    DATA['yearly'] = _calc_yearly(combined_wide)
    DATA['end_date'] = combined_wide.index.max()
    DATA['indices'] = sorted(combined_wide.columns.tolist())
    _mark_status('market', True)
    logger.info(f"🚀 Market data ready: {len(DATA['indices'])} assets.")


async def load_valuation_data(client: httpx.AsyncClient):
    content = await fetch_parquet_bytes(client, build_source_urls(URL_VALUATION))
    df_v = pd.read_parquet(io.BytesIO(content))
    if 'Date' not in df_v.columns and df_v.index.name == 'Date':
        df_v = df_v.reset_index()
    df_v['Date'] = pd.to_datetime(df_v['Date'])
    df_v['Index_Name'] = df_v['Index_Name'].astype(str).str.strip()
    DATA['valuation'] = df_v
    _mark_status('valuation', True)
    logger.info("✅ Valuation data ready.")


async def load_mf_data(client: httpx.AsyncClient):
    """Download the MF parquet to local disk and index its snapshot dates +
    filter facets via DuckDB. The file itself is never loaded into pandas —
    every request-time read goes straight through DuckDB against this path."""
    content = await fetch_parquet_bytes(client, build_source_urls(URL_MF))

    os.makedirs(os.path.dirname(MF_PARQUET_PATH) or ".", exist_ok=True)
    tmp_path = MF_PARQUET_PATH + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(content)
    os.replace(tmp_path, MF_PARQUET_PATH)  # atomic swap — never leaves a half-written file in place

    dates_df = mf_query(f"SELECT DISTINCT _date FROM read_parquet('{MF_PARQUET_PATH}') ORDER BY _date")
    mf_dates = [pd.Timestamp(d) for d in dates_df['_date']]
    if not mf_dates:
        raise RuntimeError("MF parquet downloaded but contains no dates")

    latest_date = mf_dates[-1]
    cfg_df = mf_query(
        """
        SELECT DISTINCT _subCategory, riskometerScheme, benchmark
        FROM read_parquet(?)
        WHERE _date = ?
          AND _subCategory IS NOT NULL
          AND riskometerScheme IS NOT NULL
          AND benchmark IS NOT NULL
        """,
        [MF_PARQUET_PATH, latest_date],
    )

    DATA['mf_dates'] = mf_dates
    DATA['mf_parquet_path'] = MF_PARQUET_PATH
    DATA['mf_config'] = {
        "categories": MF_MAP,
        "riskometers": sorted(cfg_df['riskometerScheme'].dropna().unique().tolist()),
        "benchmarks": sorted(cfg_df['benchmark'].dropna().unique().tolist()),
        "facets": [
            {
                "subcategory": int(row['_subCategory']),
                "riskometer": row['riskometerScheme'],
                "benchmark": row['benchmark'],
            }
            for _, row in cfg_df.iterrows()
        ],
    }
    _mark_status('mf', True)
    logger.info(
        f"✅ MF data ready via DuckDB: {len(mf_dates)} snapshot dates, "
        f"{os.path.getsize(MF_PARQUET_PATH) / 1e6:.1f} MB on disk (not held in process memory)."
    )


@app.on_event("startup")
async def startup_event():
    async with _startup_lock:
        async with httpx.AsyncClient() as client:
            # Run all three loaders concurrently and independently: a
            # failure in one (return_exceptions=True) can't block or crash
            # the others, and total startup time is roughly the slowest
            # single loader instead of the sum of all three.
            labels = ["market", "valuation", "mf", "mf_nav"]
            tasks = [load_market_data(client), load_valuation_data(client), load_mf_data(client), load_mf_nav_data(client)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for label, result in zip(labels, results):
                if isinstance(result, Exception):
                    logger.error(f"❌ {label} load failed: {result}")
                    logger.error("".join(traceback.format_exception(type(result), result, result.__traceback__)))
                    _mark_status(label, False, result)

    if 'rebased' not in DATA:
        logger.error("❌ CRITICAL: market data failed to load — most endpoints will return 503.")
    else:
        logger.info("🚀 ENGINE READY.")


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS — health & ops
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {
        "status": "ok" if 'rebased' in DATA else "degraded",
        "datasets": DATA_STATUS,
        "assets_loaded": len(DATA.get('indices', [])),
        "valuation_available": 'valuation' in DATA,
        "mf_available": 'mf_dates' in DATA,
        "mf_snapshot_count": len(DATA.get('mf_dates', [])),
    }


@app.post("/api/admin/reload")
async def admin_reload(request: Request):
    """Manually re-run startup loaders without redeploying — useful for
    recovering from a transient source failure (e.g. all retries exhausted
    during a GitHub outage) on an already-warm instance."""
    if RELOAD_TOKEN:
        if request.headers.get("X-Reload-Token") != RELOAD_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid or missing reload token")
    await startup_event()
    return {"status": "reload complete", "datasets": DATA_STATUS}


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS — read-only / config
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    require_data("indices")
    return {"indices": DATA["indices"], "categories": CATEGORY_MAP}


@app.get("/api/calendar-returns")
def get_calendar_returns():
    require_data("yearly")
    start = DATA["rebased"].index.min().strftime("%d %b %Y")
    end = DATA["rebased"].index.max().strftime("%d %b %Y")
    return {
        "data": DATA["yearly"].reset_index().replace({np.nan: None}).to_dict("records"),
        "scope": f"{start} to {end}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS — metrics / analytics
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/summary")
def get_summary_metrics(request: MetricsRequest):
    require_data("rebased")
    try:
        effective_ed = get_effective_end_date(request.reference_date)
        df_rb = DATA["rebased"]

        bench_name = next(
            (c for c in df_rb.columns if c.upper() == request.benchmark.upper()),
            df_rb.columns[0],
        )

        c1 = calc_cagr(df_rb, get_start_date("1 Yr", effective_ed), effective_ed, [bench_name], label="1 Yr")[bench_name]
        c20 = calc_cagr(df_rb, get_start_date("20 Yr", effective_ed), effective_ed, [bench_name], label="20 Yr")[bench_name]

        ytd_start = pd.Timestamp(f"{effective_ed.year}-01-01")
        dd_ytd = calc_mdd(df_rb, ytd_start, effective_ed, [bench_name])[bench_name]
        v_ytd = calc_vol(DATA["returns"], ytd_start, effective_ed, [bench_name])[bench_name]

        def fmt_summary(val):
            if val is None or not np.isfinite(val):
                return "—"
            return f"{val:+.1f}%"

        return {
            "cagr1": fmt_summary(c1),
            "cagr20": fmt_summary(c20),
            "mdd1": fmt_summary(dd_ytd),
            "vol1": fmt_summary(v_ytd),
            "count": len(request.indices),
        }
    except Exception as e:
        logger.error(f"Summary Error: {e}")
        return {"error": str(e)}


@app.post("/api/metrics")
def get_metrics_table(request: MetricsRequest):
    require_data("rebased")
    try:
        effective_ed = get_effective_end_date(request.reference_date)

        all_cols = DATA["rebased"].columns.tolist()
        req_indices = [idx.strip().upper() for idx in request.indices]
        valid_indices = [c for c in all_cols if c.strip().upper() in req_indices]

        bench_match = next(
            (c for c in all_cols if c.strip().upper() == request.benchmark.strip().upper()),
            "NIFTY 50",
        )

        if not valid_indices:
            return {"data": [], "error": "No valid indices selected"}

        kw = dict(
            df_rb=DATA["rebased"],
            df_ret=DATA["returns"],
            periods=request.periods,
            cols=valid_indices,
            bench=bench_match,
            end_actual=effective_ed,
            include_roll3=(request.metric != "mdd"),
        )

        if request.metric == "exc":
            df_c = build_table(metric="cagr", **kw)
            df_res = df_c.sub(df_c[bench_match], axis=0)
        elif request.metric == "ra":
            df_res = build_table(metric="cagr", **kw) / build_table(metric="vol", **kw)
        elif request.metric == "ir":
            df_c = build_table(metric="cagr", **kw)
            df_e = df_c.sub(df_c[bench_match], axis=0)
            df_t = build_table(metric="te", **kw)
            df_res = df_e / df_t
        else:
            df_res = build_table(metric=request.metric, **kw)

        ed_str = effective_ed.strftime("%d %b %y")
        date_ranges = {}
        for p in df_res.index:
            if p == "Rolling 3-Yr Avg":
                yr = effective_ed.year - 1
                date_ranges[p] = f"Jan {yr - 2} - Dec {yr}"
            else:
                target_sd = get_start_date(p, effective_ed)
                _, actual_sd = _get_last(DATA["rebased"][bench_match], target_sd)

                if p == "MTD":
                    sd_show = pd.Timestamp(f"{effective_ed.year}-{effective_ed.month:02d}-01")
                elif p == "YTD":
                    sd_show = pd.Timestamp(f"{effective_ed.year}-01-01")
                else:
                    sd_show = actual_sd if actual_sd else target_sd

                date_ranges[p] = f"{sd_show.strftime('%d %b %y')} - {ed_str}"

        df_res = df_res.reset_index().rename(columns={"index": "Period"})
        df_res["Range"] = df_res["Period"].map(date_ranges)

        return {
            "data": df_res.replace({np.nan: None, np.inf: None, -np.inf: None}).to_dict("records"),
            "error": None,
        }
    except Exception as e:
        logger.error(f"Metrics Error: {traceback.format_exc()}")
        return {"data": [], "error": str(e)}


VALUATION_BOUNDS = {
    "PE": (0, 100),
    "PB": (0, 30),
    "Div_Yield": (0, 15),
}


def clean_valuation_column(s: pd.Series, bounds: tuple) -> pd.Series:
    """Treat out-of-range values as missing, then forward-fill from prior valid data."""
    lo, hi = bounds
    s = s.mask((s < lo) | (s > hi))
    s = s.ffill()
    return s


@app.post("/api/valuation-data")
def get_val_data(request: MetricsRequest):
    require_data("valuation")
    try:
        effective_ed = get_effective_end_date(request.reference_date)
        df_full = DATA['valuation']

        df = df_full[df_full['Index_Name'].str.upper() == request.benchmark.upper()].sort_values('Date').copy()
        if df.empty: return {"error": f"No data for {request.benchmark}"}

        for col, bounds in VALUATION_BOUNDS.items():
            if col in df.columns:
                df[col] = clean_valuation_column(df[col], bounds)

        period = request.periods[0] if request.periods else "5 Yr"
        sd = get_start_date(period, effective_ed)
        df_w = df[(df['Date'] >= sd) & (df['Date'] <= effective_ed)].copy()

        if df_w.empty: return {"error": "Insufficient data in selected window"}

        def stats_for_window(s):
            clean_s = s.dropna()
            if clean_s.empty: return None

            m, std = clean_s.median(), clean_s.std()
            if not np.isfinite(std): std = 0

            return {
                k: clean_float(v) for k, v in {
                    "median": m,
                    "upper4": m + 4*std, "upper3": m + 3*std,
                    "upper2": m + 2*std, "upper1": m + std,
                    "lower1": m - std, "lower2": m - 2*std
                }.items()
            }

        return {
            "dates": df_w['Date'].dt.strftime('%Y-%m-%d').tolist(),
            "pe": {"values": [clean_float(v) for v in df_w['PE']], "stats": stats_for_window(df_w['PE'])},
            "pb": {"values": [clean_float(v) for v in df_w['PB']], "stats": stats_for_window(df_w['PB'])},
            "dy": {"values": [clean_float(v) for v in df_w['Div_Yield']], "stats": stats_for_window(df_w['Div_Yield'])}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/nav-data")
def get_nav_data(request: MetricsRequest):
    require_data("rebased")

    effective_ed = get_effective_end_date(request.reference_date)
    sd = get_start_date(request.periods[0], effective_ed)

    valid_cols = [c for c in request.indices if c in DATA["rebased"].columns]
    if request.benchmark and request.benchmark not in valid_cols:
        valid_cols.append(request.benchmark)

    df = (
        DATA["rebased"][valid_cols]
        .loc[(DATA["rebased"].index >= sd) & (DATA["rebased"].index <= effective_ed)]
        .dropna(how="all")
    )
    if df.empty:
        return []

    if request.metric == "drawdown":
        df = (df / df.cummax() - 1) * 100
    else:
        df = df.apply(
            lambda col: col / col.dropna().iloc[0] * 100 if col.dropna().size > 0 else col
        )

    output = []
    for col in df.columns:
        s = df[col].replace([np.inf, -np.inf], np.nan).dropna()
        output.append({"x": s.index.strftime("%Y-%m-%d").tolist(), "y": s.values.tolist(), "name": col})
    return output


@app.post("/api/scatter-data")
def get_scatter_data(request: MetricsRequest):
    require_data("rebased")

    effective_ed = get_effective_end_date(request.reference_date)
    sd = get_start_date(request.periods[0] if request.periods else "5 Yr", effective_ed)

    valid_indices = [idx for idx in request.indices if idx in DATA["rebased"].columns]
    if not valid_indices:
        return []

    cagrs = calc_cagr(DATA["rebased"], sd, effective_ed, valid_indices)
    vols = calc_vol(DATA["returns"], sd, effective_ed, valid_indices)

    return [
        {"index": idx, "return": clean_float(cagrs.get(idx)), "risk": clean_float(vols.get(idx))}
        for idx in valid_indices
        if np.isfinite(cagrs.get(idx, np.nan)) and np.isfinite(vols.get(idx, np.nan))
    ]


@app.post("/api/rankings")
def get_calendar_rankings(request: MetricsRequest):
    try:
        require_data("yearly")

        all_cols = DATA['yearly'].columns.tolist()
        selected = [s.strip() for s in request.indices]
        available_cols = [c for c in all_cols if c.strip() in selected]

        if not available_cols:
            return []

        df_selected = DATA['yearly'][available_cols].copy()
        rank_df = df_selected.rank(axis=1, ascending=False, method='min')

        results = []
        for year, row in rank_df.iterrows():
            y_label = str(year).split('-')[0]
            item = {"Year": y_label}

            valid_row = False
            for idx_name, rank_val in row.items():
                if not np.isnan(rank_val):
                    item[f"Rank {int(rank_val)}"] = idx_name
                    valid_row = True

            if valid_row:
                results.append(item)

        return results
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rankings Error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — Excel report generation
# ─────────────────────────────────────────────────────────────────────────────

def create_matplotlib_gauge(current, min_val, max_val, median_val, reverse=False):
    """Creates a linear gauge with a black pointer and blue median line."""

    try:
        pos = (current - min_val) / (max_val - min_val) if max_val != min_val else 0.5
        pos_med = (median_val - min_val) / (max_val - min_val) if max_val != min_val else 0.5

        pos = max(0, min(1, pos))
        pos_med = max(0, min(1, pos_med))
    except Exception:
        pos, pos_med = 0.5, 0.5

    fig, ax = plt.subplots(figsize=(4, 0.8))

    cmap = "RdYlGn_r" if not reverse else "RdYlGn"
    cmap_obj = plt.get_cmap(cmap)

    gradient = np.linspace(0, 1, 256).reshape(1, -1)
    ax.imshow(gradient, aspect="auto", extent=[0, 1, 0, 0.25], cmap=cmap_obj)

    ax.plot([pos_med, pos_med], [0, 0.25], color="#2563eb", linewidth=2.5, zorder=11)

    ax.scatter(pos, 0.35, marker="v", s=200, color="black", zorder=12)

    txt_style = {"fontsize": 9, "fontweight": "bold", "family": "sans-serif"}

    ax.text(0, 0.5, f"{min_val:.1f}", ha="left", color="#64748b", **txt_style)
    ax.text(1, 0.5, f"{max_val:.1f}", ha="right", color="#64748b", **txt_style)

    bg_rgb = cmap_obj(pos)[:3]
    luminance = 0.2126 * bg_rgb[0] + 0.7152 * bg_rgb[1] + 0.0722 * bg_rgb[2]

    text_color = "black" if luminance > 0.55 else "white"
    outline_color = "white" if text_color == "black" else "black"

    current_text = ax.text(
        pos, 0.1, f"{current:.1f}", ha="center", va="center",
        color=text_color, zorder=20, **txt_style,
    )
    current_text.set_path_effects([pe.withStroke(linewidth=2, foreground=outline_color)])

    med_text = ax.text(
        pos_med, 0.45, "MED", ha="center", color="#2563eb",
        fontsize=7, fontweight="black", zorder=20,
    )
    med_text.set_path_effects([pe.withStroke(linewidth=1.5, foreground="white")])

    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.1, 0.7)
    ax.axis("off")

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.02, transparent=True, dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf


SECTOR_RANK_MAP = {
    "NIFTY AUTO": "AUTO", "NIFTY BANK": "BANKS", "NIFTY CAPITAL MKT": "CAPITAL MKTS",
    "NIFTY CEMENT": "CEMENT", "NIFTY CHEMICALS": "CHEMICALS", "NIFTY CONSR DURBL": "CONSUMER DURABLES",
    "NIFTY FINSEREXBNK": "FINANCIALS exBANKS", "NIFTY FMCG": "FMCG",
    "NIFTY IND DEFENCE": "DEFENCE", "NIFTY IND TOURISM": "TOURISM", "NIFTY INDIA MFG": "MANUFACTURING",
    "NIFTY INFRA": "INFRA", "NIFTY IPO": "IPO", "NIFTY IT": "IT", "NIFTY METAL": "METALS",
    "NIFTY OIL AND GAS": "OIL AND GAS", "NIFTY REALTY": "REALTY",
    "NIFTY REITS & INVITS": "REITS & INVITS", "NIFTY500 HEALTH": "HEALTHCARE",
}

FACTOR_RANK_MAP = {
    "NIFTY 500": "Benchmark", "NIFTY500 QUALITY 50": "Quality", "NIFTY500 VALUE 50": "Value",
    "NIFTY500 MOMENTUM 50": "Momentum", "NIFTY500 LOW VOLATILITY 50": "Low Volatility",
    "NIFTY500 EQUAL WEIGHT": "Size (small)", "NIFTY500 MULTIFACTOR MQVLV 50": "Multi-Factor",
}


# NOTE: this is a plain `def`, not `async def`. Nothing in its body awaits
# anything — it's pure CPU/IO-bound work (DuckDB queries, matplotlib
# rendering, xlsxwriter). As `async def`, that work would run directly on
# the event loop and block every other concurrent request for however long
# the report takes to build. As a sync `def`, FastAPI automatically runs it
# in the default threadpool, keeping the event loop free.
@app.post("/api/generate-report")
def generate_report(request: MetricsRequest):
    require_data("rebased")

    try:
        effective_ed = get_effective_end_date(request.reference_date)
        five_yrs_ago = effective_ed - pd.DateOffset(years=5)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        title_f = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': 'black', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'font_size': 12})
        head_f  = workbook.add_format({'bold': True, 'bg_color': '#F2F2F2', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        text_f  = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter', 'font_size': 9})
        perc_f  = workbook.add_format({'num_format': '0.0"%"', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        num_f   = workbook.add_format({'num_format': '0.0', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        rank_f  = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 8, 'text_wrap': True})
        italic_f = workbook.add_format({'italic': True, 'font_size': 8, 'text_wrap': True})

        factor_list = list(FACTOR_RANK_MAP.keys())
        s_indices = [idx for idx in request.indices if idx not in factor_list]
        f_indices = [idx for idx in request.indices if idx in factor_list]

        bench = request.benchmark if request.benchmark in DATA['rebased'].columns else "NIFTY 50"
        if bench not in s_indices: s_indices.insert(0, bench)
        if bench not in f_indices: f_indices.insert(0, bench)

        num_periods = len(request.periods)

        # ── SHEET 1: SECTOR & THEMATIC ──────────────────────────────────────────
        ws1 = workbook.add_worksheet("Sector Dashboard")
        ws1.set_column('A:A', 35)
        ws1.set_column('B:M', 12)
        ws1.set_column('I:K', 32)

        ws1.merge_range('A1:K1', 'Sector & Thematic Dashboard', title_f)
        ws1.merge_range(1, 1, 1, num_periods, 'Performance (%)', head_f)
        ws1.merge_range(1, 1 + num_periods, 1, 3 + num_periods, 'Valuations (5Y Linear Gauge)', head_f)
        ws1.write_row('A3', ["Indices"] + request.periods + ["P/E", "P/B", "DY"], head_f)

        row_idx = 3
        for idx in s_indices[:19]:
            ws1.set_row(row_idx, 45)
            ws1.write(row_idx, 0, idx, text_f)
            ws1.write_row(row_idx, 1, get_perf_row_data(idx, effective_ed, request.periods, bench), perc_f)
            try:
                v_df = DATA.get('valuation')
                if v_df is not None:
                    hist = v_df[
                        (v_df['Index_Name'].str.upper() == idx.upper()) &
                        (v_df['Date'] >= five_yrs_ago) &
                        (v_df['Date'] <= effective_ed)
                    ]
                    if not hist.empty:
                        for i, col in enumerate(['PE', 'PB', 'Div_Yield']):
                            ser = hist[col].dropna()
                            if not ser.empty:
                                img = create_matplotlib_gauge(
                                    ser.iloc[-1], ser.min(), ser.max(), ser.median(),
                                    reverse=(col == 'Div_Yield')
                                )
                                ws1.insert_image(
                                    row_idx, 1 + num_periods + i,
                                    f"s1_{row_idx}_{i}.png",
                                    {'image_data': img, 'x_scale': 0.7, 'y_scale': 0.7,
                                     'x_offset': 10, 'y_offset': 5}
                                )
            except Exception as gauge_err:
                logger.warning(f"Gauge render skipped for {idx}: {gauge_err}")
            row_idx += 1

        ws1.merge_range(
            22, 0, 24, 10,
            f"Source: niftyindices.com and ElevateWealth. period ending {effective_ed.date()}. All returns annualized except < 1yr.",
            italic_f
        )

        ws1.write(26, 0, "Ranking of Thematic/Sector Portfolios (Strict Universe)", workbook.add_format({'bold': True}))
        years = [str(y) for y in range(2016, effective_ed.year)] + [f"{effective_ed.year} (YTD)"]
        ws1.write_row(27, 0, ["Year"] + [f"Rank {i+1}" for i in range(6)], head_f)

        strict_s_universe = [k for k in SECTOR_RANK_MAP.keys() if k in DATA['rebased'].columns]

        for r, y_lab in enumerate(years):
            curr_r = 28 + r
            ws1.write(curr_r, 0, y_lab, head_f)
            if "YTD" in y_lab:
                rets = calc_cagr(DATA['rebased'], pd.Timestamp(f"{effective_ed.year}-01-01"), effective_ed, strict_s_universe, label="YTD")
            else:
                rets = DATA['yearly'].loc[y_lab, strict_s_universe] if y_lab in DATA['yearly'].index else pd.Series()
            top_6 = rets.sort_values(ascending=False).head(6)
            for i, (name, val) in enumerate(top_6.items()):
                ws1.write(curr_r, i + 1, f"{SECTOR_RANK_MAP.get(name, name)}\n({val:.1f}%)", rank_f)

        # ── SHEET 2: FACTOR DASHBOARD ────────────────────────────────────────────
        ws2 = workbook.add_worksheet("Factor Dashboard")
        ws2.set_column('A:A', 35)
        ws2.set_column('B:M', 12)

        ws2.merge_range('A1:K1', 'Factor Dashboard', title_f)
        ws2.merge_range(1, 1, 1, num_periods, 'Performance (%)', head_f)
        ws2.merge_range(1, 1 + num_periods, 1, 3 + num_periods, 'Risk Metrics (Since Inception)', head_f)
        ws2.write_row('A3', ["Factor Indices"] + request.periods + ["Volatility", "Risk-Adj", "Max DD"], head_f)

        row_idx = 3
        for idx in f_indices:
            ws2.write(row_idx, 0, idx, text_f)
            ws2.write_row(row_idx, 1, get_perf_row_data(idx, effective_ed, request.periods, bench), perc_f)
            try:
                incept  = DATA['rebased'][idx].dropna().index.min()
                v_val   = calc_vol(DATA['returns'], incept, effective_ed, [idx])[idx]
                m_val   = calc_mdd(DATA['rebased'], incept, effective_ed, [idx])[idx]
                c_val   = calc_cagr(DATA['rebased'], incept, effective_ed, [idx])[idx]
                ra_val  = clean_float(c_val / v_val) if v_val else 0
                ws2.write_row(row_idx, 1 + num_periods, [clean_float(v_val), ra_val, clean_float(m_val)], num_f)
            except Exception as factor_err:
                logger.warning(f"Factor row skipped for {idx}: {factor_err}")
            row_idx += 1

        row_idx += 2
        ws2.write(row_idx, 0, "Ranking of Factor Portfolios (Strict Universe)", workbook.add_format({'bold': True}))
        for i, rd in enumerate(FACTOR_RANKS_STATIC):
            ws2.write_row(row_idx + 1 + i, 0, rd, head_f if i == 0 else text_f)

        strict_f_universe = [k for k in FACTOR_RANK_MAP.keys() if k in DATA['rebased'].columns]
        y26_col = len(FACTOR_RANKS_STATIC[0])
        ws2.write(row_idx + 1, y26_col, f"{effective_ed.year} (YTD)", head_f)
        f_ytd = calc_cagr(
            DATA['rebased'], pd.Timestamp(f"{effective_ed.year}-01-01"),
            effective_ed, strict_f_universe, label="YTD"
        ).sort_values(ascending=False).head(6)
        for i, (name, val) in enumerate(f_ytd.items()):
            ws2.write(row_idx + 2 + i, y26_col, f"{FACTOR_RANK_MAP.get(name, name)}\n({val:.1f}%)", rank_f)

        # ── SHEET 3: INTERNATIONAL DASHBOARD ────────────────────────────────────
        ws3 = workbook.add_worksheet("International Dashboard")
        ws3.set_column('A:A', 35)
        ws3.set_column('B:B', 12)
        ws3.set_column('C:I', 14)

        ws3.merge_range('A1:I1', 'International Markets Dashboard', title_f)
        intl_headers = ["Asset/Index", "Currency", "MTD", "YTD", "1 Yr", "3 Yr", "5 Yr", "10 Yr", "Rolling 3Yr Average"]
        ws3.write_row('A2', intl_headers, head_f)

        fixed_periods = ["MTD", "YTD", "1 Yr", "3 Yr", "5 Yr", "10 Yr", "Rolling 3-Yr Avg"]
        row_idx = 2
        for item in INTL_REPORT_LIST:
            match = next((c for c in DATA['rebased'].columns if c.upper() in item.upper()), None)
            if match:
                ws3.write(row_idx, 0, item, text_f)
                ws3.write(row_idx, 1, INTL_CURRENCY_MAP.get(match, "USD"), text_f)
                ws3.write_row(row_idx, 2, get_perf_row_data(match, effective_ed, fixed_periods, bench), perc_f)
                row_idx += 1

        # ── SHEET 4: MUTUAL FUNDS (optional, DuckDB-backed) ─────────────────────
        if request.include_mf and 'mf_parquet_path' in DATA:
            try:
                snap_date = find_mf_snapshot_date(effective_ed)
                if snap_date is not None:
                    where_sql, params = build_mf_where_clause(
                        request.mf_search, request.mf_subcategories,
                        request.mf_riskometers, request.mf_benchmarks, snap_date,
                    )
                    select_cols = ", ".join(MF_SELECT_COLS)
                    df_mf = mf_query(
                        f"""
                        SELECT {select_cols}
                        FROM read_parquet(?)
                        WHERE {where_sql}
                        ORDER BY return1YearRegular DESC NULLS LAST
                        LIMIT 500
                        """,
                        [DATA['mf_parquet_path']] + params,
                    )

                    ws4 = workbook.add_worksheet("Mutual Funds")
                    ws4.set_column('A:A', 40)
                    ws4.set_column('B:B', 22)
                    ws4.set_column('C:F', 12)

                    ws4.merge_range('A1:F1', 'Mutual Fund Performance', title_f)
                    ws4.merge_range(
                        'A2:F2',
                        f"MF data as of {snap_date.strftime('%d %b %Y')} | Index data as of {effective_ed.strftime('%d %b %Y')}",
                        italic_f
                    )
                    ws4.write_row('A3', ["Scheme Name", "AMFI Benchmark", "NAV", "1 Yr", "3 Yr", "5 Yr", "10 Yr"], head_f)

                    def get_idx_ret(period):
                        try:
                            sd = get_start_date(period, effective_ed)
                            return calc_cagr(DATA['rebased'], sd, effective_ed, [bench], label=period)[bench]
                        except Exception:
                            return None

                    ws4.write(3, 0, f" BENCHMARK: {bench}", text_f)
                    ws4.write(3, 1, "-", text_f)
                    bench_vals = [None] + [clean_float(get_idx_ret(p)) for p in ["1 Yr", "3 Yr", "5 Yr", "10 Yr"]]
                    ws4.write_row(3, 2, bench_vals, num_f)

                    row_idx = 4
                    for _, r in df_mf.iterrows():
                        ws4.write(row_idx, 0, r.get('schemeName'), text_f)
                        ws4.write(row_idx, 1, r.get('benchmark'), text_f)
                        vals = [
                            clean_float(r.get('navRegular')),
                            clean_float(r.get('return1YearRegular')),
                            clean_float(r.get('return3YearRegular')),
                            clean_float(r.get('return5YearRegular')),
                            clean_float(r.get('return10YearRegular')),
                        ]
                        ws4.write_row(row_idx, 2, vals, num_f)
                        row_idx += 1
                else:
                    logger.warning("⚠️ No MF snapshot available for report date; skipping MF sheet.")
            except Exception as mf_sheet_err:
                logger.error(f"MF sheet generation failed, continuing without it: {mf_sheet_err}")

        workbook.close()
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=NSE_Advanced_Report.xlsx"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"REPORT ERROR: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS — mutual funds (fully DuckDB-backed, no pandas dataframe held in memory)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/mf-config")
def get_mf_config():
    require_data("mf_config")
    return DATA['mf_config']


@app.post("/api/mf-data")
def get_mf_data(request: MFDataRequest):
    require_data("mf_parquet_path", "mf_dates")

    effective_ed = get_effective_end_date(request.reference_date)
    snap_date = find_mf_snapshot_date(effective_ed)

    if snap_date is None:
        return {
            "rows": [], "comparison_row": None,
            "total": 0, "page": 1, "page_size": request.page_size,
            "snapshot_date": None,
        }

    parquet_path = DATA['mf_parquet_path']

    try:
        where_sql, params = build_mf_where_clause(
            request.search, request.subcategories, request.riskometers, request.benchmarks, snap_date,
        )

        total_df = mf_query(
            f"SELECT COUNT(*) AS n FROM read_parquet(?) WHERE {where_sql}",
            [parquet_path] + params,
        )
        total = int(total_df["n"].iloc[0])

        sort_col = request.sort_by if request.sort_by in ALLOWED_MF_SORT_COLS else "return1YearRegular"
        order_dir = "ASC" if request.sort_dir == "asc" else "DESC"

        page = max(request.page, 1)
        page_size = min(max(request.page_size, 1), 500)
        offset = (page - 1) * page_size

        select_cols = ", ".join(MF_SELECT_COLS)
        df_page = mf_query(
            f"""
            SELECT {select_cols}
            FROM read_parquet(?)
            WHERE {where_sql}
            ORDER BY {sort_col} {order_dir} NULLS LAST
            LIMIT ? OFFSET ?
            """,
            [parquet_path] + params + [page_size, offset],
        )
    except Exception as e:
        logger.error(f"MF query failed: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"MF query failed: {e}")

    df_page = df_page.replace([np.inf, -np.inf], np.nan)
    df_page = df_page.where(pd.notnull(df_page), None)
    rows = df_page.to_dict("records")

    comparison_row = None
    if request.compare_index and request.compare_index in DATA.get("rebased", pd.DataFrame()).columns:
        idx_name = request.compare_index

        def get_idx_ret(period):
            try:
                sd = get_start_date(period, effective_ed)
                val = calc_cagr(DATA["rebased"], sd, effective_ed, [idx_name], label=period)[idx_name]
                return clean_float(val)
            except Exception:
                return None

        comparison_row = {
            "schemeName": f" BENCHMARK: {idx_name}",
            "benchmark": "-",
            "riskometerScheme": "-",
            "navRegular": None,
            "return1YearRegular": get_idx_ret("1 Yr"),
            "return3YearRegular": get_idx_ret("3 Yr"),
            "return5YearRegular": get_idx_ret("5 Yr"),
            "return10YearRegular": get_idx_ret("10 Yr"),
            "is_benchmark": True,
        }

    return {
        "rows": rows,
        "comparison_row": comparison_row,
        "total": total,
        "page": page,
        "page_size": page_size,
        "snapshot_date": snap_date.strftime("%Y-%m-%d"),
    }
    
# ─────────────────────────────────────────────────────────────────────────────
# MF CATEGORY ANALYSIS (month-end NAV based)
# ─────────────────────────────────────────────────────────────────────────────

def _pct(v):
    return None if v is None or not np.isfinite(v) else round(float(v) * 100, 2)


def _num(v, nd=2):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


def _resolve_index(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    return next((c for c in DATA["rebased"].columns if c.strip().upper() == name.strip().upper()), None)


def _month_end_prices(cols, month_ends) -> pd.DataFrame:
    """Index levels at the same month-ends as the fund NAVs (last trading day <= month-end)."""
    reb = DATA["rebased"]
    cols = [c for c in cols if c in reb.columns]
    px = reb[cols].sort_index().reindex(month_ends, method="ffill")
    px.loc[px.index > reb.index.max()] = np.nan           # never fabricate months beyond index data
    return px


def compute_mf_analysis(fund_class, as_of, bench, extras, n_years=12, min_history_months=12,
                        rank_partial=False, rank_with_indices=True):
    wide, meta = DATA["mf_nav_wide"], DATA["mf_nav_meta"]
    eligible = wide.index[wide.index <= as_of]
    if len(eligible) == 0:
        return None
    t = eligible[-1]                                       # as-of month-end

    # ── funds of this class that are live at t and have enough history ──────
    codes = meta.index[meta["fund_class"] == fund_class]
    nav = wide.reindex(columns=codes).loc[:t]
    nav = nav.loc[:, nav.loc[t].notna()]
    if nav.shape[1] == 0:
        return None
    first_m = nav.notna().idxmax()
    hist = (t.year - first_m.dt.year) * 12 + (t.month - first_m.dt.month)
    nav = nav.loc[:, hist >= min_history_months]
    if nav.shape[1] == 0:
        return None
    nav.columns = nav.columns.astype(str)

    # ── append benchmark / peer indices as rows on the same month-end grid ──
    idx_names = [bench] + [e for e in extras if e != bench]
    px = _month_end_prices(idx_names, nav.index)
    px.columns = [f"IDX::{c}" for c in px.columns]
    allp = pd.concat([nav, px], axis=1)
    fund_cols = list(nav.columns)
    bkey = f"IDX::{bench}"

    has = allp.notna().any()
    first = allp.notna().idxmax()
    ye = allp[allp.index.month == 12].copy()
    ye.index = ye.index.year

    last_full = t.year if t.month == 12 else t.year - 1
    years = [last_full - i for i in range(n_years)]        # most recent first

    # ── calendar-year returns (+ part-year return in each fund's first year) ─
    cur = ye.reindex(years)
    prev = ye.reindex([y - 1 for y in years]); prev.index = years
    cal = (cur / prev - 1).replace([np.inf, -np.inf], np.nan)

    partial = pd.DataFrame(False, index=years, columns=allp.columns)
    for col in allp.columns[has.values]:
        f = first[col]; y0 = f.year
        if (y0 in cal.index and f.month < 12 and pd.isna(cal.at[y0, col])
                and y0 in ye.index and pd.notna(ye.at[y0, col])):
            cal.at[y0, col] = ye.at[y0, col] / allp.at[f, col] - 1
            partial.at[y0, col] = True

    # ── trailing CAGR as of t (true trailing, not calendar-compounded) ──────
    pos = len(allp) - 1
    def trailing(n):
        if pos - 12 * n < 0:
            return pd.Series(np.nan, index=allp.columns)
        return ((allp.iloc[pos] / allp.iloc[pos - 12 * n]) ** (1 / n) - 1).replace([np.inf, -np.inf], np.nan)
    trail = {n: trailing(n) for n in (10, 5, 3, 1)}

    # ── rolling 3Y CAGR for the window ending each calendar year ────────────
    num = ye.reindex(years).to_numpy(dtype=float)
    den = ye.reindex([y - 3 for y in years]).to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        roll3 = pd.DataFrame(np.power(num / den, 1 / 3) - 1, index=years, columns=allp.columns)
    roll3 = roll3.replace([np.inf, -np.inf], np.nan)
    roll3_avg = roll3.mean()

    # ── ranks (1 = best), average / median over 10-5-3 most recent years ────
    calr = cal if rank_partial else cal.where(~partial)
    rk_src = calr if rank_with_indices else calr[fund_cols]
    ranks = rk_src.rank(axis=1, ascending=False, method="min").reindex(columns=allp.columns)
    universe = rk_src.notna().sum(axis=1)

    def rank_stat(k, fn="mean"):
        sub = ranks.iloc[:k]
        return getattr(sub, fn)().where(sub.notna().sum() == k)       # need the full window
    avg10, med10, avg5, avg3 = rank_stat(10), rank_stat(10, "median"), rank_stat(5), rank_stat(3)

    # ── correlation of calendar-year returns vs benchmark ───────────────────
    if bkey in calr.columns:
        bs = calr[bkey]
        corr = calr.apply(lambda c: c.corr(bs, min_periods=5))
    else:
        corr = pd.Series(np.nan, index=allp.columns)

    # ── YTD for the current (incomplete) year ───────────────────────────────
    ytd_year = t.year if t.month != 12 else None
    ytd = None
    if ytd_year:
        base = ye.reindex([ytd_year - 1]).iloc[0]
        ytd = (allp.iloc[pos] / base - 1).replace([np.inf, -np.inf], np.nan)

    def build_row(col):
        is_idx = col.startswith("IDX::")
        if is_idx:
            nm, amc = col[5:], None
        else:
            m = meta.loc[int(col)]
            nm, amc = m["scheme_name"], m["amc"]
        return {
            "id": col, "name": nm, "amc": amc,
            "is_index": is_idx, "is_benchmark": col == bkey,
            "ret": {str(y): _pct(cal.at[y, col]) for y in years},
            "partial": [int(y) for y in years if partial.at[y, col]],
            "ytd": _pct(ytd[col]) if ytd is not None else None,
            "trail": {str(n): _pct(trail[n][col]) for n in trail},
            "roll3": {str(y): _pct(roll3.at[y, col]) for y in years},
            "roll3_avg": _pct(roll3_avg[col]),
            "corr": _num(corr[col]),
            "rank": {str(y): (int(ranks.at[y, col]) if pd.notna(ranks.at[y, col]) else None) for y in years},
            "avg_rank_10": _num(avg10[col], 1), "med_rank_10": _num(med10[col], 1),
            "avg_rank_5": _num(avg5[col], 1), "avg_rank_3": _num(avg3[col], 1),
        }

    idx_cols = [f"IDX::{c}" for c in idx_names if f"IDX::{c}" in allp.columns]
    fund_sorted = sorted(
        fund_cols,
        key=lambda c: (pd.isna(trail[5][c]), -(trail[5][c] if pd.notna(trail[5][c]) else 0.0)),
    )
    return {
        "as_of": t.strftime("%Y-%m-%d"),
        "years": years, "ytd_year": ytd_year, "benchmark": bench,
        "n_funds": len(fund_cols),
        "universe": {str(y): int(universe[y]) for y in years},
        "rows": [build_row(c) for c in idx_cols + fund_sorted],
    }


@app.get("/api/mf-analysis-config")
def mf_analysis_config():
    require_data("mf_nav_wide", "mf_nav_meta", "rebased")
    counts = DATA["mf_nav_meta"]["fund_class"].value_counts().to_dict()
    classes = []
    for cls, d in MF_CLASS_DEFAULTS.items():
        classes.append({
            "id": cls,
            "count": int(counts.get(cls, 0)),
            "benchmark": _resolve_index(d["benchmark"]),
            "extras": [x for x in (_resolve_index(e) for e in d["extras"]) if x],
        })
    wide = DATA["mf_nav_wide"]
    return {
        "classes": classes,
        "indices": DATA["indices"],
        "min_date": wide.index.min().strftime("%Y-%m-%d"),
        "max_date": wide.index.max().strftime("%Y-%m-%d"),
    }


@app.post("/api/mf-analysis")
def mf_analysis(req: MFAnalysisRequest):
    require_data("mf_nav_wide", "mf_nav_meta", "rebased")
    d = MF_CLASS_DEFAULTS.get(req.fund_class)
    if d is None:
        raise HTTPException(status_code=400, detail=f"Unknown fund_class '{req.fund_class}'")

    bench = _resolve_index(req.benchmark_index or d["benchmark"]) or _resolve_index("NIFTY 500")
    if bench is None:
        raise HTTPException(status_code=400, detail="Benchmark index not found in index data")
    raw_extras = d["extras"] if req.extra_indices is None else req.extra_indices
    extras = [x for x in (_resolve_index(e) for e in raw_extras) if x]

    try:
        out = compute_mf_analysis(
            req.fund_class, get_effective_end_date(req.reference_date), bench, extras,
            n_years=max(req.n_years, 10), min_history_months=max(req.min_history_months, 0),
            rank_partial=req.include_partial_in_rank, rank_with_indices=req.rank_with_indices,
        )
    except Exception as e:
        logger.error(f"MF analysis failed: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

    if out is None:
        return {"as_of": None, "years": [], "ytd_year": None, "benchmark": bench,
                "n_funds": 0, "universe": {}, "rows": []}
    return out



# ═════════════════════════════════════════════════════════════════════════════
# MF IMPLEMENTATION 2 — funds + indices on ONE month-end grid
# ═════════════════════════════════════════════════════════════════════════════

MF2_CLASS_ORDER = ["Large-Cap", "Mid-Cap", "Small-Cap", "Flexi-Cap & Multi-Cap", "Thematic", "ELSS", "International"]
MF2_ALL_PERIODS = [1, 3, 5, 10, 15, 20]


class MF2Request(BaseModel):
    fund_codes: List[int] = []
    indices: List[str] = []
    benchmark: str = "NIFTY 50"
    periods: List[int] = [1, 3, 5, 10, 15, 20]
    reference_date: Optional[str] = None
    min_months: int = 12            # NEW


class MF2ReportRequest(MF2Request):
    sheets: List[str] = ["returns", "calendar", "rolling", "vs_benchmark", "rankings"]
    roll_start_year: Optional[int] = None


def _m2_resolve(name):
    if not name:
        return None
    up = name.strip().upper()
    return next((c for c in DATA["rebased"].columns if str(c).strip().upper() == up), None)


def _m2_lst(x, nd=2):
    a = np.asarray(x, dtype=float)
    return [None if not np.isfinite(v) else round(float(v), nd) for v in a]


def _m2_int(x):
    a = np.asarray(x, dtype=float)
    return [None if not np.isfinite(v) else int(v) for v in a]

MF2_MAX_STALE_MONTHS = 1      # last real NAV may be at most this many months before the as-of month (0 = strict)
MF2_MIN_COVERAGE = 0.9        # share of months (first NAV -> as-of) that must have a real NAV


def mf2_asof(req_date):
    """Latest COMPLETE month-end <= reference date (that exists in the NAV grid)."""
    idx = DATA["mf_nav_wide"].index
    ed = get_effective_end_date(req_date)
    ok = idx[idx <= ed]
    return ok[-1] if len(ok) else None


def mf2_eligible(t, min_months=12) -> pd.Index:
    raw = DATA["mf_nav_raw"]
    upto = raw.loc[:t]
    if upto.empty:
        return raw.columns[:0]
    pres = upto.notna().to_numpy()
    last_i = len(upto) - 1
    n_obs = pres.sum(axis=0)
    first_i = pres.argmax(axis=0)                           # first real NAV (position)
    last_obs_i = last_i - pres[::-1].argmax(axis=0)         # last real NAV (position)
    span = last_i - first_i + 1
    ok = (
        (n_obs > 0)
        & (first_i <= last_i - max(min_months, 0))
        & (last_obs_i >= last_i - MF2_MAX_STALE_MONTHS)
        & (n_obs >= MF2_MIN_COVERAGE * span)
    )
    return raw.columns[ok]

def compute_mf2(req: MF2Request):
    wide, meta, reb = DATA["mf_nav_wide"], DATA["mf_nav_meta"], DATA["rebased"]

    t = mf2_asof(req.reference_date)
    if t is None:
        return None
    bench = _m2_resolve(req.benchmark) or _m2_resolve("NIFTY 50")
    if bench is None:
        raise HTTPException(status_code=400, detail="Benchmark index not found in index data")

    others = {_m2_resolve(n) for n in req.indices} - {None, bench}
    idx_names = [bench] + sorted(others)

    ok = set(mf2_eligible(t, req.min_months))               # authoritative filter, even if the UI sends stale codes
    codes = [c for c in dict.fromkeys(req.fund_codes) if c in ok]
    codes.sort(key=lambda c: str(meta.at[c, "scheme_name"]))

    periods = sorted({p for p in req.periods if p in MF2_ALL_PERIODS})
    
    
    # ── one monthly grid: oldest first-valid among selected items, at least 21y back ──
    firsts = [reb[c].first_valid_index() for c in idx_names] + [wide[c].first_valid_index() for c in codes]
    start = min([d for d in firsts if d is not None] + [t - pd.DateOffset(years=21)])
    grid = pd.period_range(start.to_period("M"), t.to_period("M"), freq="M").to_timestamp(how="end").normalize()

    fund_px = wide.reindex(columns=codes).reindex(grid)
    fund_px.columns = [f"F:{c}" for c in codes]
    idx_px = reb[idx_names].sort_index().reindex(grid, method="ffill")     # last trading day <= month-end
    idx_px.loc[idx_px.index > reb.index.max()] = np.nan
    idx_px.columns = [f"I:{c}" for c in idx_names]
    P = pd.concat([idx_px, fund_px], axis=1)

    keys, bkey = list(P.columns), f"I:{bench}"
    N, pos = len(keys), len(P) - 1

    items = []
    for k in keys:
        if k.startswith("I:"):
            items.append({"id": k, "name": k[2:], "kind": "index", "amc": None, "cls": None, "is_benchmark": k == bkey})
        else:
            m = meta.loc[int(k[2:])]
            items.append({"id": k, "name": str(m["scheme_name"]), "kind": "fund",
                          "amc": m["amc"] if pd.notna(m["amc"]) else None,
                          "cls": m["fund_class"], "is_benchmark": False})

    # ── trailing CAGR / excess / correlation / tracking error (monthly returns) ──
    R = P.pct_change(fill_method=None)
    cagr, excess, corr, te = {}, {}, {}, {}
    for n in periods:
        back, key = pos - 12 * n, str(n)
        if back < 0:
            cagr[key] = excess[key] = corr[key] = te[key] = [None] * N
            continue
        c = ((P.iloc[pos] / P.iloc[back]) ** (1.0 / n) - 1).replace([np.inf, -np.inf], np.nan) * 100
        W = R.iloc[back + 1: pos + 1]
        bw = W[bkey]
        valid = (W.notna().to_numpy() & bw.notna().to_numpy()[:, None]).sum(axis=0)
        ok = P.iloc[back].notna().to_numpy() & (valid >= 0.9 * 12 * n)     # item must span the whole window
        cr = W.corrwith(bw).to_numpy(dtype=float)
        tr = (W.sub(bw, axis=0).std(ddof=1) * np.sqrt(12) * 100).to_numpy(dtype=float)
        cagr[key] = _m2_lst(c)
        excess[key] = _m2_lst(c - c[bkey])
        corr[key] = _m2_lst(np.where(ok, cr, np.nan))
        te[key] = _m2_lst(np.where(ok, tr, np.nan))

    # ── calendar-year returns (full Dec→Dec years only) ──
    dec = P[P.index.month == 12].copy()
    dec.index = dec.index.year
    L = t.year if t.month == 12 else t.year - 1
    y0 = P.index.min().year
    cal_years = list(range(y0 + 1, L + 1))
    CAL = pd.DataFrame(index=cal_years, columns=keys, dtype=float)
    if cal_years:
        cur = dec.reindex(cal_years)
        prev = dec.reindex([y - 1 for y in cal_years]); prev.index = cal_years
        CAL = ((cur / prev) - 1).replace([np.inf, -np.inf], np.nan) * 100
    n_valid = CAL.notna().sum(axis=1)
    years = [y for y in cal_years if n_valid[y] > 0]

    ytd_year, ytd = (t.year if t.month != 12 else None), None
    if ytd_year:
        base = dec.reindex([ytd_year - 1]).iloc[0]
        ytd = (P.iloc[pos] / base - 1).replace([np.inf, -np.inf], np.nan) * 100

    # ── rolling 3Y (window ending each Dec) ──
    roll_all = list(range(y0 + 3, L + 1))
    ROLL = pd.DataFrame(index=roll_all, columns=keys, dtype=float)
    if roll_all:
        num = dec.reindex(roll_all)
        den = dec.reindex([y - 3 for y in roll_all]); den.index = roll_all
        ROLL = (((num / den) ** (1.0 / 3)) - 1).replace([np.inf, -np.inf], np.nan) * 100
    roll_years = [y for y in roll_all if ROLL.loc[y].notna().any()]

    # ── ranks (1 = best) among everything selected, + median / avg(10,5,3) ──
    rank, universe, median_rank, avg_rank = {}, {}, [None] * N, {"10": [None] * N, "5": [None] * N, "3": [None] * N}
    if years:
        CALy = CAL.loc[years]
        RK = CALy.rank(axis=1, ascending=False, method="min")
        universe = {str(y): int(CALy.loc[y].notna().sum()) for y in years}
        rank = {str(y): _m2_int(RK.loc[y]) for y in years}
        median_rank = _m2_lst(RK.median().where(RK.notna().sum() >= 3), 1)
        for k in (10, 5, 3):
            sub = RK.reindex(list(range(L, L - k, -1)))
            full = sub.notna().sum() == k                      # need the complete window
            avg_rank[str(k)] = _m2_int(np.floor(sub.mean().where(full) + 0.5))

    yd = sorted(years, reverse=True)
    return {
        "as_of": t.strftime("%Y-%m-%d"), "benchmark": bench, "periods": periods, "items": items,
        "cagr": cagr, "excess": excess, "corr": corr, "te": te,
        "years": yd, "n_valid": {str(y): int(n_valid[y]) for y in yd},
        "cal": {str(y): _m2_lst(CAL.loc[y]) for y in yd},
        "ytd_year": ytd_year, "ytd": _m2_lst(ytd) if ytd is not None else None,
        "roll_years": sorted(roll_years, reverse=True),
        "roll3": {str(y): _m2_lst(ROLL.loc[y]) for y in roll_years},
        "rank": {str(y): rank[str(y)] for y in yd} if years else {},
        "universe": universe, "median_rank": median_rank, "avg_rank": avg_rank,
    }


@app.get("/api/mf2/config")
def mf2_config(reference_date: Optional[str] = None, min_months: int = 12):
    require_data("mf_nav_wide", "mf_nav_meta", "rebased")
    meta, wide = DATA["mf_nav_meta"], DATA["mf_nav_wide"]

    t = mf2_asof(reference_date)
    ok = set(mf2_eligible(t, min_months)) if t is not None else set()

    m = meta.reset_index().sort_values("scheme_name")
    m = m[m["fund_class"].isin(MF2_CLASS_ORDER)]
    elig = m[m["scheme_code"].isin(ok)]
    counts = elig["fund_class"].value_counts().to_dict()

    return {
        "classes": [{"id": c, "count": int(counts.get(c, 0))} for c in MF2_CLASS_ORDER],
        "funds": [
            {"c": int(r.scheme_code), "n": str(r.scheme_name), "a": r.amc if pd.notna(r.amc) else None, "k": r.fund_class}
            for r in elig.itertuples(index=False)
        ],
        "hidden": int(len(m) - len(elig)),
        "as_of": t.strftime("%Y-%m-%d") if t is not None else None,
        "indices": DATA["indices"],
        "min_date": wide.index.min().strftime("%Y-%m-%d"),
        "max_date": wide.index.max().strftime("%Y-%m-%d"),
    }
    

@app.post("/api/mf2/analysis")
def mf2_analysis(req: MF2Request):
    require_data("mf_nav_wide", "mf_nav_meta", "rebased")
    try:
        with np.errstate(all="ignore"):
            res = compute_mf2(req)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MF2 analysis failed: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    if res is None:
        raise HTTPException(status_code=404, detail="No mutual fund data on or before the reference date")
    return res


@app.post("/api/mf2/report")
def mf2_report(req: MF2ReportRequest):
    require_data("mf_nav_wide", "mf_nav_meta", "rebased")
    with np.errstate(all="ignore"):
        res = compute_mf2(req)
    if res is None:
        raise HTTPException(status_code=404, detail="No mutual fund data on or before that date")

    items, periods, years, N = res["items"], res["periods"], res["years"], len(res["items"])
    show_years = [y for y in years if res["n_valid"][str(y)] >= max(1, 0.5 * N)]   # same default as the UI
    out = io.BytesIO()
    wb = xlsxwriter.Workbook(out, {"in_memory": True, "nan_inf_to_errors": True})

    base = {"font_size": 9, "border": 1, "valign": "vcenter"}
    f_title = wb.add_format({"bold": True, "font_color": "white", "bg_color": "black", "align": "center", "valign": "vcenter", "border": 1, "font_size": 12})
    f_note = wb.add_format({"italic": True, "font_size": 8})
    f_head = wb.add_format({**base, "bold": True, "bg_color": "#F2F2F2", "align": "center", "text_wrap": True})
    f_text = wb.add_format({**base, "align": "left"})
    f_pct = wb.add_format({**base, "align": "center", "num_format": '0.0"%"'})
    f_dec = wb.add_format({**base, "align": "center", "num_format": "0.00"})
    f_flt = wb.add_format({**base, "align": "center", "num_format": "0.0"})
    f_int = wb.add_format({**base, "align": "center", "num_format": "0"})
    foot = f"Month-end NAV basis · Regular plan, Growth option · as of {res['as_of']} · Benchmark: {res['benchmark']}"
    HEAT = {"type": "3_color_scale", "min_color": "#F8696B", "mid_type": "num", "mid_value": 0, "mid_color": "#FFFFFF", "max_color": "#63BE7B"}
    RANKHEAT = {"type": "3_color_scale", "min_color": "#63BE7B", "mid_color": "#FFEB84", "max_color": "#F8696B"}

    def lead(it):
        return [("[Benchmark] " if it["is_benchmark"] else "") + it["name"], "Index" if it["kind"] == "index" else "Fund", it["cls"] or ""]

    def make(name, headers, rows, fmts):
        ws = wb.add_worksheet(name)
        last = len(headers) - 1
        ws.merge_range(0, 0, 0, last, name, f_title)
        ws.merge_range(1, 0, 1, last, foot, f_note)
        ws.write_row(2, 0, headers, f_head)
        ws.set_row(2, 30)
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                ws.write(3 + i, j, v, fmts[j])
        ws.set_column(0, 0, 48); ws.set_column(1, 1, 8); ws.set_column(2, 2, 22); ws.set_column(3, last, 11)
        ws.freeze_panes(3, 1)
        return ws

    L3 = [f_text, f_text, f_text]
    P_ = len(periods)

    if "returns" in req.sheets:
        rows = [lead(it) + [res["cagr"][str(n)][i] for n in periods] for i, it in enumerate(items)]
        ws = make("Returns (CAGR)", ["Fund / Index", "Type", "Category"] + [f"{n} Yr" for n in periods], rows, L3 + [f_pct] * P_)
        if rows: ws.conditional_format(3, 3, 2 + len(rows), 2 + P_, HEAT)

    if "calendar" in req.sheets:
        ytd = res["ytd_year"]
        headers = ["Fund / Index", "Type", "Category"] + [str(y) for y in show_years] + ([f"{ytd} YTD"] if ytd else [])
        rows = [lead(it) + [res["cal"][str(y)][i] for y in show_years] + ([res["ytd"][i]] if ytd else []) for i, it in enumerate(items)]
        ws = make("Calendar Returns", headers, rows, L3 + [f_pct] * (len(headers) - 3))
        if rows and len(headers) > 3: ws.conditional_format(3, 3, 2 + len(rows), len(headers) - 1, HEAT)

    if "rolling" in req.sheets:
        S = req.roll_start_year
        ends = [y for y in res["roll_years"] if S is None or y >= S + 2]
        headers = ["Fund / Index", "Type", "Category", "Average"] + [str(y) for y in ends]
        vals = [[res["roll3"][str(y)][i] for y in ends] for i in range(N)]
        rows = [lead(it) + [None] + vals[i] for i, it in enumerate(items)]
        ws = make("3Y Rolling", headers, rows, L3 + [f_pct] * (len(headers) - 3))
        for i, v in enumerate(vals):
            have = [x for x in v if x is not None]
            if ends:
                rng = f"{xl_rowcol_to_cell(3 + i, 4)}:{xl_rowcol_to_cell(3 + i, 3 + len(ends))}"
                ws.write_formula(3 + i, 3, f'=IFERROR(AVERAGE({rng}),"")', f_pct, round(sum(have) / len(have), 2) if have else "")
        if rows and len(headers) > 3: ws.conditional_format(3, 3, 2 + len(rows), len(headers) - 1, HEAT)

    if "vs_benchmark" in req.sheets:
        headers = (["Fund / Index", "Type", "Category"]
                   + [f"Excess CAGR {n}Y (%)" for n in periods] + [f"Correlation {n}Y" for n in periods]
                   + [f"Tracking Error {n}Y (%)" for n in periods])
        rows = [lead(it) + [res["excess"][str(n)][i] for n in periods] + [res["corr"][str(n)][i] for n in periods]
                + [res["te"][str(n)][i] for n in periods] for i, it in enumerate(items)]
        ws = make("Vs Benchmark", headers, rows, L3 + [f_pct] * P_ + [f_dec] * P_ + [f_dec] * P_)
        if rows: ws.conditional_format(3, 3, 2 + len(rows), 2 + P_, HEAT)

    if "rankings" in req.sheets:
        order = sorted(range(N), key=lambda i: (not items[i]["is_benchmark"], res["median_rank"][i] is None, res["median_rank"][i] or 0))
        headers = ["Fund / Index", "Type", "Category", "Median Rank", "Avg Rank 10Y", "Avg Rank 5Y", "Avg Rank 3Y"] + [str(y) for y in show_years]
        rows = [lead(items[i]) + [res["median_rank"][i], res["avg_rank"]["10"][i], res["avg_rank"]["5"][i], res["avg_rank"]["3"][i]]
                + [res["rank"][str(y)][i] for y in show_years] for i in order]
        ws = make("Rankings", headers, rows, L3 + [f_flt, f_int, f_int, f_int] + [f_int] * len(show_years))
        if rows and show_years: ws.conditional_format(3, 7, 2 + len(rows), len(headers) - 1, RANKHEAT)

    wb.close()
    out.seek(0)
    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=MF_Analysis_{res['as_of']}.xlsx"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))