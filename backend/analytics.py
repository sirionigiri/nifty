# analytics.py
import pandas as pd
import numpy as np
import io

# ── Global Configuration ───────────────────────────────────────────────────
CATEGORY_MAP = {
    "Broad Market": [
        "NIFTY 100", "NIFTY 200", "NIFTY 50", "NIFTY 500",
        "NIFTY LARGEMIDCAP 250", "NIFTY MICROCAP 250",
        "NIFTY MIDCAP 100", "NIFTY MIDCAP 150", "NIFTY MIDCAP 50",
        "NIFTY MIDCAP SELECT", "NIFTY MIDSMALLCAP 400", "NIFTY MIDSMALLCAP400 50:50",
        "NIFTY NEXT 50", "NIFTY SMALLCAP 100", "NIFTY SMALLCAP 250",
        "NIFTY SMALLCAP 50", "NIFTY SMALLCAP 500", "NIFTY TOTAL MARKET",
        "NIFTY500 LARGEMIDSMALL EQUAL-CAP WEIGHTED", "NIFTY500 MULTICAP 50:25:25",
    ],

    "Strategy": [
        "NIFTY ALPHA 50", "NIFTY ALPHA LOW-VOLATILITY 30",
        "NIFTY ALPHA QUALITY LOW-VOLATILITY 30", "NIFTY ALPHA QUALITY VALUE LOW-VOLATILITY 30",
        "NIFTY DIVIDEND OPPORTUNITIES 50", "NIFTY GROWTH SECTORS 15",
        "NIFTY HIGH BETA 50", "NIFTY LOW VOLATILITY 50", "NIFTY MIDCAP150 MOMENTUM 50",
        "NIFTY MIDCAP150 QUALITY 50", "NIFTY MIDSMALLCAP400 MOMENTUM QUALITY 100",
        "NIFTY QUALITY LOW-VOLATILITY 30", "NIFTY SMALLCAP250 MOMENTUM QUALITY 100",
        "NIFTY SMALLCAP250 QUALITY 50", "NIFTY TOP 10 EQUAL WEIGHT",
        "NIFTY TOP 15 EQUAL WEIGHT", "NIFTY TOP 20 EQUAL WEIGHT",
        "NIFTY100 ALPHA 30", "NIFTY100 EQUAL WEIGHT", "NIFTY100 LOW VOLATILITY 30",
        "NIFTY100 QUALITY 30", "NIFTY200 ALPHA 30", "NIFTY200 MOMENTUM 30",
        "NIFTY200 QUALITY 30", "NIFTY200 VALUE 30",
        "NIFTY50 EQUAL WEIGHT", "NIFTY50 VALUE 20", "NIFTY500 EQUAL WEIGHT",
        "NIFTY500 FLEXICAP QUALITY 30", "NIFTY500 LOW VOLATILITY 50", "NIFTY500 MOMENTUM 50",
        "NIFTY500 MULTICAP INDIA MANUFACTURING 50:30:20", "NIFTY500 MULTICAP INFRASTRUCTURE 50:30:20",
        "NIFTY500 MULTICAP MOMENTUM QUALITY 50", "NIFTY500 MULTIFACTOR MQVLV 50",
        "NIFTY500 QUALITY 50", "NIFTY500 VALUE 50",
    ],

    "Sectoral": [
        "NIFTY AUTO", "NIFTY BANK", "NIFTY CEMENT", "NIFTY CHEMICALS",
        "NIFTY CONSUMER DURABLES", "NIFTY FINANCIAL SERVICES", "NIFTY FINANCIAL SERVICES 25/50",
        "NIFTY FINANCIAL SERVICES EX-BANK", "NIFTY FMCG", "NIFTY HEALTHCARE", "NIFTY IT",
        "NIFTY MEDIA", "NIFTY METAL", "NIFTY MIDSMALL FINANCIAL SERVICES", "NIFTY MIDSMALL HEALTHCARE",
        "NIFTY MIDSMALL IT & TELECOM", "NIFTY OIL & GAS", "NIFTY PHARMA",
        "NIFTY PRIVATE BANK", "NIFTY PSU BANK", "NIFTY REALTY", "NIFTY500 HEALTHCARE",
    ],

    "Thematic": [
        "NIFTY CAPITAL MARKETS", "NIFTY COMMODITIES", "NIFTY CONGLOMERATE 50",
        "NIFTY CORE HOUSING", "NIFTY CPSE", "NIFTY ENERGY", "NIFTY EV & NEW AGE AUTOMOTIVE",
        "NIFTY HOUSING", "NIFTY INDIA CONSUMPTION",
        "NIFTY INDIA CORPORATE GROUP INDEX - ADITYA BIRLA GROUP",
        "NIFTY INDIA CORPORATE GROUP INDEX - MAHINDRA GROUP",
        "NIFTY INDIA CORPORATE GROUP INDEX - TATA GROUP",
        "NIFTY INDIA CORPORATE GROUP INDEX - TATA GROUP 25% CAP",
        "NIFTY INDIA DEFENCE", "NIFTY INDIA DIGITAL",
        "NIFTY INDIA INFRASTRUCTURE & LOGISTICS", "NIFTY INDIA INTERNET", "NIFTY INDIA MANUFACTURING",
        "NIFTY INDIA NEW AGE CONSUMPTION", "NIFTY INDIA RAILWAYS PSU",
        "NIFTY INDIA SELECT 5 CORPORATE GROUPS (MAATR)", "NIFTY INDIA TOURISM",
        "NIFTY INFRASTRUCTURE", "NIFTY IPO", "NIFTY MIDCAP LIQUID 15",
        "NIFTY MIDSMALL INDIA CONSUMPTION", "NIFTY MNC", "NIFTY MOBILITY", "NIFTY NON-CYCLICAL CONSUMER",
        "NIFTY PSE", "NIFTY REITS & INVITS", "NIFTY RURAL", "NIFTY SERVICES SECTOR",
        "NIFTY SHARIAH 25", "NIFTY SME EMERGE", "NIFTY TRANSPORTATION & LOGISTICS", "NIFTY WAVES",
        "NIFTY100 ENHANCED ESG", "NIFTY100 ESG SECTOR LEADERS", "NIFTY100 LIQUID 15",
        "NIFTY50 SHARIAH", "NIFTY500 SHARIAH",
    ],

    "International Indices": [
        "S&P 500", "Nasdaq 100 Futures", "Bitcoin", "Gold", "Silver",
        "EEM", "KOSPI", "Shanghai Composite", "Bovespa", "TAIEX", "Mexico IPC", "S&P Europe 350",
    ],
}

