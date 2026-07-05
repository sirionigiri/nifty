import pandas as pd
import numpy as np
import io

# ── Global Configuration ───────────────────────────────────────────────────
CATEGORY_MAP = {
    "Broad Market": [
        "NIFTY 100","NIFTY 200","NIFTY 50","NIFTY 500",
        "NIFTY FPI 150","NIFTY LARGEMID250","NIFTY MICROCAP250",
        "NIFTY MIDCAP 100","NIFTY MIDCAP 150","NIFTY MIDCAP 50",
        "NIFTY MID SELECT","NIFTY MIDSML 400","NIFTY MIDSMALLCAP400 50:50",
        "NIFTY NEXT 50","NIFTY SMLCAP 100","NIFTY SMLCAP 250",
        "NIFTY SMLCAP 50","NIFTY SMALLCAP 500","NIFTY TOTAL MKT",
        "NIFTY500 LMS EQL","NIFTY500 MULTICAP", 
    ],
    
    "Strategy": [
        "NIFTY 50 ARBITRAGE","NIFTY ALPHA 50","NIFTY ALPHALOWVOL",
        "NIFTY AQL 30","NIFTY AQLV 30","NIFTY DIV OPPS 50","NIFTY GROWSECT 15",
        "NIFTY HIGHBETA 50","NIFTY LOW VOL 50","NIFTYM150MOMNTM50",
        "NIFTY M150 QLTY50","NIFTYMS400 MQ 100","NIFTY QLTY LV 30",
        "NIFTYSML250MQ 100","NIFTY SML250 Q50","NIFTY TOP 10 EW",
        "NIFTY TOP 15 EW","NIFTY TOP 20 EW","NIFTY TMMQ 50",
        "NIFTY100 ALPHA 30","NIFTY100 EQL WGT","NIFTY100 LOWVOL30",
        "NIFTY100 QUALTY30","NIFTY200 ALPHA 30","NIFTY200MOMENTM30",
        "NIFTY200 QUALITY 30","NIFTY200 VALUE 30","NIFTY50 DIV POINT",
        "NIFTY50 EQL WGT","NIFTY50 PR 1X INV","NIFTY50 PR 2X LEV",
        "NIFTY50 TR 1X INV","NIFTY50 TR 2X LEV","NIFTY50 USD",
        "NIFTY50 VALUE 20","NIFTY500 EW","NIFTY500 FLEXICAP",
        "NIFTY500 LOWVOL50","NIFTY500MOMENTM50","NIFTY MULTI MQ 50",
        "NIFTY500 MQVLV50","NIFTY500 QLTY50","NIFTY500 VALUE 50",
    ],
    
    "Sectoral": [
        "NIFTY AUTO","NIFTY BANK","NIFTY CEMENT","NIFTY CHEMICALS",
        "NIFTY CONSR DURBL","NIFTY FIN SERVICE","NIFTY FINSRV25 50",
        "NIFTY FINSEREXBNK","NIFTY FMCG","NIFTY HEALTHCARE","NIFTY IT",
        "NIFTY MEDIA","NIFTY METAL","NIFTY MS FIN SERV","NIFTY MIDSML HLTH",
        "NIFTY MS IT TELCM","NIFTY OIL AND GAS","NIFTY PHARMA",
        "NIFTY PVT BANK","NIFTY PSU BANK","NIFTY REALTY","NIFTY500 HEALTH",
    ],
    
    "Thematic": [
        "NIFTY CAPITAL MKT","NIFTY COMMODITIES","NIFTY CONGLOMERATE 50",
        "NIFTY COREHOUSING","NIFTY CPSE","NIFTY ENERGY","NIFTY EV",
        "NIFTY HOUSING","NIFTY CONSUMPTION",
        "NIFTY INDIA CORPORATE GROUP INDEX - ADITYA BIRLA GROUP",
        "NIFTY INDIA CORPORATE GROUP INDEX - MAHINDRA GROUP",
        "NIFTY INDIA CORPORATE GROUP INDEX - TATA GROUP",
        "NIFTY TATA 25 CAP","NIFTY IND DEFENCE","NIFTY IND DIGITAL",
        "NIFTY INFRALOG","NIFTY INTERNET","NIFTY INDIA MFG",
        "NIFTY NEW CONSUMP","NIFTY INDIA RAILWAYS PSU","NIFTY CORP MAATR",
        "NIFTY IND TOURISM","NIFTY INFRA","NIFTY IPO","NIFTY MID LIQ 15",
        "NIFTY MS IND CONS","NIFTY MNC","NIFTY MOBILITY","NIFTY NONCYC CONS",
        "NIFTY PSE","NIFTY REITS & INVITS","NIFTY RURAL","NIFTY SERV SECTOR",
        "NIFTY SHARIAH 25","NIFTY SME EMERGE","NIFTY TRANS LOGIS","NIFTY WAVES",
        "NIFTY100 ENH ESG","NIFTY100 ESG","NIFTY100ESGSECLDR","NIFTY100 LIQ 15",
        "NIFTY50 SHARIAH","NIFTY MULTI MFG","NIFTY MULTI INFRA","NIFTY500 SHARIAH",
    ],
    "International Indices": [
        "S&P 500", "Nasdaq 100 Futures", "Bitcoin", "Gold", "Silver", 
        "EEM", "KOSPI", "Shanghai Composite", "Bovespa", "TAIEX", "Mexico IPC", "S&P Europe 350",
    ],
}

