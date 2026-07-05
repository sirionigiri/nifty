"""
NSE Screener Backend — FastAPI
Endpoints: /api/config, /api/summary, /api/metrics, /api/valuation-data,
           /api/nav-data, /api/scatter-data, /api/calendar-returns,
           /api/rankings, /api/generate-report
"""

# ── Standard Library ──────────────────────────────────────────────────────────
import io
import logging
import os
import time

# ── Third-Party ───────────────────────────────────────────────────────────────
import httpx
import numpy as np
import pandas as pd
import xlsxwriter
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from typing import List, Optional
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe

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

URL_INTL = "https://raw.githubusercontent.com/sirionigiri/nse-screener-data/main/data/international_data.parquet"

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# APP & MIDDLEWARE
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(default_response_class=ORJSONResponse)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production replace "*" with your Vercel URL
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


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

URL_RETURNS = "https://raw.githubusercontent.com/sirionigiri/nse-screener-data/main/nifty_data.parquet"
URL_VALUATION = "https://raw.githubusercontent.com/sirionigiri/nse-screener-data/main/valuation_data.parquet"

# In-memory data store populated at startup
DATA = {}

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
    1: {"name": "Equity", "subs": {1: "Large Cap", 2: "Large & Mid Cap", 3: "Flexicap", 4: "Multi Cap", 5: "Mid Cap", 6: "Small Cap", 7: "Value", 8: "ELSS", 9: "Contra", 10: "Dividend Yield", 11: "Focused", 12: "Quant/Passive"}},
    2: {"name": "Debt", "subs": {13: "Long Duration", 14: "Income", 15: "Short Term", 16: "Medium Term", 17: "Money Market", 18: "Low Duration", 19: "Ultra Short Duration", 20: "Liquid", 21: "Overnight", 22: "Dynamic Bond", 23: "Corporate Bond", 24: "Credit Risk", 25: "Banking & PSU", 26: "Floater", 28: "Gilt", 29: "Gilt 10yr Constant Duration"}},
    3: {"name": "Hybrid", "subs": {30: "Aggressive Hybrid", 31: "Conservative Hybrid", 32: "Equity Savings", 33: "Arbitrage", 34: "Multi Asset Allocation", 35: "Balanced Advantage"}},
    4: {"name": "Solution Oriented", "subs": {36: "Children's Fund", 37: "Retirement Fund"}},
    5: {"name": "Other", "subs": {38: "Index/Passive", 39: "Gold/Silver ETF FOF"}}
}


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST MODEL
# ─────────────────────────────────────────────────────────────────────────────

class MetricsRequest(BaseModel):
    metric: str
    periods: List[str]
    indices: List[str]
    benchmark: str
    reference_date: Optional[str] = None
    include_mf: Optional[bool] = False   # NEW

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
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def get_perf_row_data(idx, ed, periods, benchmark):
    """Gathers performance data for a single index across multiple periods."""
    results = []
    for p in periods:
        try:
            if p == "Rolling 3-Yr Avg":
                # Uses the pre-imported calc_rolling3_metric
                val = calc_rolling3_metric(DATA['rebased'], DATA['returns'], 'cagr', [idx], benchmark, ed)[idx]
            else:
                sd = get_start_date(p, ed)
                # Handle start dates for Absolute vs CAGR periods
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


# ─────────────────────────────────────────────────────────────────────────────
# STARTUP — load data into memory
# ─────────────────────────────────────────────────────────────────────────────
import bisect

def get_mf_snapshot(effective_ed: pd.Timestamp):
    """Return (df_snapshot, actual_snapshot_date) for the most recent
    available MF data on or before effective_ed."""
    dates = DATA.get('mf_dates')
    if not dates:
        return None, None
    idx = bisect.bisect_right(dates, effective_ed) - 1
    if idx < 0:
        return None, None
    snap_date = dates[idx]
    return DATA['mf_by_date'][snap_date], snap_date


