import json
import os
import random
import time
import warnings
from datetime import datetime, timedelta
import pandas as pd
import requests
import urllib3

# Suppress warnings
warnings.filterwarnings("ignore", category=urllib3.exceptions.NotOpenSSLWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
PARQUET_FILE = "data/nifty_data.parquet"
# Start date if the file doesn't exist yet
INCEPTION_DATE = datetime(2006, 1, 1) 
END_DATE = datetime.today()

# Use your full ALL_INDICES dictionary here
ALL_INDICES = {
    "Broad Market Indices": [
        "NIFTY 100",
        "NIFTY 200",
        "NIFTY 50",
        "NIFTY 500",
        "NIFTY FPI 150",
        "NIFTY LARGEMID250",
        "NIFTY MICROCAP250",
        "NIFTY MIDCAP 100",
        "NIFTY MIDCAP 150",
        "NIFTY MIDCAP 50",
        "NIFTY MID SELECT",
        "NIFTY MIDSML 400",
        "NIFTY MIDSMALLCAP400 50:50",
        "NIFTY NEXT 50",
        "NIFTY SMLCAP 100",
        "NIFTY SMLCAP 250",
        "NIFTY SMLCAP 50",
        "NIFTY SMALLCAP 500",
        "NIFTY TOTAL MKT",
        "NIFTY500 LMS EQL",
        "NIFTY500 MULTICAP"
    ],
    "Sectoral Indices": [
        "NIFTY AUTO",
        "NIFTY BANK",
        "NIFTY CEMENT",
        "NIFTY CHEMICALS",
        "NIFTY CONSR DURBL",
        "NIFTY FIN SERVICE",
        "NIFTY FINSRV25 50",
        "NIFTY FINSEREXBNK",
        "NIFTY FMCG",
        "NIFTY HEALTHCARE",
        "NIFTY IT",
        "NIFTY MEDIA",
        "NIFTY METAL",
        "NIFTY MS FIN SERV",
        "NIFTY MIDSML HLTH",
        "NIFTY MS IT TELCM",
        "NIFTY OIL AND GAS",
        "NIFTY PHARMA",
        "NIFTY PVT BANK",
        "NIFTY PSU BANK",
        "NIFTY REALTY",
        "NIFTY500 HEALTH"
    ],
    "Strategy Indices": [
       "NIFTY 50 ARBITRAGE",
        "NIFTY ALPHA 50",
        "NIFTY ALPHALOWVOL",
        "NIFTY AQL 30",
        "NIFTY AQLV 30",
        "NIFTY DIV OPPS 50",
        "NIFTY GROWSECT 15",
        "NIFTY HIGHBETA 50",
        "NIFTY LOW VOL 50",
        "NIFTYM150MOMNTM50",
        "NIFTY M150 QLTY50",
        "NIFTYMS400 MQ 100",
        "NIFTY QLTY LV 30",
        "NIFTYSML250MQ 100",
        "NIFTY SML250 Q50",
        "NIFTY TOP 10 EW",
        "NIFTY TOP 15 EW",
        "NIFTY TOP 20 EW",
        "NIFTY TMMQ 50",
        "NIFTY100 ALPHA 30",
        "NIFTY100 EQL WGT",
        "NIFTY100 LOWVOL30",
        "NIFTY100 QUALTY30",
        "NIFTY200 ALPHA 30",
        "NIFTY200MOMENTM30",
        "NIFTY200 QUALITY 30",
        "NIFTY200 VALUE 30",
        "NIFTY50 DIV POINT",
        "NIFTY50 EQL WGT",
        "NIFTY50 PR 1X INV",
        "NIFTY50 PR 2X LEV",
        "NIFTY50 TR 1X INV",
        "NIFTY50 TR 2X LEV",
        "NIFTY50 USD",
        "NIFTY50 VALUE 20",
        "NIFTY500 EW",
        "NIFTY500 FLEXICAP",
        "NIFTY500 LOWVOL50",
        "NIFTY500MOMENTM50",
        "NIFTY MULTI MQ 50",
        "NIFTY500 MQVLV50",
        "NIFTY500 QLTY50",
        "NIFTY500 VALUE 50"
    ],
    "Thematic Indices": [
         "NIFTY CAPITAL MKT",
        "NIFTY COMMODITIES",
        "NIFTY CONGLOMERATE 50",
        "NIFTY COREHOUSING",
        "NIFTY CPSE",
        "NIFTY ENERGY",
        "NIFTY EV",
        "NIFTY HOUSING",
        "NIFTY CONSUMPTION",
        "NIFTY INDIA CORPORATE GROUP INDEX - ADITYA BIRLA GROUP",
        "NIFTY INDIA CORPORATE GROUP INDEX - MAHINDRA GROUP",
        "NIFTY INDIA CORPORATE GROUP INDEX - TATA GROUP",
        "NIFTY TATA 25 CAP",
        "NIFTY IND DEFENCE",
        "NIFTY IND DIGITAL",
        "NIFTY INFRALOG",
        "NIFTY INTERNET",
        "NIFTY INDIA MFG",
        "NIFTY NEW CONSUMP",
        "NIFTY INDIA RAILWAYS PSU",
        "NIFTY CORP MAATR",
        "NIFTY IND TOURISM",
        "NIFTY INFRA",
        "NIFTY IPO",
        "NIFTY MID LIQ 15",
        "NIFTY MS IND CONS",
        "NIFTY MNC",
        "NIFTY MOBILITY",
        "NIFTY NONCYC CONS",
        "NIFTY PSE",
        "NIFTY REITS & INVITS",
        "NIFTY RURAL",
        "NIFTY SERV SECTOR",
        "NIFTY SHARIAH 25",
        "NIFTY SME EMERGE",
        "NIFTY TRANS LOGIS",
        "NIFTY WAVES",
        "NIFTY100 ENH ESG",
        "NIFTY100 ESG",
        "NIFTY100ESGSECLDR",
        "NIFTY100 LIQ 15",
        "NIFTY50 SHARIAH",
        "NIFTY MULTI MFG",
        "NIFTY MULTI INFRA",
        "NIFTY500 SHARIAH"
    ],
}

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def fmt(dt):
    return f"{dt.day:02d}-{MONTHS[dt.month-1]}-{dt.year}"

session = requests.Session()
session.headers.update({
    "Origin": "https://niftyindices.com",
    "Referer": "https://niftyindices.com/reports/historical-data",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Content-Type": "application/json; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
})

def fetch_tri(index_name, from_dt, to_dt):
    """Hits the hidden NIFTY POST endpoint."""
    # Handle the "INDEX" suffix requirement for certain Nifty indices
    name_val = index_name if index_name.endswith("INDEX") else f"{index_name} INDEX"
    
    payload = {"cinfo": f"{{'name':'{name_val}','startDate':'{fmt(from_dt)}','endDate':'{fmt(to_dt)}','indexName':'{index_name}'}}"}
    try:
        resp = session.post("https://niftyindices.com/Backpage.aspx/getTotalReturnIndexString", json=payload, timeout=30, verify=False)
        resp_data = resp.json()
        if "d" not in resp_data: return None
        
        data = json.loads(resp_data["d"])
        if not data: return None
        
        df = pd.DataFrame(data)
        # Handle inconsistent column naming from Nifty API
        val_col = next((c for c in ["TotalReturnsIndex", "NTR_Value", "Total_Returns_Index"] if c in df.columns), None)
        
        df = df[["Date", val_col]].copy()
        df.rename(columns={val_col: "Total_Returns_Index"}, inplace=True)
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)
        df["Total_Returns_Index"] = pd.to_numeric(df["Total_Returns_Index"].astype(str).str.replace(",", ""), errors="coerce")
        return df.dropna()
    except Exception as e:
        print(f"  Error fetching {index_name}: {e}")
        return None