ROLL3_LABEL = "Rolling 3-Yr Avg"
ABS_PERIODS = ["Last Week", "MTD", "Last Month", "3 Month", "6 Month", "YTD"]

def load_and_prepare(df_raw: pd.DataFrame) -> dict:
    df_raw['Date'] = pd.to_datetime(df_raw['Date'])
    df_raw = df_raw.sort_values(['Index_Name', 'Date'])
    df_rb = df_raw.pivot(index='Date', columns='Index_Name', values='Total_Returns_Index')
    df_rb.index = pd.to_datetime(df_rb.index)
    df_rb = df_rb.sort_index()
    # Rebase
    df_rb = df_rb.apply(lambda col: col / col.dropna().iloc[0] * 100 if col.dropna().size > 0 else col)
    # Fix pct_change
    df_ret = (df_rb.pct_change(fill_method=None).ffill() * 100).round(4)
    df_yr = _calc_yearly(df_rb)
    return {
        "rebased": df_rb, "returns": df_ret, "yearly": df_yr,
        "indices": sorted(df_raw['Index_Name'].unique().tolist()),
        "end_date": df_rb.index.max(),
    }

def _get_last(df, target_date):
    """Returns (Value/Series, ActualDateFound)"""
    try:
        # DataFrame path: don't dropna across columns — each col has its own history
        if isinstance(df, pd.DataFrame):
            found_date = df.index.asof(target_date)
            if pd.isna(found_date):
                return None, None
            return df.loc[found_date], found_date

        # Series path (unchanged)
        valid_data = df.dropna()
        if valid_data.empty: return None, None
        inception_date = valid_data.index.min()
        
        if target_date < inception_date:
            return df.loc[inception_date], inception_date
        
        found_date = df.index.asof(target_date)
        if pd.isna(found_date):
            return df.loc[inception_date], inception_date
            
        return df.loc[found_date], found_date
    except:
        return None, None

def _calc_yearly(df):
    results = []
    years = sorted(df.index.year.unique())
    for i, y in enumerate(years):
        ed = pd.Timestamp(f"{y}-12-31")
        ev, _ = _get_last(df, ed) # Unpack tuple
        if ev is None: continue
        
        if i == 0:
            sv = df.iloc[0]
            lbl = f"{df.index.min().strftime('%d/%m/%y')}-{ed.strftime('%d/%m/%y')}"
        else:
            sv, _ = _get_last(df, pd.Timestamp(f"{years[i-1]}-12-31")) # Unpack tuple
            lbl = str(y)
            
        if sv is None: continue
        ret = (ev / sv - 1) * 100
        results.append({'Period': lbl, **ret.to_dict()})
        
    out = pd.DataFrame(results).set_index('Period')
    return out.round(2)

def get_start_date(label, end_actual):
    if label == "Last Week": return end_actual - pd.Timedelta(days=7)
    if label == "MTD": return pd.Timestamp(f"{end_actual.year}-{end_actual.month:02d}-01")
    if label == "Last Month": return end_actual - pd.DateOffset(months=1)
    if label == "3 Month": return end_actual - pd.DateOffset(months=3)
    if label == "6 Month": return end_actual - pd.DateOffset(months=6)
    if label == "YTD": return pd.Timestamp(f"{end_actual.year}-01-01")
    if label == "1 Yr": return end_actual - pd.DateOffset(years=1)
    if label == "3 Yr": return end_actual - pd.DateOffset(years=3)
    if label == "5 Yr": return end_actual - pd.DateOffset(years=5)
    if label == "10 Yr": return end_actual - pd.DateOffset(years=10)
    if label == "15 Yr": return end_actual - pd.DateOffset(years=15)
    if label == "20 Yr": return end_actual - pd.DateOffset(years=20)
    return end_actual - pd.DateOffset(years=20)