@app.on_event("startup")
async def startup_event():
    async with httpx.AsyncClient() as client:
        try:
            # 1. Load NIFTY Returns (Long format: Date, Index_Name, Total_Returns_Index)
            logger.info("📡 Loading NIFTY Data...")
            res1 = await client.get(URL_RETURNS, timeout=60)
            df_nifty_raw = pd.read_parquet(io.BytesIO(res1.content))

            # Ensure Nifty Date is datetime and handle whitespace
            df_nifty_raw['Date'] = pd.to_datetime(df_nifty_raw['Date'])
            df_nifty_raw.columns = [c.strip() for c in df_nifty_raw.columns]

            # Use your existing prep engine to get the "Wide" rebased Nifty dataframe
            prep = load_and_prepare(df_nifty_raw)
            nifty_wide = prep['rebased']  # This has Date as Index

            # 2. Load International Data (Wide format: Date is Index)
            logger.info("📡 Loading International Data...")
            res_intl = await client.get(URL_INTL, timeout=60)
            if res_intl.status_code == 200:
                df_intl_raw = pd.read_parquet(io.BytesIO(res_intl.content))

                # If 'Ticker' is a level name (multi-index), flatten it
                if isinstance(df_intl_raw.columns, pd.MultiIndex):
                    df_intl_raw.columns = df_intl_raw.columns.get_level_values(-1)

                # Ensure the index (Date) is datetime
                df_intl_raw.index = pd.to_datetime(df_intl_raw.index)
                df_intl_raw.index.name = 'Date'

                # Rebase International Indices to 100 at their own inception
                df_intl_rebased = df_intl_raw.apply(
                    lambda col: col / col.dropna().iloc[0] * 100 if col.dropna().size > 0 else col
                )

                # 3. MERGE Nifty Wide + International Wide
                combined_wide = pd.concat([nifty_wide, df_intl_rebased], axis=1).sort_index()
                combined_wide = combined_wide.loc[:, ~combined_wide.columns.duplicated()].copy()

                # Fill weekend/holiday gaps so indices are comparable on any given day
                combined_wide = combined_wide.ffill()

                logger.info("✅ Data merged successfully.")
            else:
                combined_wide = nifty_wide
                logger.warning("⚠️ Intl data fetch failed. Using Nifty only.")

            # 4. Finalize global store (index/returns engine)
            DATA['rebased'] = combined_wide
            DATA['returns'] = (combined_wide.pct_change(fill_method=None).ffill() * 100).round(4)
            DATA['yearly'] = _calc_yearly(combined_wide)
            DATA['end_date'] = combined_wide.index.max()
            DATA['indices'] = sorted(combined_wide.columns.tolist())

            # 5. Load Mutual Fund Data — isolated so a failure here can't take down the rest
            logger.info("📡 Loading Mutual Fund Data...")
            try:
                mf_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "amfi_fund_performance_daily_.parquet"
                )
                mf_raw = pd.read_parquet(mf_path)

                # Normalize the date column used for snapshotting
                mf_raw['_date'] = pd.to_datetime(mf_raw['_date'])

                # Pre-split into one DataFrame per available snapshot date.
                # Each group is already "1 row per scheme" for that date.
                DATA['mf_by_date'] = {
                    date: g.reset_index(drop=True)
                    for date, g in mf_raw.groupby('_date')
                }
                DATA['mf_dates'] = sorted(DATA['mf_by_date'].keys())

                # Keep a reference table (any single date, e.g. latest) for building
                # filter options like riskometer/benchmark/category lists.
                DATA['mf_reference'] = DATA['mf_by_date'][DATA['mf_dates'][-1]]

                logger.info(
                    f"✅ Mutual Fund data loaded: {len(DATA['mf_dates'])} snapshot dates, "
                    f"{len(DATA['mf_reference'])} schemes on latest date."
                )
            except Exception as mf_err:
                logger.error(f"⚠️ Mutual Fund load failed (MF tab will be unavailable): {mf_err}")

            # 6. Load Valuations
            logger.info("📡 Loading Valuation Data...")
            res2 = await client.get(URL_VALUATION, timeout=60)
            if res2.status_code == 200:
                df_v = pd.read_parquet(io.BytesIO(res2.content))
                # Ensure Valuation Date is also clean
                if 'Date' not in df_v.columns and df_v.index.name == 'Date':
                    df_v = df_v.reset_index()
                df_v['Date'] = pd.to_datetime(df_v['Date'])
                df_v['Index_Name'] = df_v['Index_Name'].astype(str).str.strip()
                DATA["valuation"] = df_v

            logger.info(f"🚀 ENGINE READY: {len(DATA['indices'])} Assets Loaded.")

        except Exception as e:
            import traceback
            logger.error(f"❌ Startup Failure: {e}")
            logger.error(traceback.format_exc())


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS — read-only / config
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    if "indices" not in DATA: raise HTTPException(503)
    return {"indices": DATA["indices"], "categories": CATEGORY_MAP}