def main():
    # 1. SKIP WEEKENDS (Market is closed)
    # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    if datetime.now().weekday() >= 5:
        print("Market is closed (Weekend). Skipping fetch.")
        return

    # 2. CALCULATE START DATE FROM PARQUET
    if os.path.exists(PARQUET_FILE):
        print(f"Reading existing data from {PARQUET_FILE}...")
        df_existing = pd.read_parquet(PARQUET_FILE)
        df_existing["Date"] = pd.to_datetime(df_existing["Date"])
        last_date = df_existing["Date"].max()
        start_fetch = last_date + timedelta(days=1)
        print(f"Last date in file: {last_date.strftime('%Y-%m-%d')}")
    else:
        print("No existing Parquet found. Starting full fetch.")
        df_existing = pd.DataFrame()
        start_fetch = INCEPTION_DATE

    # 3. CHECK IF UPDATE IS NECESSARY
    if start_fetch > END_DATE:
        print("Data is already up to date. No request needed.")
        return

    print(f"Fetching missing data from {fmt(start_fetch)} to {fmt(END_DATE)}...")

    # 4. FETCH LOOP
    new_frames = []
    for sub_index, indices in ALL_INDICES.items():
        for name in indices:
            df_new = fetch_tri(name, start_fetch, END_DATE)
            if df_new is not None and not df_new.empty:
                df_new["Index_Name"] = name
                df_new["Sub_Index"] = sub_index
                new_frames.append(df_new)
                print(f"  ✓ {name}: {len(df_new)} new rows.")
            time.sleep(random.uniform(0.5, 1.5)) # Polite delay

    # 5. MERGE, DEDUPLICATE AND SAVE
    if new_frames:
        df_new_all = pd.concat(new_frames, ignore_index=True)
        df_final = pd.concat([df_existing, df_new_all], ignore_index=True)
        
        # Strictly deduplicate to prevent issues with holidays/late-night runs
        df_final = df_final.drop_duplicates(subset=["Date", "Index_Name"])
        df_final = df_final.sort_values(["Date", "Index_Name"])
        
        os.makedirs("data", exist_ok=True)
        df_final.to_parquet(PARQUET_FILE, compression="snappy", index=False)
        print(f"Update complete. New total rows: {len(df_final)}")
    else:
        print("No new data points returned by API (could be a public holiday).")

if __name__ == "__main__":
    main()