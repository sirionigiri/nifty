from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd
import numpy as np
import os
import httpx
import io 
import time
import logging

# 1. --- ANALYTICS ENGINE IMPORTS ---
# Ensure these functions exist in your analytics.py
from analytics import (
    load_and_prepare, 
    build_table, 
    get_start_date, 
    calc_cagr, 
    calc_vol, 
    calc_mdd, 
    calc_beta, 
    CATEGORY_MAP
)

# 2. --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# 3. --- MIDDLEWARE (CORS & CACHING & TIMING) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace "*" with your Vercel URL
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

# 4. --- REQUEST MODELS & HELPERS ---
class MetricsRequest(BaseModel):
    metric: str
    periods: List[str]
    indices: List[str]
    benchmark: str
    reference_date: Optional[str] = None

DATA = {}
URL_RETURNS = "https://raw.githubusercontent.com/sirionigiri/nse-screener-data/main/nifty_data.parquet"
URL_VALUATION = "https://raw.githubusercontent.com/sirionigiri/nse-screener-data/main/valuation_data.parquet"

def get_effective_end_date(req_date):
    """Calculates the 'Today' for the calculation based on user selection."""
    if req_date:
        try:
            return pd.to_datetime(req_date).normalize()
        except:
            return DATA.get('end_date')
    return DATA.get('end_date')

def clean_float(val):
    """Ensures value is JSON compliant (NaN/Inf -> None/null)"""
    if val is None or not np.isfinite(val):
        return None
    return round(float(val), 2)

# 5. --- STARTUP ---
@app.on_event("startup")
async def startup_event():
    async with httpx.AsyncClient() as client:
        try:
            logger.info("Fetching Returns Data from GitHub...")
            res1 = await client.get(URL_RETURNS, timeout=60)
            if res1.status_code != 200: raise Exception("Returns file not found")
            
            df_returns = pd.read_parquet(io.BytesIO(res1.content))
            df_returns.columns = [c.strip() for c in df_returns.columns]
            prepared = load_and_prepare(df_returns)
            
            DATA['rebased'] = prepared['rebased']
            DATA['returns'] = prepared['returns']
            DATA['yearly']  = prepared['yearly']
            DATA['end_date'] = prepared['end_date']
            DATA['indices'] = prepared['indices']

            logger.info("Fetching Valuation Data from GitHub...")
            res2 = await client.get(URL_VALUATION, timeout=60)
            if res2.status_code == 200:
                df_val = pd.read_parquet(io.BytesIO(res2.content))
                df_val['Date'] = pd.to_datetime(df_val['Date'])
                DATA['valuation'] = df_val
            
            logger.info("✅ BACKEND ENGINE READY")
        except Exception as e:
            logger.error(f"❌ Startup Failure: {e}")

# 6. --- ENDPOINTS ---

@app.get("/api/config")
def get_config():
    if 'indices' not in DATA: raise HTTPException(status_code=503)
    return {"indices": DATA['indices'], "categories": CATEGORY_MAP}

@app.post("/api/summary")
def get_summary_metrics(request: MetricsRequest):
    if 'rebased' not in DATA: return {"error": "Data not loaded"}
    try:
        effective_ed = get_effective_end_date(request.reference_date)
        df_rb, df_ret = DATA['rebased'], DATA['returns']
        
        bench_name = next((c for c in df_rb.columns if c.upper() == request.benchmark.upper()), df_rb.columns[0])
        
        # Calculations relative to Reference Date
        c1 = calc_cagr(df_rb, get_start_date("1 Yr", effective_ed), effective_ed, [bench_name], label="1 Yr")[bench_name]
        c20 = calc_cagr(df_rb, get_start_date("20 Yr", effective_ed), effective_ed, [bench_name], label="20 Yr")[bench_name]
        
        # YTD window: Jan 1st of Reference Year to Reference Date
        ytd_start = pd.Timestamp(f"{effective_ed.year}-01-01")
        dd_ytd = calc_mdd(df_rb, ytd_start, effective_ed, [bench_name])[bench_name]
        v_ytd = calc_vol(df_ret, ytd_start, effective_ed, [bench_name])[bench_name]

        def fmt_summary(val):
            if val is None or not np.isfinite(val): return "—"
            return f"{val:+.1f}%"

        return {
            "cagr1": fmt_summary(c1),
            "cagr20": fmt_summary(c20),
            "mdd1": fmt_summary(dd_ytd),
            "vol1": fmt_summary(v_ytd),
            "count": len(request.indices)
        }
    except Exception as e:
        logger.error(f"Summary Error: {e}")
        return {"error": str(e)}