@app.get("/api/calendar-returns")
def get_calendar_returns():
    if "yearly" not in DATA:
        raise HTTPException(status_code=503)
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
    if "rebased" not in DATA:
        return {"error": "Data not loaded"}
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
    if "rebased" not in DATA:
        raise HTTPException(status_code=503)
    try:
        effective_ed = get_effective_end_date(request.reference_date)

        all_cols = DATA["rebased"].columns.tolist()
        req_indices = [idx.strip().upper() for idx in request.indices]
        valid_indices = [c for c in all_cols if c.strip().upper() in req_indices]
        
        # Robust benchmark matching
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

        # 1. RUN CALCULATIONS
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

        # 2. BUILD DYNAMIC DATE RANGE LABELS (Metadata)
        ed_str = effective_ed.strftime("%d %b %y")
        date_ranges = {}
        for p in df_res.index:
            if p == "Rolling 3-Yr Avg":
                yr = effective_ed.year - 1
                date_ranges[p] = f"Jan {yr - 2} - Dec {yr}"
            else:
                target_sd = get_start_date(p, effective_ed)
                
                # FIX: Check what date was actually used for the anchor (Benchmark)
                # This unpacks the (Value, Date) tuple from our new _get_last
                _, actual_sd = _get_last(DATA["rebased"][bench_match], target_sd)
                
                # Determine what to show in the UI label
                if p == "MTD":
                    sd_show = pd.Timestamp(f"{effective_ed.year}-{effective_ed.month:02d}-01")
                elif p == "YTD":
                    sd_show = pd.Timestamp(f"{effective_ed.year}-01-01")
                else:
                    # If actual_sd is inception (newer than target), show inception date
                    sd_show = actual_sd if actual_sd else target_sd
                
                date_ranges[p] = f"{sd_show.strftime('%d %b %y')} - {ed_str}"

        # 3. FORMAT FINAL RESPONSE
        df_res = df_res.reset_index().rename(columns={"index": "Period"})
        df_res["Range"] = df_res["Period"].map(date_ranges)

        return {
            "data": df_res.replace({np.nan: None, np.inf: None, -np.inf: None}).to_dict("records"),
            "error": None,
        }
    except Exception as e:
        import traceback
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
    s = s.mask((s < lo) | (s > hi))   # garbage -> NaN, so ffill can replace it
    s = s.ffill()
    return s