ROLL3_LABEL = "Rolling 3-Yr Avg"
ABS_PERIODS = ["Last Week", "MTD", "Last Month", "3 Month", "6 Month", "YTD"]

from collections import Counter

# Maps every abbreviated/legacy index name (as it appeared in the old
# dataset) to its correct full name in the new dataset. Needed because
# these aren't case/whitespace variants — they're structurally different
# strings (e.g. "SMLCAP" vs "SMALLCAP") that no generic normalization can
# reconcile. Keys are matched case-insensitively at lookup time.
NAME_ALIASES_RAW = {
    # Broad Market
    "NIFTY LARGEMID250": "NIFTY LARGEMIDCAP 250",
    "NIFTY MICROCAP250": "NIFTY MICROCAP 250",
    "NIFTY MID SELECT": "NIFTY MIDCAP SELECT",
    "NIFTY MIDSML 400": "NIFTY MIDSMALLCAP 400",
    "NIFTY SMLCAP 100": "NIFTY SMALLCAP 100",
    "NIFTY SMLCAP 250": "NIFTY SMALLCAP 250",
    "NIFTY SMLCAP 50": "NIFTY SMALLCAP 50",
    "NIFTY TOTAL MKT": "NIFTY TOTAL MARKET",
    "NIFTY500 LMS EQL": "NIFTY500 LARGEMIDSMALL EQUAL-CAP WEIGHTED",
    "NIFTY500 MULTICAP": "NIFTY500 MULTICAP 50:25:25",

    # Strategy
    "NIFTY ALPHALOWVOL": "NIFTY ALPHA LOW-VOLATILITY 30",
    "NIFTY AQL 30": "NIFTY ALPHA QUALITY LOW-VOLATILITY 30",
    "NIFTY AQLV 30": "NIFTY ALPHA QUALITY VALUE LOW-VOLATILITY 30",
    "NIFTY DIV OPPS 50": "NIFTY DIVIDEND OPPORTUNITIES 50",
    "NIFTY GROWSECT 15": "NIFTY GROWTH SECTORS 15",
    "NIFTY HIGHBETA 50": "NIFTY HIGH BETA 50",
    "NIFTY LOW VOL 50": "NIFTY LOW VOLATILITY 50",
    "NIFTYM150MOMNTM50": "NIFTY MIDCAP150 MOMENTUM 50",
    "NIFTY M150 QLTY50": "NIFTY MIDCAP150 QUALITY 50",
    "NIFTYMS400 MQ 100": "NIFTY MIDSMALLCAP400 MOMENTUM QUALITY 100",
    "NIFTY QLTY LV 30": "NIFTY QUALITY LOW-VOLATILITY 30",
    "NIFTYSML250MQ 100": "NIFTY SMALLCAP250 MOMENTUM QUALITY 100",
    "NIFTY SML250 Q50": "NIFTY SMALLCAP250 QUALITY 50",
    "NIFTY TOP 10 EW": "NIFTY TOP 10 EQUAL WEIGHT",
    "NIFTY TOP 15 EW": "NIFTY TOP 15 EQUAL WEIGHT",
    "NIFTY TOP 20 EW": "NIFTY TOP 20 EQUAL WEIGHT",
    "NIFTY100 EQL WGT": "NIFTY100 EQUAL WEIGHT",
    "NIFTY100 LOWVOL30": "NIFTY100 LOW VOLATILITY 30",
    "NIFTY100 QUALTY30": "NIFTY100 QUALITY 30",
    "NIFTY200MOMENTM30": "NIFTY200 MOMENTUM 30",
    "NIFTY50 EQL WGT": "NIFTY50 EQUAL WEIGHT",
    "NIFTY500 EW": "NIFTY500 EQUAL WEIGHT",
    "NIFTY500 LOWVOL50": "NIFTY500 LOW VOLATILITY 50",
    "NIFTY500MOMENTM50": "NIFTY500 MOMENTUM 50",
    "NIFTY MULTI MQ 50": "NIFTY500 MULTICAP MOMENTUM QUALITY 50",
    "NIFTY500 MQVLV50": "NIFTY500 MULTIFACTOR MQVLV 50",
    "NIFTY500 QLTY50": "NIFTY500 QUALITY 50",

    # Sectoral
    "NIFTY CONSR DURBL": "NIFTY CONSUMER DURABLES",
    "NIFTY FIN SERVICE": "NIFTY FINANCIAL SERVICES",
    "NIFTY FINSRV25 50": "NIFTY FINANCIAL SERVICES 25/50",
    "NIFTY FINSEREXBNK": "NIFTY FINANCIAL SERVICES EX-BANK",
    "NIFTY MS FIN SERV": "NIFTY MIDSMALL FINANCIAL SERVICES",
    "NIFTY MIDSML HLTH": "NIFTY MIDSMALL HEALTHCARE",
    "NIFTY MS IT TELCM": "NIFTY MIDSMALL IT & TELECOM",
    "NIFTY OIL AND GAS": "NIFTY OIL & GAS",
    "NIFTY PVT BANK": "NIFTY PRIVATE BANK",

    # Thematic
    "NIFTY CAPITAL MKT": "NIFTY CAPITAL MARKETS",
    "NIFTY COREHOUSING": "NIFTY CORE HOUSING",
    "NIFTY EV": "NIFTY EV & NEW AGE AUTOMOTIVE",
    "NIFTY CONSUMPTION": "NIFTY INDIA CONSUMPTION",
    "NIFTY TATA 25 CAP": "NIFTY INDIA CORPORATE GROUP INDEX - TATA GROUP 25% CAP",
    "NIFTY IND DEFENCE": "NIFTY INDIA DEFENCE",
    "NIFTY INDIA MFG": "NIFTY INDIA MANUFACTURING",
    "NIFTY NEW CONSUMP": "NIFTY INDIA NEW AGE CONSUMPTION",
    "NIFTY CORP MAATR": "NIFTY INDIA SELECT 5 CORPORATE GROUPS (MAATR)",
    "NIFTY IND TOURISM": "NIFTY INDIA TOURISM",
    "NIFTY INFRA": "NIFTY INFRASTRUCTURE",
    "NIFTY MID LIQ 15": "NIFTY MIDCAP LIQUID 15",
    "NIFTY MS IND CONS": "NIFTY MIDSMALL INDIA CONSUMPTION",
    "NIFTY NONCYC CONS": "NIFTY NON-CYCLICAL CONSUMER",
    "NIFTY SERV SECTOR": "NIFTY SERVICES SECTOR",
    "NIFTY TRANS LOGIS": "NIFTY TRANSPORTATION & LOGISTICS",
    "NIFTY100 ENH ESG": "NIFTY100 ENHANCED ESG",
    "NIFTY100ESGSECLDR": "NIFTY100 ESG SECTOR LEADERS",
    "NIFTY100 LIQ 15": "NIFTY100 LIQUID 15",
    "NIFTY MULTI MFG": "NIFTY500 MULTICAP INDIA MANUFACTURING 50:30:20",
    "NIFTY MULTI INFRA": "NIFTY500 MULTICAP INFRASTRUCTURE 50:30:20",
}

