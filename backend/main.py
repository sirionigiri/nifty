from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import pandas as pd
import os
import numpy as np
import duckdb
import httpx
import pandas as pd
from analytics import load_and_prepare


URL_RETURNS = "https://raw.githubusercontent.com/sirionigiri/nse-screener-data/main/nifty_data.parquet"
URL_VALUATION = "https://raw.githubusercontent.com/sirionigiri/nse-screener-data/main/valuation_data.parquet"


class MetricsRequest(BaseModel):
    metric: str
    periods: List[str]
    indices: List[str]
    benchmark: str



# Import YOUR functions directly from your file
from analytics import get_start_date, load_and_prepare, build_table, CATEGORY_MAP, calc_cagr, calc_vol, calc_mdd, calc_beta

app = FastAPI()

# Allow the Next.js frontend (running on localhost:3000) to communicate
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# This dictionary will hold your dataframes in memory
DATA = {}

# --- NEW: Load data on application startup ---
@app.on_event("startup")
async def startup_event():
    async with httpx.AsyncClient() as client:
        try:
            # Load Returns Data
            print("Fetching Returns Data from GitHub...")
            res1 = await client.get(URL_RETURNS)
            # DuckDB reads the parquet bytes directly into a Pandas DF
            df_returns = duckdb.query("SELECT * FROM read_parquet(?)", params=[res1.content]).to_df()
            prepared = load_and_prepare(df_returns)
            
            DATA['rebased'] = prepared['rebased']
            DATA['returns'] = prepared['returns']
            DATA['yearly']  = prepared['yearly']
            DATA['end_date'] = prepared['end_date']
            DATA['indices'] = prepared['indices']

            # Load Valuation Data
            print("Fetching Valuation Data from GitHub...")
            res2 = await client.get(URL_VALUATION)
            df_val = duckdb.query("SELECT * FROM read_parquet(?)", params=[res2.content]).to_df()
            df_val['Date'] = pd.to_datetime(df_val['Date'])
            DATA['valuation'] = df_val
            
            print("Backend Ready: All data loaded into RAM.")
        except Exception as e:
            print(f"Startup Failure: {e}")
            
            

@app.post("/api/valuation-data")
def get_valuation_data(request: MetricsRequest):
    if 'valuation' not in DATA: raise HTTPException(status_code=503)
    
    idx_name = request.benchmark 
    df_full = DATA['valuation']
    
    # Filter and sort
    df = df_full[df_full['Index_Name'].str.strip().str.upper() == idx_name.strip().upper()].sort_values('Date')
    
    if df.empty:
        return {"error": f"No valuation data available for {idx_name}"}

    # Time Window Slicing
    period = request.periods[0] if request.periods else "5 Yr"
    sd = get_start_date(period, DATA['end_date'])
    df_window = df[df['Date'] >= sd]

    if df_window.empty:
        return {"error": f"Insufficient data for {idx_name} in {period} window"}

    # HELPER: Ensure values are JSON compliant (NaN/Inf -> None)
    def clean_float(val):
        if val is None or not np.isfinite(val):
            return None
        return round(float(val), 2)

    def get_series_and_stats(column_name):
        series_full = df[column_name].dropna()
        series_window = df_window[column_name]
        
        if series_full.empty:
            return None

        median = series_full.median()
        std = series_full.std()

        # Handle case where std might be NaN (only one data point)
        if not np.isfinite(std): std = 0

        return {
            "values": [clean_float(v) for v in series_window.tolist()],
            "stats": {
                "median": clean_float(median),
                "upper4": clean_float(median + 4*std),
                "upper3": clean_float(median + 3*std),
                "upper2": clean_float(median + 2*std),
                "upper1": clean_float(median + 1*std),
                "lower1": clean_float(median - 1*std),
                "lower2": clean_float(median - 2*std),
            }
        }

    # Build response
    pe_data = get_series_and_stats('PE')
    pb_data = get_series_and_stats('PB')
    dy_data = get_series_and_stats('Div_Yield')

    return {
        "dates": df_window['Date'].dt.strftime('%Y-%m-%d').tolist(),
        "pe": pe_data,
        "pb": pb_data,
        "dy": dy_data,
    }
    
    

