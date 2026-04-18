import pandas as pd
import numpy as np
import io

# ── Constants (Copied directly from your script) ───────────────────────────
CATEGORY_MAP = {
    "Broad Market": ["NIFTY 50", "NIFTY NEXT 50", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250", "NIFTY MICROCAP250", "NIFTY 500"],
    "Factor – Momentum": ["NIFTY200 MOMENTUM 30", "NIFTY500 MOMENTUM 50", "NIFTY MIDCAP150 MOMENTUM 50", "NIFTY SMALLCAP250 MOMENTUM QUALITY 100"],
    "Factor – Quality": ["NIFTY200 QUALITY 30", "NIFTY500 QUALITY 50", "NIFTY MIDCAP150 QUALITY 50", "NIFTY SMALLCAP250 QUALITY 50"],
    "Factor – Value": ["NIFTY200 VALUE 30", "NIFTY500 VALUE 50"],
    "Factor – Multi": ["NIFTY ALPHA LOW-VOLATILITY 30", "NIFTY500 MULTICAP MOMENTUM QUALITY 50", "NIFTY500 MULTIFACTOR MQVLV 50"],
}

PRESET_PERIODS = ["Last Week", "Last Month", "YTD", "1 Yr", "3 Yr", "5 Yr", "10 Yr", "15 Yr", "20 Yr"]
ROLL3_LABEL = "Rolling 3-Yr Avg"

# ── Analytics helpers ─────────────────────────────────────────────────────
def load_and_prepare(file_bytes: bytes) -> dict:
    """
    Loads raw CSV bytes, processes it, and returns a dictionary of key dataframes.
    This is the main data ingestion and preparation function.
    """
    df_raw = pd.read_csv(io.BytesIO(file_bytes))
    df_raw['Date'] = pd.to_datetime(df_raw['Date'])
    df_raw = df_raw.sort_values(['Index_Name', 'Date'])
    
    df_rb = df_raw.pivot(index='Date', columns='Index_Name', values='Total_Returns_Index')
    df_rb.index = pd.to_datetime(df_rb.index)
    df_rb = df_rb.sort_index()
    
    # Rebase each index to 100 at its own start date
    df_rb = df_rb.apply(lambda col: col / col.dropna().iloc[0] * 100 if col.dropna().size > 0 else col)
    
    df_ret = (df_rb.pct_change() * 100).round(4)
    df_yr = _calc_yearly(df_rb)
    
    return {
        "rebased": df_rb, 
        "returns": df_ret, 
        "yearly": df_yr,
        "indices": sorted(df_raw['Index_Name'].unique().tolist()),
        "end_date": df_rb.index.max(),
    }

def _get_last(df, date):
    """Helper to get the last available row on or before a given date."""
    sl = df.loc[:date]
    return sl.iloc[-1] if not sl.empty else None

def _calc_yearly(df):
    """Calculates calendar year returns."""
    results = []
    years = sorted(df.index.year.unique())
    for i, y in enumerate(years):
        ed = pd.Timestamp(f"{y}-12-31")
        ev = _get_last(df, ed)
        if ev is None: continue
        
        if i == 0:
            sv = df.iloc[0]
            lbl = f"{df.index.min().strftime('%d/%m/%y')}-{ed.strftime('%d/%m/%y')}"
        else:
            sv = _get_last(df, pd.Timestamp(f"{years[i-1]}-12-31"))
            lbl = str(y)
            
        ret = ev / sv - 1
        results.append({'Period': lbl, **ret.to_dict()})
        
    out = pd.DataFrame(results).set_index('Period')
    nc = out.select_dtypes(include='number').columns
    out[nc] = (out[nc] * 100).round(2)
    return out

def get_start_date(label, end_actual, slider_years=None):
    """Calculates the start date for a given period label (e.g., "1 Yr", "YTD")."""
    if label == "Last Week": return end_actual - pd.Timedelta(days=7)
    if label == "Last Month": return end_actual - pd.DateOffset(months=1)
    if label == "YTD": return pd.Timestamp(f"{end_actual.year}-01-01") - pd.Timedelta(days=1)
    if label == "1 Yr": return end_actual - pd.DateOffset(years=1)
    if label == "3 Yr": return end_actual - pd.DateOffset(years=3)
    if label == "5 Yr": return end_actual - pd.DateOffset(years=5)
    if label == "10 Yr": return end_actual - pd.DateOffset(years=10)
    if label == "15 Yr": return end_actual - pd.DateOffset(years=15)
    if label == "20 Yr": return end_actual - pd.DateOffset(years=20)
    if label.endswith(" Yr") and slider_years is not None:
        return end_actual - pd.DateOffset(years=slider_years)
    return end_actual - pd.DateOffset(years=20)

# ── Point-in-time metric calculators ─────────────────────────────────────
def calc_cagr(df_rb, sd, ed, cols):
    sv = _get_last(df_rb[cols], sd)
    ev = _get_last(df_rb[cols], ed)
    if sv is None or ev is None: return pd.Series(np.nan, index=cols)
    yrs = (ev.name - sv.name).days / 365.25
    if yrs <= 0: return pd.Series(np.nan, index=cols)
    return ((ev / sv) ** (1/yrs) - 1).mul(100).round(2)

def calc_vol(df_ret, sd, ed, cols):
    p = df_ret[cols].loc[(df_ret.index > sd) & (df_ret.index <= ed)]
    return pd.Series(np.nan, index=cols) if p.empty else (p.std() * np.sqrt(250)).round(2)

def calc_mdd(df_rb, sd, ed, cols):
    out = {}
    for col in cols:
        s = df_rb[col].dropna().loc[:ed]
        dd = s / s.cummax() - 1
        dw = dd.loc[(dd.index > sd) & (dd.index <= ed)]
        out[col] = round(dw.min() * 100, 2) if not dw.empty else np.nan
    return pd.Series(out)

def calc_beta(df_ret, sd, ed, cols, bench):
    p = df_ret.loc[(df_ret.index > sd) & (df_ret.index <= ed)]
    out = {}
    for col in cols:
        al = pd.concat([p[col], p[bench]], axis=1).dropna()
        if al.shape[0] < 2:
            out[col] = np.nan
            continue
        cov = al.iloc[:, 0].cov(al.iloc[:, 1])
        var = al.iloc[:, 1].var()
        out[col] = round(cov/var, 2) if var != 0 else np.nan
    return pd.Series(out)

def calc_te(df_ret, sd, ed, cols, bench):
    p = df_ret.loc[(df_ret.index > sd) & (df_ret.index <= ed)]
    exc = p[cols].sub(p[bench], axis=0)
    return pd.Series(np.nan, index=cols) if exc.empty else (exc.std() * np.sqrt(250)).round(2)

# ── Rolling 3-Yr Avg ───────────────────────────────────────────────────────
def calc_rolling3_metric(df_rb, df_ret, metric, cols, bench, end_actual):
    latest_full_year = end_actual.year - 1
    year_results = []
    for offset in range(3):
        yr = latest_full_year - offset
        sd = pd.Timestamp(f"{yr-1}-12-31")
        ed = pd.Timestamp(f"{yr}-12-31")
        if metric == 'cagr': r = calc_cagr(df_rb, sd, ed, cols)
        elif metric == 'vol': r = calc_vol(df_ret, sd, ed, cols)
        elif metric == 'mdd': r = calc_mdd(df_rb, sd, ed, cols)
        elif metric == 'beta': r = calc_beta(df_ret, sd, ed, cols, bench)
        elif metric == 'te': r = calc_te(df_ret, sd, ed, cols, bench)
        else: r = pd.Series(np.nan, index=cols)
        year_results.append(r)
    return pd.DataFrame(year_results).mean().round(2)

# ── Main Table Builder Function ───────────────────────────────────────────
def build_table(df_rb, df_ret, metric, periods, cols, bench,
                end_actual=None, custom_label=None, slider_years=None,
                include_roll3=False):
    """
    The main orchestrator function. It builds a DataFrame of a specific metric
    for given periods and indices. This is the primary function the API will call.
    """
    if not cols:
        return pd.DataFrame()

    rows = {}
    for lbl in periods:
        sl = slider_years if lbl == custom_label else None
        sd = get_start_date(lbl, end_actual, slider_years=sl)
        
        # Ensure we only calculate for columns that exist in the dataframe
        valid_cols = [c for c in cols if c in df_rb.columns and c in df_ret.columns]
        if bench not in valid_cols:
             valid_cols.append(bench) # ensure benchmark is available for calculation

        if not valid_cols: continue
        
        if metric == 'cagr': rows[lbl] = calc_cagr(df_rb, sd, end_actual, valid_cols)
        elif metric == 'vol': rows[lbl] = calc_vol(df_ret, sd, end_actual, valid_cols)
        elif metric == 'mdd': rows[lbl] = calc_mdd(df_rb, sd, end_actual, valid_cols)
        elif metric == 'beta': rows[lbl] = calc_beta(df_ret, sd, end_actual, valid_cols, bench)
        elif metric == 'te': rows[lbl] = calc_te(df_ret, sd, end_actual, valid_cols, bench)
    
    if include_roll3 and end_actual is not None:
        rows[ROLL3_LABEL] = calc_rolling3_metric(df_rb, df_ret, metric, cols, bench, end_actual)
    
    return pd.DataFrame(rows).T