@app.post("/api/metrics")
def get_metrics_table(request: MetricsRequest):
    if 'rebased' not in DATA: raise HTTPException(status_code=503)
    try:
        effective_ed = get_effective_end_date(request.reference_date)
        
        # Clean incoming request indices for matching
        all_cols = DATA['rebased'].columns.tolist()
        req_indices = [idx.strip().upper() for idx in request.indices]
        valid_indices = [c for c in all_cols if c.strip().upper() in req_indices]
        bench_match = next((c for c in all_cols if c.strip().upper() == request.benchmark.strip().upper()), "NIFTY 50")

        if not valid_indices: return {"data": [], "error": "No valid indices selected"}

        kw = dict(df_rb=DATA['rebased'], df_ret=DATA['returns'], periods=request.periods,
                  cols=valid_indices, bench=bench_match, end_actual=effective_ed, 
                  include_roll3=(request.metric != 'mdd'))

        # Handle derived vs direct metrics
        if request.metric == "exc":
            # Alpha = Index CAGR - Bench CAGR
            df_c = build_table(metric='cagr', **kw)
            df_res = df_c.sub(df_c[bench_match], axis=0)
        elif request.metric == "ra":
            # Risk Adjusted = CAGR / Vol
            df_res = build_table(metric='cagr', **kw) / build_table(metric='vol', **kw)
        elif request.metric == "ir":
            # Information Ratio = Alpha / Tracking Error
            df_c = build_table(metric='cagr', **kw)
            df_e = df_c.sub(df_c[bench_match], axis=0)
            df_t = build_table(metric='te', **kw)
            df_res = df_e / df_t
        else:
            df_res = build_table(metric=request.metric, **kw)
        
        # Inject Date Ranges Metadata for each row
        ed_str = effective_ed.strftime('%d %b %y')
        date_ranges = {}
        for p in df_res.index:
            if p == "Rolling 3-Yr Avg":
                yr = effective_ed.year - 1
                date_ranges[p] = f"Jan {yr-2} - Dec {yr}"
            else:
                sd = get_start_date(p, effective_ed)
                sd_show = pd.Timestamp(f"{effective_ed.year}-01-01") if p == "YTD" else sd
                date_ranges[p] = f"{sd_show.strftime('%d %b %y')} - {ed_str}"

        df_res = df_res.reset_index().rename(columns={'index': 'Period'})
        df_res['Range'] = df_res['Period'].map(date_ranges)
        
        return {
            "data": df_res.replace({np.nan: None, np.inf: None, -np.inf: None}).to_dict('records'), 
            "error": None
        }
    except Exception as e:
        logger.error(f"Metrics Error: {e}")
        return {"data": [], "error": str(e)}

