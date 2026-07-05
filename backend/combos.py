"""
Run this once to discover all valid (maturityType, category, subCategory) combos.
Prints a summary and the exact COMBOS list to paste into amfi_scraper.py.

    pip install requests pandas
    python discover_combos.py
"""

import requests
import json
import time
from datetime import date

API_URL     = "https://www.amfiindia.com/gateway/pollingsebi/api/amfi/fundperformance"
SESSION_URL = "https://www.amfiindia.com/polling/amfi/fund-performance"

HEADERS = {
    "User-Agent":        "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
    "sec-ch-ua":         '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
    "sec-ch-ua-mobile":  "?1",
    "sec-ch-ua-platform": '"Android"',
    "sec-fetch-dest":    "empty",
    "sec-fetch-mode":    "cors",
    "sec-fetch-site":    "same-origin",
    "Accept-Encoding":   "gzip, deflate, br, zstd",
    "Accept-Language":   "en-US,en;q=0.9",
    "Referer":           SESSION_URL,
    "Origin":            "https://www.amfiindia.com",
    "Accept":            "application/json, text/plain, */*",
    "Content-Type":      "application/json",
}

# Probe range — widen if you think there are more
MATURITY_TYPES  = [1, 2, 3]
CATEGORIES      = list(range(1, 10))  # 1-9
SUB_CATEGORIES  = list(range(1, 100))  # 1-15

REPORT_DATE = date(2026, 7, 2).strftime("%d-%b-%Y")  # e.g. "02-Jul-2026"

session = requests.Session()
valid_combos = []
total_schemes = set()

print(f"Probing on {REPORT_DATE} ...\n")
print(f"{'mt':>4} {'cat':>4} {'sub':>4}  {'schemes':>8}  sample name")
print("-" * 70)

for mt in MATURITY_TYPES:
    for cat in CATEGORIES:
        for sub in SUB_CATEGORIES:
            time.sleep(0.3)
            payload = {
                "maturityType": mt, "category": cat,
                "subCategory": sub, "mfid": 0, "reportDate": REPORT_DATE
            }
            try:
                r = session.post(API_URL, json=payload, headers=HEADERS, timeout=20)
                if r.status_code != 200:
                    continue
                data = r.json()
                if data.get("validationStatus") != "SUCCESS":
                    continue
                rows = data.get("data") or []
                if not rows:
                    continue

                names = [row.get("schemeName", "") for row in rows]
                total_schemes.update(names)
                valid_combos.append((mt, cat, sub, len(rows)))
                sample = names[0][:45] if names else ""
                print(f"{mt:>4} {cat:>4} {sub:>4}  {len(rows):>8}  {sample}")

            except Exception as e:
                print(f"{mt:>4} {cat:>4} {sub:>4}  ERROR: {e}")

print("\n" + "=" * 70)
print(f"Valid combos found: {len(valid_combos)}")
print(f"Total unique scheme names across all combos: {len(total_schemes)}")
print(f"Total requests per day if scraping all combos: {len(valid_combos)}")

print("\n\n# ── Paste this into amfi_scraper.py ──")
print("COMBOS = [")
for mt, cat, sub, count in valid_combos:
    print(f"    ({mt}, {cat}, {sub}),  # {count} schemes")
print("]")