# Keys normalized once at module load, so lookups are a simple dict hit
# regardless of how the old name's case/spacing appears in the raw data.
NAME_ALIASES = {k.upper().strip(): v for k, v in NAME_ALIASES_RAW.items()}


def _normalize_index_names(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Canonicalizes Index_Name in three passes, and flags which rows came
    from a known legacy/abbreviated name so duplicate (Date, Index_Name)
    conflicts can be resolved in favor of the fuller, current-name series:

      1. Explicit alias table (NAME_ALIASES) — abbreviated old names like
         "NIFTY SMLCAP 50" get rewritten to the new full name
         "NIFTY SMALLCAP 50" outright, regardless of case/spacing.
      2. CATEGORY_MAP casing match — anything not in the alias table but
         matching a CATEGORY_MAP entry case-insensitively gets that exact
         casing, so category filters and sector maps keep working.
      3. Majority-vote fallback — anything still unmatched (e.g.
         international assets) keeps whatever casing appears most often
         in the raw data.
    """
    df = df_raw.copy()
    original = df['Index_Name'].astype(str).str.strip()
    upper_key = original.str.upper().str.replace(r'\s+', ' ', regex=True)

    # Pass 1: explicit alias table
    canonical = upper_key.map(NAME_ALIASES)

    # Pass 2: CATEGORY_MAP casing match
    category_lookup = {
        name.upper().strip(): name
        for group in CATEGORY_MAP.values()
        for name in group
    }
    canonical = canonical.fillna(upper_key.map(category_lookup))

    # Pass 3: majority-vote fallback for anything still unmatched
    unmapped_mask = canonical.isna()
    if unmapped_mask.any():
        fallback_lookup = {}
        for k in upper_key[unmapped_mask].unique():
            variants = original[upper_key == k]
            fallback_lookup[k] = Counter(variants).most_common(1)[0][0]
        canonical = canonical.fillna(upper_key.map(fallback_lookup))

    df['Index_Name'] = canonical
    # Rows whose ORIGINAL name was a known legacy alias key are lower
    # priority when resolving same-date conflicts against the current name.
    df['_is_legacy'] = upper_key.isin(NAME_ALIASES.keys()).astype(int)
    return df


def load_and_prepare(df_raw: pd.DataFrame) -> dict:
    df_raw['Date'] = pd.to_datetime(df_raw['Date'])
    df_raw = _normalize_index_names(df_raw)

    # After aliasing, "NIFTY SMLCAP 50" (legacy) and "NIFTY SMALLCAP 50"
    # (current) both carry Index_Name == "NIFTY SMALLCAP 50", so the same
    # Date can now appear twice for that name — pivot() would raise a
    # duplicate-entries error. Collapse those pairs here: sort so the
    # non-legacy (fuller) row comes first per (Date, Index_Name), then
    # keep the first non-null value — i.e. prefer the good series, but
    # fall back to the legacy value if the good series is missing that date.
    df_raw = df_raw.sort_values(['Date', 'Index_Name', '_is_legacy'])
    df_raw = (
        df_raw.groupby(['Date', 'Index_Name'], as_index=False, sort=False)
        .agg(Total_Returns_Index=(
            'Total_Returns_Index',
            lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan
        ))
    )

    df_raw = df_raw.sort_values(['Index_Name', 'Date'])
    df_rb = df_raw.pivot(index='Date', columns='Index_Name', values='Total_Returns_Index')
    df_rb.index = pd.to_datetime(df_rb.index)
    df_rb = df_rb.sort_index()
    df_rb = df_rb.apply(lambda col: col / col.dropna().iloc[0] * 100 if col.dropna().size > 0 else col)
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