@app.post("/api/valuation-data")
def get_valuation_data(request: MetricsRequest):
    if 'valuation' not in DATA: raise HTTPException(status_code=503)
    try:
        effective_ed = get_effective_end_date(request.reference_date)
        df_full = DATA['valuation']
        
        # Filter for Target Index
        df = df_full[df_full['Index_Name'].str.strip().str.upper() == request.benchmark.strip().upper()].sort_values('Date')
        if df.empty: return {"error": f"No valuation data for {request.benchmark}"}

        # Slice Window between start of period and reference date
        period = request.periods[0] if request.periods else "5 Yr"
        sd = get_start_date(period, effective_ed)
        df_window = df[(df['Date'] >= sd) & (df['Date'] <= effective_ed)]

        if df_window.empty: return {"error": "Insufficient data in window"}

        def get_stats(col):
            # Calculate long-term norms from full historical dataset
            series = df[col].dropna()
            if series.empty: return None
            m, s = series.median(), series.std()
            return {
                "median": clean_float(m), "upper4": clean_float(m+4*s), "upper3": clean_float(m+3*s),
                "upper2": clean_float(m+2*s), "upper1": clean_float(m+s), "lower1": clean_float(m-s), "lower2": clean_float(m-2*s)
            }

        return {
            "dates": df_window['Date'].dt.strftime('%Y-%m-%d').tolist(),
            "pe": {"values": [clean_float(v) for v in df_window['PE']], "stats": get_stats('PE')},
            "pb": {"values": [clean_float(v) for v in df_window['PB']], "stats": get_stats('PB')},
            "dy": {"values": [clean_float(v) for v in df_window['Div_Yield']], "stats": get_stats('Div_Yield')}
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/nav-data")
def get_nav_data(request: MetricsRequest):
    if 'rebased' not in DATA: raise HTTPException(status_code=503)
    effective_ed = get_effective_end_date(request.reference_date)
    sd = get_start_date(request.periods[0], effective_ed)
    
    valid_cols = [c for c in request.indices if c in DATA['rebased'].columns]
    if request.benchmark and request.benchmark not in valid_cols: valid_cols.append(request.benchmark)

    # Slice strictly between start and effective end
    df = DATA['rebased'][valid_cols].loc[(DATA['rebased'].index >= sd) & (DATA['rebased'].index <= effective_ed)].dropna(how='all')
    if df.empty: return []

    if request.metric == "drawdown":
        df = (df / df.cummax() - 1) * 100 
    else:
        # Rebase to 100 at the first available point in this window
        df = df.apply(lambda col: col / col.dropna().iloc[0] * 100 if col.dropna().size > 0 else col)
    
    output = []
    for col in df.columns:
        s = df[col].dropna()
        output.append({"x": s.index.strftime('%Y-%m-%d').tolist(), "y": s.values.tolist(), "name": col})
    return output

@app.post("/api/scatter-data")
def get_scatter_data(request: MetricsRequest):
    if 'rebased' not in DATA: return []
    effective_ed = get_effective_end_date(request.reference_date)
    sd = get_start_date(request.periods[0] if request.periods else "5 Yr", effective_ed)
    
    valid_indices = [idx for idx in request.indices if idx in DATA['rebased'].columns]
    if not valid_indices: return []

    cagrs = calc_cagr(DATA['rebased'], sd, effective_ed, valid_indices)
    vols = calc_vol(DATA['returns'], sd, effective_ed, valid_indices)
    
    return [
        {"index": idx, "return": clean_float(cagrs.get(idx)), "risk": clean_float(vols.get(idx))}
        for idx in valid_indices if np.isfinite(cagrs.get(idx, np.nan)) and np.isfinite(vols.get(idx, np.nan))
    ]

@app.get("/api/calendar-returns")
def get_calendar_returns():
    if 'yearly' not in DATA: raise HTTPException(status_code=503)
    start = DATA['rebased'].index.min().strftime('%d %b %Y')
    end = DATA['rebased'].index.max().strftime('%d %b %Y')
    return {
        "data": DATA['yearly'].reset_index().replace({np.nan: None}).to_dict('records'),
        "scope": f"{start} to {end}"
    }

@app.post("/api/rankings")
def get_calendar_rankings(request: MetricsRequest):
    if 'yearly' not in DATA: raise HTTPException(status_code=503)
    try:
        available_cols = [c for c in DATA['yearly'].columns if c.strip().upper() in [s.strip().upper() for s in request.indices]]
        if not available_cols: return []
        # Relative ranking for selected indices only
        rank_df = DATA['yearly'][available_cols].rank(axis=1, ascending=False, method='min')
        results = []
        for year, row in rank_df.iterrows():
            item = {"Year": str(year).split('-')[0]}
            valid = False
            for idx_name, rnk in row.items():
                if not np.isnan(rnk):
                    item[f"Rank {int(rnk)}"] = idx_name
                    valid = True
            if valid: results.append(item)
        return results
    except: return []

if __name__ == "__main__":
    import uvicorn
    # Use PORT env variable for Cloud Run, default to 8000 for local
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))