# --- NEW: Endpoint to provide initial app config ---
@app.get("/api/config")
def get_config():
    if 'indices' not in DATA: raise HTTPException(status_code=503)
    return {"indices": DATA['indices'], "categories": CATEGORY_MAP}



# Define the structure of the request we expect from the frontend
class MetricsRequest(BaseModel):
    metric: str
    periods: List[str]
    indices: List[str]
    benchmark: str
    
 
  
# --- Add to backend/main.py ---

@app.get("/api/calendar-returns")
def get_calendar_returns():
    if 'yearly' not in DATA: raise HTTPException(status_code=503)
    df = DATA['yearly'].reset_index()
    
    # Get total data scope
    start = DATA['rebased'].index.min().strftime('%d %b %Y')
    end = DATA['rebased'].index.max().strftime('%d %b %Y')
    
    return {
        "data": df.replace({np.nan: None}).to_dict(orient='records'),
        "scope": f"{start} to {end}"
    }


@app.post("/api/nav-data")
def get_nav_data(request: MetricsRequest):
    """
    Returns NAV or Drawdown data in Plotly-compatible format (list of traces,
    where each trace has lists of x and y values).
    """
    if 'rebased' not in DATA:
        raise HTTPException(status_code=503, detail="Data not available.")

    sd = get_start_date(request.periods[0], DATA['end_date'])
    
    # Filter columns to only include those that exist in the dataframe
    valid_cols = [c for c in request.indices if c in DATA['rebased'].columns]
    
    # Ensure benchmark is included if selected, even if not explicitly in selectedIndices
    if request.benchmark and request.benchmark in DATA['rebased'].columns and request.benchmark not in valid_cols:
        valid_cols.append(request.benchmark)

    if not valid_cols:
        return [] # Return empty list if no valid columns to plot

    df = DATA['rebased'][valid_cols].loc[DATA['rebased'].index >= sd].dropna(how='all')
    
    if df.empty:
        return [] # Return empty list if dataframe is empty after filtering/slicing

    if request.metric == "drawdown":
        # Calculate drawdown: (current / cumulative_max - 1) * 100
        # cummax() should be applied to the *rebased* values, not the drawdown itself.
        # This gives drawdown from the local peak within the window.
        df = (df / df.cummax() - 1) * 100 
    else:
        # Rebase to 100 at the start of the selected window
        # This needs to be done *after* slicing by `sd`
        df = df.apply(lambda col: col / col.dropna().iloc[0] * 100 if col.dropna().size > 0 else col)
    
    output = []
    for col in df.columns:
        s = df[col].dropna()
        if not s.empty: # Only add if series is not empty
            output.append({
                "x": s.index.strftime('%Y-%m-%d').tolist(), # Plotly expects date strings
                "y": s.values.tolist(),
                "name": col
            })
    return output



@app.post("/api/summary")
def get_summary_metrics(request: MetricsRequest):
    try:
        if 'rebased' not in DATA: return {"error": "Data not loaded"}
        ed = DATA['end_date']
        df_rb, df_ret = DATA['rebased'], DATA['returns']
        
        bench_name = request.benchmark if request.benchmark in df_rb.columns else df_rb.columns[0]
        bench_list = [bench_name]
        
        try:
            c1 = calc_cagr(df_rb, get_start_date("1 Yr", ed), ed, bench_list)[bench_name]
            c20 = calc_cagr(df_rb, get_start_date("20 Yr", ed), ed, bench_list)[bench_name]
            # Changed to YTD as requested
            dd1 = calc_mdd(df_rb, get_start_date("YTD", ed), ed, bench_list)[bench_name]
            v1 = calc_vol(df_ret, get_start_date("YTD", ed), ed, bench_list)[bench_name]
        except:
            return {"cagr1": "—", "cagr20": "—", "mdd1": "—", "vol1": "—", "count": 0}

        def safe_fmt(val, is_perc=True):
            if val is None or np.isnan(val) or np.isinf(val): return "—"
            return f"{val:+.1f}%" if is_perc else f"{val:.1f}%"

        return {"cagr1": safe_fmt(c1), "cagr20": safe_fmt(c20), "mdd1": safe_fmt(dd1, False), "vol1": safe_fmt(v1, False), "count": len(request.indices)}
    except Exception as e:
        return {"error": str(e)}