@app.post("/api/valuation-data")
def get_val_data(request: MetricsRequest):
    if 'valuation' not in DATA: raise HTTPException(503)
    try:
        effective_ed = get_effective_end_date(request.reference_date)
        df_full = DATA['valuation']

        # 1. Filter for Target Index
        df = df_full[df_full['Index_Name'].str.upper() == request.benchmark.upper()].sort_values('Date').copy()
        if df.empty: return {"error": f"No data for {request.benchmark}"}

        # 2. Clean on the FULL history first (garbage -> NaN -> ffill),
        #    so the window's leading rows have something valid to inherit from.
        for col, bounds in VALUATION_BOUNDS.items():
            if col in df.columns:
                df[col] = clean_valuation_column(df[col], bounds)

        # 3. Slice the Window
        period = request.periods[0] if request.periods else "5 Yr"
        sd = get_start_date(period, effective_ed)
        df_w = df[(df['Date'] >= sd) & (df['Date'] <= effective_ed)].copy()

        if df_w.empty: return {"error": "Insufficient data in selected window"}

        # 4. STATS HELPER (unchanged — now works on cleaned data)
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
    except Exception as e:
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/nav-data")
def get_nav_data(request: MetricsRequest):
    if "rebased" not in DATA:
        raise HTTPException(status_code=503)

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
        # Rebase each series to 100 at its first available point in the window
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
    if "rebased" not in DATA:
        return []

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
        if 'yearly' not in DATA:
            raise HTTPException(status_code=503)

        # 1. Extreme Name Matching
        all_cols = DATA['yearly'].columns.tolist()
        # Clean names (remove hidden spaces) for matching
        selected = [s.strip() for s in request.indices]
        available_cols = [c for c in all_cols if c.strip() in selected]
        
        if not available_cols:
            return []

        # 2. Slice and calculate ranks
        # method='min' handles ties better for rankings
        df_selected = DATA['yearly'][available_cols].copy()
        rank_df = df_selected.rank(axis=1, ascending=False, method='min')

        results = []
        for year, row in rank_df.iterrows():
            # Standardize the year label
            y_label = str(year).split('-')[0] # Get just "2007" if it's a timestamp
            item = {"Year": y_label}
            
            # Map the ranks found in this row
            valid_row = False
            for idx_name, rank_val in row.items():
                if not np.isnan(rank_val):
                    item[f"Rank {int(rank_val)}"] = idx_name
                    valid_row = True
            
            # Only add the year if there is at least one rank found
            if valid_row:
                results.append(item)

        return results
    except Exception as e:
        print(f"Rankings Error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — Excel report generation
# ─────────────────────────────────────────────────────────────────────────────
def create_matplotlib_gauge(current, min_val, max_val, median_val, reverse=False):
    """Creates a linear gauge with a black pointer and blue median line."""

    try:
        # Normalize positions (0 to 1)
        pos = (current - min_val) / (max_val - min_val) if max_val != min_val else 0.5
        pos_med = (median_val - min_val) / (max_val - min_val) if max_val != min_val else 0.5

        pos = max(0, min(1, pos))
        pos_med = max(0, min(1, pos_med))
    except Exception:
        pos, pos_med = 0.5, 0.5

    fig, ax = plt.subplots(figsize=(4, 0.8))

    # Gradient bar
    cmap = "RdYlGn_r" if not reverse else "RdYlGn"
    cmap_obj = plt.get_cmap(cmap)

    gradient = np.linspace(0, 1, 256).reshape(1, -1)
    ax.imshow(
        gradient,
        aspect="auto",
        extent=[0, 1, 0, 0.25],
        cmap=cmap_obj,
    )

    # Median line
    ax.plot(
        [pos_med, pos_med],
        [0, 0.25],
        color="#2563eb",
        linewidth=2.5,
        zorder=11,
    )

    # Current value pointer
    ax.scatter(
        pos,
        0.35,
        marker="v",
        s=200,
        color="black",
        zorder=12,
    )

    txt_style = {
        "fontsize": 9,
        "fontweight": "bold",
        "family": "sans-serif",
    }

    # Min / Max labels
    ax.text(
        0,
        0.5,
        f"{min_val:.1f}",
        ha="left",
        color="#64748b",
        **txt_style,
    )

    ax.text(
        1,
        0.5,
        f"{max_val:.1f}",
        ha="right",
        color="#64748b",
        **txt_style,
    )

    # Determine background brightness at current position
    bg_rgb = cmap_obj(pos)[:3]
    luminance = (
        0.2126 * bg_rgb[0]
        + 0.7152 * bg_rgb[1]
        + 0.0722 * bg_rgb[2]
    )

    text_color = "black" if luminance > 0.55 else "white"
    outline_color = "white" if text_color == "black" else "black"

    # Current value label
    current_text = ax.text(
        pos,
        0.1,
        f"{current:.1f}",
        ha="center",
        va="center",
        color=text_color,
        zorder=20,
        **txt_style,
    )

    current_text.set_path_effects([
        pe.withStroke(
            linewidth=2,
            foreground=outline_color,
        )
    ])

    # Median label
    med_text = ax.text(
        pos_med,
        0.45,
        "MED",
        ha="center",
        color="#2563eb",
        fontsize=7,
        fontweight="black",
        zorder=20,
    )

    med_text.set_path_effects([
        pe.withStroke(
            linewidth=1.5,
            foreground="white",
        )
    ])

    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.1, 0.7)
    ax.axis("off")

    buf = io.BytesIO()

    plt.savefig(
        buf,
        format="png",
        bbox_inches="tight",
        pad_inches=0.02,
        transparent=True,
        dpi=120,
    )

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



