import pandas as pd
import numpy as np
import yfinance as yf
from dateutil.relativedelta import relativedelta
from pathlib import Path
from datetime import date

# ── Output directory ──────────────────────────────────────────────────────────
OUTPUT_DIR = Path("market_data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TODAY = date.today().strftime("%Y-%m-%d")
START_DATE = "2006-01-01"

TICKERS = {
    "S&P 500":              "^GSPC",
    "NIFTY 50":             "^NSEI",
    "Nasdaq 100 Futures":   "NQ=F",
    "KOSPI":                "^KS11",
    "Shanghai Composite":   "000001.SS",
    "EEM":                  "EEM",
    "TAIEX":                "^TWII",
    "Bovespa":              "^BVSP",
    "Mexico IPC":           "^MXX",
    "S&P Europe 350":       "^SPEUP",
    "Gold":                 "GC=F",
    "Silver":               "SI=F",
    "Bitcoin":              "BTC-USD",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def nearest_price(series, target_date):
    """First available price on or after target_date."""
    valid_dates = series.index[series.index >= pd.Timestamp(target_date)]
    return series.loc[valid_dates[0]] if len(valid_dates) else np.nan


def cumulative_return(start_price, end_price):
    return (end_price / start_price - 1) * 100


def annualized_return(start_price, end_price, years):
    return ((end_price / start_price) ** (1 / years) - 1) * 100


def rolling_3yr_average_cagr(series):
    """Average of all rolling 3-year CAGR observations."""
    cagr_values = []
    for date in series.index:
        start_date = date - relativedelta(years=3)
        start_dates = series.index[series.index >= start_date]
        if len(start_dates) == 0:
            continue
        start_idx = start_dates[0]
        if start_idx >= date:
            continue
        cagr = annualized_return(series.loc[start_idx], series.loc[date], 3)
        cagr_values.append(cagr)
    return np.mean(cagr_values) if cagr_values else np.nan


def calculate_metrics(series):
    current_date  = series.index[-1]
    current_price = series.iloc[-1]
    results = {}

    # MTD
    month_price = nearest_price(series, current_date.replace(day=1))
    results["MTD"] = cumulative_return(month_price, current_price) if pd.notna(month_price) else np.nan

    # YTD
    year_price = nearest_price(series, current_date.replace(month=1, day=1))
    results["YTD"] = cumulative_return(year_price, current_price) if pd.notna(year_price) else np.nan

    # 1 Yr cumulative
    p1y = nearest_price(series, current_date - relativedelta(years=1))
    results["1 Yr"] = cumulative_return(p1y, current_price) if pd.notna(p1y) else np.nan

    # 3 Yr CAGR
    p3y = nearest_price(series, current_date - relativedelta(years=3))
    results["3 Yr"] = annualized_return(p3y, current_price, 3) if pd.notna(p3y) else np.nan

    # 5 Yr CAGR
    p5y = nearest_price(series, current_date - relativedelta(years=5))
    results["5 Yr"] = annualized_return(p5y, current_price, 5) if pd.notna(p5y) else np.nan

    # 10 Yr CAGR
    p10y = nearest_price(series, current_date - relativedelta(years=10))
    results["10 Yr"] = annualized_return(p10y, current_price, 10) if pd.notna(p10y) else np.nan

    # Rolling 3-Yr Average CAGR
    results["Rolling 3Yr Average"] = rolling_3yr_average_cagr(series)

    return results


# ── Download ──────────────────────────────────────────────────────────────────

print(f"Downloading data from {START_DATE} to {TODAY} …")

prices = yf.download(
    tickers=list(TICKERS.values()),
    start=START_DATE,
    end=TODAY,
    auto_adjust=True,
    progress=True,
)["Close"]

# Rename columns from tickers → readable names
ticker_to_name = {v: k for k, v in TICKERS.items()}
prices.rename(columns=ticker_to_name, inplace=True)

# ── Save raw price data ───────────────────────────────────────────────────────

prices_csv     = OUTPUT_DIR / f"prices_{START_DATE}_to_{TODAY}.csv"
prices_parquet = OUTPUT_DIR / f"prices_{START_DATE}_to_{TODAY}.parquet"

prices.to_csv(prices_csv)
prices.to_parquet(prices_parquet, engine="pyarrow", compression="snappy", index=True)

print(f"✅ Raw prices saved:")
print(f"   CSV     → {prices_csv}")
print(f"   Parquet → {prices_parquet}")

# ── Calculate metrics ─────────────────────────────────────────────────────────

rows = []
for name, ticker in TICKERS.items():
    try:
        series  = prices[name].dropna()
        metrics = calculate_metrics(series)
        metrics["Asset"] = name
        rows.append(metrics)
    except Exception as e:
        print(f"⚠️  Failed: {name} ({ticker}) → {e}")

results_df = pd.DataFrame(rows)[
    ["Asset", "MTD", "YTD", "1 Yr", "3 Yr", "5 Yr", "10 Yr", "Rolling 3Yr Average"]
].round(2)

# ── Save metrics ──────────────────────────────────────────────────────────────

metrics_csv     = OUTPUT_DIR / f"metrics_{TODAY}.csv"
metrics_parquet = OUTPUT_DIR / f"metrics_{TODAY}.parquet"

results_df.to_csv(metrics_csv, index=False)
results_df.to_parquet(metrics_parquet, engine="pyarrow", compression="snappy", index=False)

print(f"\n✅ Metrics saved:")
print(f"   CSV     → {metrics_csv}")
print(f"   Parquet → {metrics_parquet}")

print("\n── Results ──────────────────────────────────────────────────────────────")
print(results_df.to_string(index=False))