@app.post("/api/metrics")
def get_metrics_table(request: MetricsRequest):
    if 'rebased' not in DATA: raise HTTPException(status_code=503)

    include_roll = False if request.metric == 'mdd' else True

    kw = dict(df_rb=DATA['rebased'], df_ret=DATA['returns'], periods=request.periods,
              cols=request.indices, bench=request.benchmark, end_actual=DATA['end_date'], 
              include_roll3=include_roll)

    if request.metric == "exc":
        df_cagr = build_table(metric='cagr', **kw)
        df_result = df_cagr.sub(df_cagr[request.benchmark], axis=0)
    elif request.metric == "ra":
        df_cagr = build_table(metric='cagr', **kw)
        df_vol = build_table(metric='vol', **kw)
        df_result = df_cagr / df_vol
    elif request.metric == "ir":
        df_cagr = build_table(metric='cagr', **kw)
        df_exc = df_cagr.sub(df_cagr[request.benchmark], axis=0)
        df_te = build_table(metric='te', **kw)
        df_result = df_exc / df_te
    else:
        df_result = build_table(metric=request.metric, **kw)
    
    if df_result.empty: return []

    # --- NEW: Calculate Date Ranges for Metadata ---
    ed_str = DATA['end_date'].strftime('%d %b %Y')
    date_ranges = {}
    for p in df_result.index:
        if p == "Rolling 3-Yr Avg":
            yr = DATA['end_date'].year - 1
            date_ranges[p] = f"Jan {yr-2} - Dec {yr}"
        else:
            sd = get_start_date(p, DATA['end_date'])
            # Standardize YTD start to Jan 1st for clarity
            sd_show = pd.Timestamp(f"{DATA['end_date'].year}-01-01") if p == "YTD" else sd
            date_ranges[p] = f"{sd_show.strftime('%d %b %y')} - {ed_str}"

    df_result = df_result.reset_index().rename(columns={'index': 'Period'})
    
    # Inject the Range column
    df_result['Range'] = df_result['Period'].map(date_ranges)
    
    df_result = df_result.replace({np.nan: None, np.inf: None, -np.inf: None})
    return df_result.to_dict(orient='records')



@app.post("/api/scatter-data")
def get_scatter_data(request: MetricsRequest):
    """Robust Risk vs Return data provider"""
    if 'rebased' not in DATA: return []
    
    # 1. Determine time window
    period = request.periods[0] if request.periods else "5 Yr"
    sd = get_start_date(period, DATA['end_date'])
    ed = DATA['end_date']
    
    # 2. Run calculations
    # Note: We filter indices here to ensure they exist in the dataframe columns
    valid_indices = [idx for idx in request.indices if idx in DATA['rebased'].columns]
    if not valid_indices: return []

    cagrs = calc_cagr(DATA['rebased'], sd, ed, valid_indices)
    vols = calc_vol(DATA['returns'], sd, ed, valid_indices)
    
    output = []
    for idx in valid_indices:
        # Extract values
        r = cagrs.get(idx)
        v = vols.get(idx)

        # 3. THE CRITICAL FIX: 
        # Check if the value is a "Finite" number (Not NaN, Not Inf, Not -Inf)
        # We use pd.isna and np.isfinite for maximum safety
        if r is not None and v is not None:
            if np.isfinite(r) and np.isfinite(v):
                output.append({
                    "index": idx,
                    "return": round(float(r), 2),
                    "risk": round(float(v), 2)
                })
            else:
                # Log or print skipped indices for debugging
                print(f"Skipping {idx}: Non-finite values (CAGR: {r}, Vol: {v})")
        
    return output



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
    
    