def calc_cagr(df_rb, sd, ed, cols, label=None):
    results = {}
    for col in cols:
        val_s, actual_sd = _get_last(df_rb[col], sd)
        val_e, actual_ed = _get_last(df_rb[col], ed)
        
        if val_s is None or val_e is None:
            results[col] = np.nan
            continue
            
        # --- FIX: Ensure we have a scalar float even if a Series is returned ---
        try:
            # If val_s is a Series (due to duplicates), take the first value
            sv = float(val_s.iloc[0]) if isinstance(val_s, pd.Series) else float(val_s)
            ev = float(val_e.iloc[0]) if isinstance(val_e, pd.Series) else float(val_e)
        except Exception as e:
            print(f"Math Error for {col}: {e}")
            results[col] = np.nan
            continue

        if sv == 0 or np.isnan(sv) or np.isnan(ev):
            results[col] = np.nan
            continue
            
        diff_days = (actual_ed - actual_sd).days
        if diff_days < 360 or label in ABS_PERIODS:
            results[col] = (ev / sv - 1) * 100
        else:
            yrs = diff_days / 365.25
            results[col] = ((ev / sv) ** (1/yrs) - 1) * 100
                
    return pd.Series(results).round(2)

def calc_vol(df_ret, sd, ed, cols):
    p = df_ret[cols].loc[(df_ret.index > sd) & (df_ret.index <= ed)]
    return pd.Series(np.nan, index=cols) if p.empty else (p.std() * np.sqrt(250)).round(2)

def calc_mdd(df_rb, sd, ed, cols):
    out = {}
    for col in cols:
        s = df_rb[col].dropna().loc[:ed]
        if s.empty: 
            out[col] = np.nan
            continue
        dd = s / s.cummax() - 1
        dw = dd.loc[(dd.index > sd) & (dd.index <= ed)]
        out[col] = round(dw.min() * 100, 2) if not dw.empty else np.nan
    return pd.Series(out)

def calc_beta(df_ret, sd, ed, cols, bench):
    p = df_ret.loc[(df_ret.index > sd) & (df_ret.index <= ed)]
    out = {}
    for col in cols:
        if col not in p.columns or bench not in p.columns: 
            out[col] = np.nan
            continue
        al = pd.concat([p[col], p[bench]], axis=1).dropna()
        if al.shape[0] < 2: out[col] = np.nan; continue
        cov = al.iloc[:,0].cov(al.iloc[:,1]); var = al.iloc[:,1].var()
        out[col] = round(cov/var, 2) if var != 0 else np.nan
    return pd.Series(out)

def calc_te(df_ret, sd, ed, cols, bench):
    p = df_ret.loc[(df_ret.index > sd) & (df_ret.index <= ed)]
    if bench not in p.columns: return pd.Series(np.nan, index=cols)
    exc = p[cols].sub(p[bench], axis=0)
    return pd.Series(np.nan, index=cols) if exc.empty else (exc.std() * np.sqrt(250)).round(2)

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

def build_table(df_rb, df_ret, metric, periods, cols, bench, end_actual, include_roll3=True):
    rows = {}
    for lbl in periods:
        sd = get_start_date(lbl, end_actual)
        valid_cols = [c for c in cols if c in df_rb.columns]
        if not valid_cols: continue
        if metric == 'cagr': rows[lbl] = calc_cagr(df_rb, sd, end_actual, valid_cols, label=lbl)
        elif metric == 'vol': rows[lbl] = calc_vol(df_ret, sd, end_actual, valid_cols)
        elif metric == 'mdd': rows[lbl] = calc_mdd(df_rb, sd, end_actual, valid_cols)
        elif metric == 'beta': rows[lbl] = calc_beta(df_ret, sd, end_actual, valid_cols, bench)
        elif metric == 'te': rows[lbl] = calc_te(df_ret, sd, end_actual, valid_cols, bench)
    if include_roll3:
        rows[ROLL3_LABEL] = calc_rolling3_metric(df_rb, df_ret, metric, cols, bench, end_actual)
    return pd.DataFrame(rows).T