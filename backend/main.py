from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import pandas as pd
import os
import numpy as np




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
def startup_event():
    """
    This function runs ONCE when the `uvicorn` server starts.
    It loads the CSV from disk and prepares all the data.
    """
    csv_path = "NIFTY_total_returns.csv" # Assumes the CSV is in the same directory
    if not os.path.exists(csv_path):
        print(f"FATAL ERROR: {csv_path} not found. Server cannot start without data.")
        return # Or raise an exception

    print(f"Loading data from {csv_path}...")
    with open(csv_path, "rb") as f:
        file_bytes = f.read()
    
    prepared_data = load_and_prepare(file_bytes)
    
    # Store the processed dataframes globally in our DATA dictionary
    DATA['rebased'] = prepared_data['rebased']
    DATA['returns'] = prepared_data['returns']
    DATA['yearly']  = prepared_data['yearly']
    DATA['end_date'] = prepared_data['end_date']
    DATA['indices'] = prepared_data['indices']
    
    print("Data loaded and processed successfully. Server is ready.")



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
    return df.replace({np.nan: None}).to_dict(orient='records')



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


# --- Replace get_metrics_table in backend/main.py ---

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

    kw = dict(df_rb=DATA['rebased'], df_ret=DATA['returns'], periods=request.periods,
              cols=request.indices, bench=request.benchmark, end_actual=DATA['end_date'], include_roll3=True)

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

    df_result = df_result.reset_index().rename(columns={'index': 'Period'})
    df_result = df_result.replace({np.nan: None, np.inf: None, -np.inf: None})
    return df_result.to_dict(orient='records')



@app.post("/api/scatter-data")
def get_scatter_data(request: MetricsRequest):
    """Powers the Risk vs Return Scatter Plot"""
    # Use your build_table logic to get CAGR and Vol for the requested indices
    # request.periods[0] will be the active period (e.g. "5 Yr")
    period = request.periods[0]
    
    cagrs = calc_cagr(DATA['rebased'], get_start_date(period, DATA['end_date']), DATA['end_date'], request.indices)
    vols = calc_vol(DATA['returns'], get_start_date(period, DATA['end_date']), DATA['end_date'], request.indices)
    
    output = []
    for idx in request.indices:
        output.append({
            "index": idx,
            "return": cagrs[idx],
            "risk": vols[idx]
        })
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
    
    
