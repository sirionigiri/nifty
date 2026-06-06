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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from typing import List, Optional
import matplotlib.pyplot as plt

# ── Internal ──────────────────────────────────────────────────────────────────
from analytics import (
    CATEGORY_MAP,
    build_table,
    calc_beta,
    calc_cagr,
    calc_mdd,
    calc_rolling3_metric,
    calc_vol,
    get_start_date,
    load_and_prepare,
)


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# APP & MIDDLEWARE
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production replace "*" with your Vercel URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
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
DATA: dict = {}

# Maps index names to human-readable sector/type labels used in the Excel report
REPORT_SECTOR_MAP = {
    "NIFTY 500": "Benchmark",
    "NIFTY ENERGY": "Energy",
    "NIFTY AUTO": "Auto",
    "NIFTY INDIA MFG": "Manufacturing",
    "NIFTY BANK": "Banks",
    "NIFTY CAPITAL MKT": "Capital Market",
    "NIFTY FINANCIAL SERVICES EX-BANK": "Finserv",
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


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST MODEL
# ─────────────────────────────────────────────────────────────────────────────

class MetricsRequest(BaseModel):
    metric: str
    periods: List[str]
    indices: List[str]
    benchmark: str
    reference_date: Optional[str] = None


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

@app.on_event("startup")
async def startup_event():
    async with httpx.AsyncClient() as client:
        try:
            logger.info("📡 Loading Index Returns...")
            r1 = await client.get(URL_RETURNS, timeout=60)
            df_returns = pd.read_parquet(io.BytesIO(r1.content))
            df_returns.columns = [c.strip() for c in df_returns.columns]
            prep = load_and_prepare(df_returns)
            DATA.update(prep)

            logger.info("📡 Loading Valuation Data...")
            r2 = await client.get(URL_VALUATION, timeout=60)
            if r2.status_code == 200:
                df_v = pd.read_parquet(io.BytesIO(r2.content))
                # CRITICAL: Strip names and ensure Date type for matching
                df_v['Index_Name'] = df_v['Index_Name'].str.strip()
                df_v['Date'] = pd.to_datetime(df_v['Date'])
                DATA["valuation"] = df_v
            
            logger.info("✅ BACKEND ENGINE READY")
        except Exception as e:
            logger.error(f"❌ Startup Failure: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS — read-only / config
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    if "indices" not in DATA:
        raise HTTPException(status_code=503)
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

        # Build human-readable date range labels for each period row
        ed_str = effective_ed.strftime("%d %b %y")
        date_ranges = {}
        for p in df_res.index:
            if p == "Rolling 3-Yr Avg":
                yr = effective_ed.year - 1
                date_ranges[p] = f"Jan {yr - 2} - Dec {yr}"
            else:
                sd = get_start_date(p, effective_ed)
                if p == "MTD":
                    sd_show = pd.Timestamp(f"{effective_ed.year}-{effective_ed.month:02d}-01")
                elif p == "YTD":
                    sd_show = pd.Timestamp(f"{effective_ed.year}-01-01")
                else:
                    sd_show = sd
                date_ranges[p] = f"{sd_show.strftime('%d %b %y')} - {ed_str}"

        df_res = df_res.reset_index().rename(columns={"index": "Period"})
        df_res["Range"] = df_res["Period"].map(date_ranges)

        return {
            "data": df_res.replace({np.nan: None, np.inf: None, -np.inf: None}).to_dict("records"),
            "error": None,
        }
    except Exception as e:
        logger.error(f"Metrics Error: {e}")
        return {"data": [], "error": str(e)}


@app.post("/api/valuation-data")
def get_val_data(request: MetricsRequest):
    if 'valuation' not in DATA: raise HTTPException(503)
    try:
        effective_ed = get_effective_end_date(request.reference_date)
        df_full = DATA['valuation']
        
        # 1. Filter for Target Index
        df = df_full[df_full['Index_Name'].str.upper() == request.benchmark.upper()].sort_values('Date')
        if df.empty: return {"error": f"No data for {request.benchmark}"}

        # 2. Slice the Window FIRST
        period = request.periods[0] if request.periods else "5 Yr"
        sd = get_start_date(period, effective_ed)
        df_w = df[(df['Date'] >= sd) & (df['Date'] <= effective_ed)].copy()

        if df_w.empty: return {"error": "Insufficient data in selected window"}

        # 3. STATS HELPER (Now strictly using the windowed data)
        def stats_for_window(s):
            clean_s = s.dropna()
            if clean_s.empty: return None
            
            # Recalculate Median and SD based ONLY on the current view
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
        s = df[col].dropna()
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
    if "yearly" not in DATA:
        raise HTTPException(status_code=503)
    try:
        available_cols = [
            c for c in DATA["yearly"].columns
            if c.strip().upper() in [s.strip().upper() for s in request.indices]
        ]
        if not available_cols:
            return []

        rank_df = DATA["yearly"][available_cols].rank(axis=1, ascending=False, method="min")
        results = []
        for year, row in rank_df.iterrows():
            item = {"Year": str(year).split("-")[0]}
            valid = False
            for idx_name, rnk in row.items():
                if not np.isnan(rnk):
                    item[f"Rank {int(rnk)}"] = idx_name
                    valid = True
            if valid:
                results.append(item)
        return results
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — Excel report generation
# ─────────────────────────────────────────────────────────────────────────────
def create_matplotlib_gauge(current, min_val, max_val, median_val, reverse=False):
    """Creates a linear gauge with a Black Pointer and a Blue Median Line."""
    try:
        # Normalize positions (0 to 1)
        pos = (current - min_val) / (max_val - min_val) if max_val != min_val else 0.5
        pos_med = (median_val - min_val) / (max_val - min_val) if max_val != min_val else 0.5
        pos = max(0, min(1, pos))
        pos_med = max(0, min(1, pos_med))
    except: 
        pos, pos_med = 0.5, 0.5

    fig, ax = plt.subplots(figsize=(4, 0.8))
    
    # 1. Draw Gradient Bar
    cmap = "RdYlGn" if not reverse else "RdYlGn_r"
    gradient = np.linspace(0, 1, 256).reshape(1, -1)
    ax.imshow(gradient, aspect="auto", extent=[0, 1, 0, 0.25], cmap=cmap)

    # 2. Draw BLUE MEDIAN LINE (The new requirement)
    ax.plot([pos_med, pos_med], [0, 0.25], color='#2563eb', linewidth=2.5, zorder=11, label="Median")

    # 3. Draw CURRENT VALUE POINTER (Black Triangle)
    ax.scatter(pos, 0.35, marker="v", s=200, color="black", zorder=12)

    # 4. Add Text Labels
    txt_style = {'fontsize': 9, 'fontweight': 'bold', 'family': 'sans-serif'}
    ax.text(0, 0.5, f"{min_val:.1f}", ha="left", color='#64748b', **txt_style)
    ax.text(1, 0.5, f"{max_val:.1f}", ha="right", color='#64748b', **txt_style)
    ax.text(pos, 0.1, f"{current:.1f}", ha="center", color='black', **txt_style)
    # Add small blue label for median
    ax.text(pos_med, 0.45, "MED", ha="center", color='#2563eb', fontsize=7, fontweight='black')

    ax.set_xlim(-0.05, 1.05); ax.set_ylim(-0.1, 0.7); ax.axis("off")

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.02, transparent=True, dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf

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
        head_f = workbook.add_format({'bold': True, 'bg_color': '#F2F2F2', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        text_f = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter', 'font_size': 9})
        perc_f = workbook.add_format({'num_format': '0.0"%"', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        num_f = workbook.add_format({'num_format': '0.0', 'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 9})
        rank_f = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 8, 'text_wrap': True})
        italic_f = workbook.add_format({'italic': True, 'font_size': 8, 'text_wrap': True})

        # --- CATEGORIZE INDICES ---
        factor_list = CATEGORY_MAP.get("Strategy", []) + CATEGORY_MAP.get("Factor Indices", [])
        s_indices = [idx for idx in request.indices if idx not in factor_list]
        f_indices = [idx for idx in request.indices if idx in factor_list]
        bench = request.benchmark if request.benchmark in DATA['rebased'].columns else "NIFTY 500"
        
        # Ensure Benchmark is at the top of BOTH lists
        if bench not in s_indices: s_indices.insert(0, bench)
        if bench not in f_indices: f_indices.insert(0, bench)
        num_periods = len(request.periods)

        # --- SHEET 1: SECTOR & THEMATIC ---
        ws1 = workbook.add_worksheet("Sector Dashboard")
        ws1.set_column('A:A', 35); ws1.set_column('B:M', 12); ws1.set_column('I:K', 25)
        ws1.merge_range('A1:K1', 'Sector & Thematic Dashboard', title_f)
        
        # Merge subheaders
        ws1.merge_range(1, 1, 1, num_periods, 'Performance (%)', head_f)
        ws1.merge_range(1, 1 + num_periods, 1, 3 + num_periods, 'Valuations (5Y Linear Gauge)', head_f)
        
        headers1 = ["Indices"] + request.periods + ["P/E (5Y)", "P/B (5Y)", "DY (5Y)"]
        ws1.write_row('A3', headers1, head_f)

        row_idx = 3
        for idx in s_indices[:19]:
            ws1.set_row(row_idx, 45)
            ws1.write(row_idx, 0, idx, text_f)
            # Perf
            ws1.write_row(row_idx, 1, get_perf_row_data(idx, effective_ed, request.periods, bench), perc_f)
            # Gauges (5Y Window)
            try:
                val_df = DATA['valuation']
                hist = val_df[(val_df['Index_Name'].str.upper() == idx.upper()) & (val_df['Date'] >= five_yrs_ago) & (val_df['Date'] <= effective_ed)]
                if not hist.empty:
                    for i, col in enumerate(['PE', 'PB', 'Div_Yield']):
                        ser = hist[col].dropna()
                        if not ser.empty:
                            img = create_matplotlib_gauge(ser.iloc[-1], ser.min(), ser.max(), ser.median(), reverse=(col=='Div_Yield'))
                            ws1.insert_image(row_idx, 1 + num_periods + i, f"s_{row_idx}_{i}.png", {'image_data': img, 'x_scale': 0.7, 'y_scale': 0.7, 'x_offset': 10, 'y_offset': 5})
            except: pass
            row_idx += 1

        ws1.merge_range(22, 0, 24, 10, f"Source: niftyindices.com and ElevateWealth. Total Returns in INR for period ending {effective_ed.date()}. Rolling 3-Yr average returns calculated since Dec 2020. All returns annualized except < 1yr.", italic_f)

        # Sector Rankings (Bottom of Sheet 1)
        ws1.write(26, 0, "Ranking Matrix (Sector)", workbook.add_format({'bold': True}))
        years = [str(y) for y in range(2016, effective_ed.year)] + [f"{effective_ed.year} (YTD)"]
        ws1.write_row(27, 0, ["Year"] + [f"Rank {i+1}" for i in range(6)], head_f)
        for r, y_lab in enumerate(years):
            curr_r = 28 + r
            ws1.write(curr_r, 0, y_lab, head_f)
            rets = calc_cagr(DATA['rebased'], pd.Timestamp(f"{effective_ed.year}-01-01"), effective_ed, s_indices, label="YTD") if "YTD" in y_lab else (DATA['yearly'].loc[y_lab, s_indices] if y_lab in DATA['yearly'].index else pd.Series())
            top_6 = rets.sort_values(ascending=False).head(6)
            for i, (name, val) in enumerate(top_6.items()):
                ws1.write(curr_r, i+1, f"{REPORT_SECTOR_MAP.get(name, name)}\n({val:.1f}%)", rank_f)

        # --- SHEET 2: FACTOR DASHBOARD ---
        ws2 = workbook.add_worksheet("Factor Dashboard")
        ws2.set_column('A:A', 35); ws2.set_column('B:M', 12)
        ws2.merge_range('A1:K1', 'Factor Dashboard', title_f)
        
        # FIX: Updated Headers to mention Since Inception
        ws2.merge_range(1, 1, 1, num_periods, 'Performance (%)', head_f)
        ws2.merge_range(1, 1 + num_periods, 1, 3 + num_periods, 'Risk Metrics (Since Inception)', head_f)
        headers2 = ["Factor Indices"] + request.periods + ["Volatility (Incept)", "Risk-Adj (Incept)", "Max DD (Incept)"]
        ws2.write_row('A3', headers2, head_f)

        row_idx = 3
        for idx in f_indices:
            ws2.write(row_idx, 0, idx, text_f)
            ws2.write_row(row_idx, 1, get_perf_row_data(idx, effective_ed, request.periods, bench), perc_f)
            # Since Inception Risk Metrics
            try:
                incept_date = DATA['rebased'][idx].dropna().index.min()
                v_val = calc_vol(DATA['returns'], incept_date, effective_ed, [idx])[idx]
                m_val = calc_mdd(DATA['rebased'], incept_date, effective_ed, [idx])[idx]
                c_val = calc_cagr(DATA['rebased'], incept_date, effective_ed, [idx])[idx]
                ra_val = c_val / v_val if v_val and v_val != 0 else 0
                ws2.write_row(row_idx, 1 + num_periods, [clean_float(v_val), clean_float(ra_val), clean_float(m_val)], num_f)
            except: pass
            row_idx += 1

        # Factor Ranking Matrix (Sheet 2)
        row_idx += 2
        ws2.write(row_idx, 0, "Ranking of Factor Portfolios", workbook.add_format({'bold': True}))
        for r_idx, r_data in enumerate(FACTOR_RANKS_STATIC):
            ws2.write_row(row_idx + 1 + r_idx, 0, r_data, head_f if r_idx == 0 else text_f)
        
        # Append dynamic 2026 YTD column for factors
        y26_col = 20 
        ws2.write(row_idx + 1, y26_col, f"{effective_ed.year} (YTD)", head_f)
        f_ytd = calc_cagr(DATA['rebased'], pd.Timestamp(f"{effective_ed.year}-01-01"), effective_ed, f_indices, label="YTD").sort_values(ascending=False).head(6)
        for i, (name, val) in enumerate(f_ytd.items()):
             ws2.write(row_idx + 2 + i, y26_col, f"{name}\n({val:.1f}%)", rank_f)

        workbook.close()
        output.seek(0)
        return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=NSE_Report.xlsx"})

    except Exception as e:
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))