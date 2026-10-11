"""
python build_mf_monthly.py mf_nav.parquet      # or .csv
-> mf_monthly_growth_nav.parquet  (one NAV per fund per month, Regular/Growth, classified)
"""
import re, sys
import pandas as pd

SRC = sys.argv[1] if len(sys.argv) > 1 else "mf_nav.parquet"
OUT = "mf_monthly_growth_nav.parquet"

CATEGORY_KEYWORDS = {
    "Large-Cap": ["Equity Scheme - Large Cap Fund", "Equity Schemes - Large Cap Fund"],
    "Mid-Cap": ["Equity Scheme - Mid Cap Fund", "Equity Schemes - Mid Cap Fund"],
    "Small-Cap": ["Equity Scheme - Small Cap Fund", "Equity Schemes - Small Cap Fund"],
    "Flexi-Cap & Multi-Cap": [
        "Equity Scheme - Flexi Cap Fund", "Equity Schemes - Flexi Cap Fund",
        "Equity Scheme - Multi Cap Fund", "Equity Schemes - Multi Cap Fund",
    ],
    "Thematic": [
        "Equity Schemes - Sectoral Fund", "Equity Schemes - Thematic Fund",
        "Equity Scheme - Sectoral/ Thematic",
    ],
    "ELSS": ["Equity Schemes - ELSS- Tax Saver Fund", "Equity Scheme - ELSS", "ELSS"],
    "International": [
        "Fund of Funds - Overseas", "Other Scheme - FoF Overseas",
        "Overseas Fund of Funds - Fund of Funds investing overseas",
    ],
}

def norm(s) -> str:                       # "Equity Scheme - Sectoral/ Thematic" -> "equity scheme sectoral thematic"
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()

PATTERNS = {
    cls: re.compile("|".join(rf"(?<![a-z0-9]){re.escape(norm(k))}(?![a-z0-9])" for k in kws))
    for cls, kws in CATEGORY_KEYWORDS.items()
}

def classify(text):
    t = norm(text)
    for cls, pat in PATTERNS.items():
        if pat.search(t):
            return cls
    return None

# ── load ─────────────────────────────────────────────────────────────────────
df = pd.read_parquet(SRC) if SRC.endswith(".parquet") else pd.read_csv(SRC, low_memory=False)
for c in ("plan", "option", "category", "amc"):
    if c not in df.columns:
        df[c] = None
df["date"] = pd.to_datetime(df["date"])
df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
df["scheme_code"] = pd.to_numeric(df["scheme_code"], errors="coerce")
df = df[(df["nav"] > 0) & df["scheme_code"].notna()].copy()
df["scheme_code"] = df["scheme_code"].astype("int64")
df = df.sort_values(["scheme_code", "date"])

# ── scheme-level table: latest name/plan/option, latest non-null category ────
sch = df.drop_duplicates("scheme_code", keep="last").set_index("scheme_code")[
    ["scheme_name", "amc", "plan", "option"]
]
sch["category"] = df.dropna(subset=["category"]).groupby("scheme_code")["category"].last()

name = sch["scheme_name"].fillna("").str.lower()
plan = sch["plan"].fillna("").astype(str).str.lower()
opt = sch["option"].fillna("").astype(str).str.lower()

is_growth = opt.str.contains("growth") | name.str.contains(r"\bgrowth\b")
is_direct = plan.str.contains("direct") | name.str.contains(r"\bdirect\b")
is_bad = name.str.contains(r"\b(?:idcw|bonus|payout|reinvest\w*|institutional|segregated)\b")
sch["is_rg"] = is_growth & ~is_direct & ~is_bad          # Regular (or single-plan) + Growth

sch["fund_class"] = [
    classify(c) or classify(n)
    for c, n in zip(sch["category"].fillna(""), sch["scheme_name"].fillna(""))
]
keep = sch[sch["is_rg"] & sch["fund_class"].notna()]

# ── month-end collapse: last available NAV per scheme per month ─────────────
d = df[df["scheme_code"].isin(keep.index)].copy()
d["month"] = d["date"].dt.to_period("M").dt.end_time.dt.normalize()
d = d.drop_duplicates(["scheme_code", "month"], keep="last")        # df already sorted by date
out = d[["scheme_code", "month", "nav"]].merge(
    keep[["scheme_name", "amc", "fund_class"]], left_on="scheme_code", right_index=True
)
out.to_parquet(OUT, index=False, compression="zstd")

# ── report ───────────────────────────────────────────────────────────────────
print(f"{len(out):,} rows, {out['scheme_code'].nunique()} schemes -> {OUT}")
print(keep["fund_class"].value_counts())
miss = sch[sch["is_rg"] & sch["fund_class"].isna()]["category"].fillna("(null)")
print("\nUnclassified Regular/Growth categories (extend CATEGORY_KEYWORDS if any are equity):")
print(miss[miss.str.contains("equity|elss|fund of funds|(null)", case=False)].value_counts().head(25))