@app.post("/api/generate-report")
async def generate_report(request: MetricsRequest):
    if "rebased" not in DATA:
        raise HTTPException(status_code=503, detail="Server data not loaded")

    try:
        effective_ed = get_effective_end_date(request.reference_date)
        five_yrs_ago = effective_ed - pd.DateOffset(years=5)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # --- FORMATS ---
        title_f = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': 'black', 'align': 'center', 'valign': 'vcenter', 'border': 1, 'font_size': 12})
        head_f  = workbook.add_format({'bold': True, 'bg_color': '#F2F2F2', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        text_f  = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter', 'font_size': 9})
        perc_f  = workbook.add_format({'num_format': '0.0"%"', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        num_f   = workbook.add_format({'num_format': '0.0', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        rank_f  = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 8, 'text_wrap': True})
        italic_f = workbook.add_format({'italic': True, 'font_size': 8, 'text_wrap': True})

        # --- CATEGORIZE INDICES ---
        factor_list = list(FACTOR_RANK_MAP.keys())
        s_indices = [idx for idx in request.indices if idx not in factor_list]
        f_indices = [idx for idx in request.indices if idx in factor_list]

        # Bench fallback + ensure it leads both lists
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
        ws1.merge_range(1, 1, 1, num_periods,             'Performance (%)',            head_f)
        ws1.merge_range(1, 1 + num_periods, 1, 3 + num_periods, 'Valuations (5Y Linear Gauge)', head_f)
        ws1.write_row('A3', ["Indices"] + request.periods + ["P/E", "P/B", "DY"], head_f)

        row_idx = 3
        for idx in s_indices[:19]:
            ws1.set_row(row_idx, 45)
            ws1.write(row_idx, 0, idx, text_f)
            ws1.write_row(row_idx, 1, get_perf_row_data(idx, effective_ed, request.periods, bench), perc_f)
            try:
                v_df = DATA['valuation']
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
            except:
                pass
            row_idx += 1

        ws1.merge_range(
            22, 0, 24, 10,
            f"Source: niftyindices.com and ElevateWealth. period ending {effective_ed.date()}. All returns annualized except < 1yr.",
            italic_f
        )

        # Sector Rankings Matrix
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
        ws2.merge_range(1, 1, 1, num_periods,             'Performance (%)',                head_f)
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
            except:
                pass
            row_idx += 1

        # Factor Rankings Matrix
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

        if request.include_mf and 'mf_by_date' in DATA:
            df_mf, mf_snap_date = get_mf_snapshot(effective_ed)

            if df_mf is not None:
                df_mf = df_mf.copy()

                if request.mf_search:
                    df_mf = df_mf[df_mf['schemeName'].str.contains(request.mf_search, case=False, na=False)]
                if request.mf_subcategories:
                    df_mf = df_mf[df_mf['_subCategory'].isin(request.mf_subcategories)]
                if request.mf_riskometers:
                    df_mf = df_mf[df_mf['riskometerScheme'].isin(request.mf_riskometers)]
                if request.mf_benchmarks:
                    df_mf = df_mf[df_mf['benchmark'].isin(request.mf_benchmarks)]

                df_mf = df_mf.sort_values('return1YearRegular', ascending=False, na_position='last')

                ws4 = workbook.add_worksheet("Mutual Funds")
                ws4.set_column('A:A', 40)
                ws4.set_column('B:B', 22)
                ws4.set_column('C:F', 12)

                ws4.merge_range('A1:F1', 'Mutual Fund Performance', title_f)
                ws4.merge_range(
                    'A2:F2',
                    f"MF data as of {mf_snap_date.strftime('%d %b %Y')} | Index data as of {effective_ed.strftime('%d %b %Y')}",
                    italic_f
                )
                ws4.write_row('A3', ["Scheme Name", "AMFI Benchmark", "NAV", "1 Yr", "3 Yr", "5 Yr", "10 Yr"], head_f)

                # Comparison row for the selected index benchmark
                def get_idx_ret(period):
                    try:
                        sd = get_start_date(period, effective_ed)
                        return calc_cagr(DATA['rebased'], sd, effective_ed, [bench], label=period)[bench]
                    except Exception:
                        return None

                ws4.write(3, 0, f"⭐ BENCHMARK: {bench}", text_f)
                ws4.write(3, 1, "-", text_f)
                bench_vals = [None] + [clean_float(get_idx_ret(p)) for p in ["1 Yr", "3 Yr", "5 Yr", "10 Yr"]]
                ws4.write_row(3, 2, bench_vals, num_f)

                row_idx = 4
                for _, r in df_mf.head(500).iterrows():
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
                
        workbook.close()
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=NSE_Advanced_Report.xlsx"}
        )

    except Exception as e:
        import traceback
        logger.error(f"REPORT ERROR: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mf-config")
def get_mf_config():
    if 'mf_reference' not in DATA:
        raise HTTPException(503)
    df = DATA['mf_reference']

    riskometers = sorted(df['riskometerScheme'].dropna().unique().tolist())
    benchmarks = sorted(df['benchmark'].dropna().unique().tolist())

    # Distinct (subcategory, riskometer, benchmark) combinations that actually
    # occur in the data — lets the frontend compute which filter options are
    # still valid given the other active filters, without a round trip per change.
    facet_df = df[['_subCategory', 'riskometerScheme', 'benchmark']].dropna().drop_duplicates()
    facets = [
        {
            "subcategory": int(row['_subCategory']),
            "riskometer": row['riskometerScheme'],
            "benchmark": row['benchmark'],
        }
        for _, row in facet_df.iterrows()
    ]

    return {
        "categories": MF_MAP,
        "riskometers": riskometers,
        "benchmarks": benchmarks,
        "facets": facets,
    }
    
    
@app.post("/api/mf-data")
def get_mf_data(request: MFDataRequest):
    if 'mf_by_date' not in DATA:
        raise HTTPException(503)

    effective_ed = get_effective_end_date(request.reference_date)
    df, snap_date = get_mf_snapshot(effective_ed)

    if df is None:
        return {
            "rows": [], "comparison_row": None,
            "total": 0, "page": 1, "page_size": request.page_size,
            "snapshot_date": None,
        }

    df = df.copy()

    # --- FILTERS ---
    if request.search:
        df = df[df['schemeName'].str.contains(request.search, case=False, na=False)]

    if request.subcategories:
        df = df[df['_subCategory'].isin(request.subcategories)]

    if request.riskometers:
        df = df[df['riskometerScheme'].isin(request.riskometers)]

    if request.benchmarks:
        df = df[df['benchmark'].isin(request.benchmarks)]

    # --- SORT ---
    sort_col = request.sort_by if request.sort_by in df.columns else "return1YearRegular"
    ascending = request.sort_dir == "asc"
    if sort_col in df.columns:
        df = df.sort_values(sort_col, ascending=ascending, na_position="last")

    total = len(df)

    # --- PAGINATE ---
    page = max(request.page, 1)
    page_size = min(max(request.page_size, 1), 500)
    start = (page - 1) * page_size
    df_page = df.iloc[start:start + page_size]

    # --- CLEAN ---
    keep_cols = [
        "schemeName", "benchmark", "riskometerScheme", "navRegular",
        "return1YearRegular", "return3YearRegular",
        "return5YearRegular", "return10YearRegular",
        "_category", "_subCategory",
    ]
    df_page = df_page[[c for c in keep_cols if c in df_page.columns]]
    df_page = df_page.replace([np.inf, -np.inf], np.nan)
    df_page = df_page.where(pd.notnull(df_page), None)
    rows = df_page.to_dict("records")

    # --- COMPARISON ROW (our own index, same 1/3/5/10yr windows, as of effective_ed) ---
    comparison_row = None
    if request.compare_index and request.compare_index in DATA["rebased"].columns:
        idx_name = request.compare_index

        def get_idx_ret(period):
            try:
                sd = get_start_date(period, effective_ed)
                val = calc_cagr(DATA["rebased"], sd, effective_ed, [idx_name], label=period)[idx_name]
                return clean_float(val)
            except Exception:
                return None

        comparison_row = {
            "schemeName": f"⭐ BENCHMARK: {idx_name}",
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
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))