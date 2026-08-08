"""
Aggregation
"""


# In[1]:


import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
 
import pandas as pd
import psycopg2


# In[3]:


# ══════════
# CONFIG
# ══════════
DB_URI = "postgresql://pipeline_user:me_dashboard@127.0.0.1:5432/me_dashboard"
OUTPUT_DIR = Path("dashboard_data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# In[11]:


# ═══════════════════════════
# THE 22 ECOSYSTEM SERVICES
# ═══════════════════════════

SERVICES_DEF = [
    ("Biochemicals",            "Provisioning"),
    ("Fibre/Hide/Wood",         "Provisioning"),
    ("Fuel",                    "Provisioning"),
    ("Potable Water",           "Provisioning"),
    ("Food",                    "Provisioning"),
    ("Biodiversity",            "Provisioning"),
    ("Disease Regulation",      "Regulating"),
    ("Waste Treatment",         "Regulating"),
    ("Climate Regulation",      "Regulating"),
    ("Atmospheric Regulation",  "Regulating"),
    ("Water Regulation",        "Regulating"),
    ("Pollination",             "Regulating"),
    ("Coastline Regulation",    "Regulating"),
    ("Primary Production",      "Supporting"),
    ("Soil Formation",          "Supporting"),
    ("Nutrient Cycling",        "Supporting"),
    ("Inspiration/Education",   "Cultural"),
    ("Aesthetic",               "Cultural"),
    ("Recreation",              "Cultural"),
    ("Cultural Heritage",       "Cultural"),
    ("Spiritual",               "Cultural"),
    ("Cultural Identity",       "Cultural"),
]
VALID_SERVICES = {name for name, _ in SERVICES_DEF}
SERVICE_TO_CATEGORY = dict(SERVICES_DEF)


# In[12]:


# ════════
# Helper
# ════════
def write_json(path: Path, payload: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


# In[13]:


# ═══════════════════════
# STEP 0 Connect
# ═══════════════════════

t0 = time.time()
conn = psycopg2.connect(DB_URI)


# In[14]:


# ════════════════════════════════════════════════════════════════
# STEP 1 corpus_meta.json — top-level funnel
# ════════════════════════════════════════════════════════════════

meta_sql = """
SELECT
    COUNT(*)                                                       AS total_papers,
    COUNT(*) FILTER (WHERE is_review = FALSE)                      AS non_review,
    COUNT(*) FILTER (WHERE is_review = TRUE)                       AS reviews
FROM papers
"""
meta_df = pd.read_sql(meta_sql, conn)
total      = int(meta_df["total_papers"][0])
non_review = int(meta_df["non_review"][0])
reviews    = int(meta_df["reviews"][0])
 
# Decision=Y count needs the classifications join
decision_y_sql = """
SELECT COUNT(*) AS decision_y
FROM papers p
JOIN classifications c ON p.wos_id = c.wos_id
WHERE p.is_review = FALSE
  AND c.is_current = TRUE
  AND c.decision = 'Y'
  AND c.ecosystem_service = ANY(%s)
"""
decision_y_df = pd.read_sql(decision_y_sql, conn, params=(list(VALID_SERVICES),))
decision_y = int(decision_y_df["decision_y"][0])

version_sql = "SELECT version FROM datasets ORDER BY import_date DESC LIMIT 1"
version_df = pd.read_sql(version_sql, conn)
dataset_version = version_df["version"][0] if len(version_df) else None
 
meta = {
    "total_papers":                      total,
    "non_review":                        non_review,
    "reviews":                           reviews,
    "decision_y":                        decision_y,
    "decision_y_pct_of_non_review":      round(decision_y / non_review, 4) if non_review else 0.0,
    "n_services":                        len(SERVICES_DEF),
    "dataset_version":                   dataset_version,
    "generated_at":                      datetime.now(timezone.utc).isoformat(timespec="seconds"),
}
write_json(OUTPUT_DIR / "corpus_meta.json", meta)
print(f"  total={total:,}  non_review={non_review:,}  decision_y={decision_y:,}")


# In[15]:


# ══════════════════════════════════════════════════════
# STEP 2 services_summary.json — 22 services × R/E/S
# ══════════════════════════════════════════════════════
 
# One row per (ecosystem_service, category) combo, filtered to non-review
# Y papers in the whitelist.
svc_sql = """
SELECT
    c.ecosystem_service,
    c.category,
    COUNT(*) AS n
FROM papers p
JOIN classifications c ON p.wos_id = c.wos_id
WHERE p.is_review = FALSE
  AND c.is_current = TRUE
  AND c.decision = 'Y'
  AND c.ecosystem_service = ANY(%s)
GROUP BY c.ecosystem_service, c.category
"""
raw = pd.read_sql(svc_sql, conn, params=(list(VALID_SERVICES),))
 
# Pivot to wide form: one row per service, three columns (R/E/S)
pivot = raw.pivot_table(
    index="ecosystem_service",
    columns="category",
    values="n",
    aggfunc="sum",
    fill_value=0,
).rename_axis(columns=None)
 
# Make sure all three columns exist even if a paradigm is empty for some service
for col in ("Replace", "Enhance", "Support"):
    if col not in pivot.columns:
        pivot[col] = 0
 
# Build the services list in the canonical SERVICES_DEF order. Any service
# defined but with zero papers (e.g. Spiritual, Cultural Identity) appears
# as a real row with zeros.

services_list = []
for svc_name, svc_category in SERVICES_DEF:
    if svc_name in pivot.index:
        row = pivot.loc[svc_name]
        replace_n = int(row["Replace"])
        enhance_n = int(row["Enhance"])
        support_n = int(row["Support"])
    else:
        replace_n = enhance_n = support_n = 0
    services_list.append({
        "service":  svc_name,
        "category": svc_category,
        "total":    replace_n + enhance_n + support_n,
        "replace":  replace_n,
        "enhance":  enhance_n,
        "support":  support_n,
    })
 
# Category-level and paradigm-level rollups
category_totals = {}
paradigm_totals = {"replace": 0, "enhance": 0, "support": 0}
for s in services_list:
    category_totals[s["category"]] = category_totals.get(s["category"], 0) + s["total"]
    paradigm_totals["replace"] += s["replace"]
    paradigm_totals["enhance"] += s["enhance"]
    paradigm_totals["support"] += s["support"]
 
summary = {
    "services":         services_list,
    "category_totals":  category_totals,
    "paradigm_totals":  paradigm_totals,
    "grand_total":      sum(s["total"] for s in services_list),
    "generated_at":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
}
write_json(OUTPUT_DIR / "services_summary.json", summary)
 
# Sanity check
assert summary["grand_total"] == decision_y, (
    f"Mismatch: grand_total={summary['grand_total']} vs decision_y={decision_y}. "
    "Likely cause: ecosystem_service value in classifications not in SERVICES_DEF."
)
print(f"  Services with data: {sum(1 for s in services_list if s['total'] > 0)} / {len(services_list)}")
print(f"  Grand total: {summary['grand_total']:,}  (== decision_y ✓)")
print(f"  Paradigms — Replace: {paradigm_totals['replace']:,}  "
      f"Enhance: {paradigm_totals['enhance']:,}  Support: {paradigm_totals['support']:,}")


# ════════════════════════════════════════════════════════════════
# STEP 2.5 annual_by_category.json — year × R/E/S for the narrative
# ════════════════════════════════════════════════════════════════
# One row per (pub_year, category) with non-review Decision=Y papers only.
# The narrative's stacked-area chart reads this.

annual_sql = """
SELECT
    p.pub_year,
    c.category,
    COUNT(*) AS n
FROM papers p
JOIN classifications c ON p.wos_id = c.wos_id
WHERE p.is_review = FALSE
  AND c.is_current = TRUE
  AND c.decision = 'Y'
  AND c.ecosystem_service = ANY(%s)
  AND p.pub_year IS NOT NULL
GROUP BY p.pub_year, c.category
ORDER BY p.pub_year, c.category
"""
annual_raw = pd.read_sql(annual_sql, conn, params=(list(VALID_SERVICES),))

# Pivot: rows = year, columns = Replace/Enhance/Support
annual_pivot = annual_raw.pivot_table(
    index="pub_year", columns="category", values="n",
    aggfunc="sum", fill_value=0,
).rename_axis(columns=None)
for col in ("Replace", "Enhance", "Support"):
    if col not in annual_pivot.columns:
        annual_pivot[col] = 0

annual_data = {
    "years":   [int(y) for y in annual_pivot.index],
    "replace": [int(x) for x in annual_pivot["Replace"]],
    "enhance": [int(x) for x in annual_pivot["Enhance"]],
    "support": [int(x) for x in annual_pivot["Support"]],
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
}
write_json(OUTPUT_DIR / "annual_by_category.json", annual_data)
print(f"  Years: {annual_data['years'][0]}–{annual_data['years'][-1]}  "
      f"({len(annual_data['years'])} years)")

# ════════════════════════════════════════════════════════════════
# STEP 2.6 country_oa.json — country × open-access for the map
# ════════════════════════════════════════════════════════════════
# For each country, aggregate Replace-oriented papers only:
#   • bubble size = # Replace papers with a first-author from that country
#   • colour      = % of those papers that are open access (open_access != 'Closed')
# The narrative's accessibility map reads this.

country_sql = """
SELECT
    (SELECT pf.feature_val
     FROM paper_features pf
     WHERE pf.wos_id = p.wos_id
       AND pf.feature_set = 'nlp_v1'
       AND pf.feature_key = 'country_first'
       AND pf.is_current  = TRUE
     LIMIT 1) AS country_first,
    p.open_access
FROM papers p
JOIN classifications c ON p.wos_id = c.wos_id
WHERE p.is_review = FALSE
  AND c.is_current = TRUE
  AND c.decision = 'Y'
  AND c.ecosystem_service = ANY(%s)
  AND c.category = 'Replace'
"""
country_raw = pd.read_sql(country_sql, conn, params=(list(VALID_SERVICES),))
country_raw = country_raw.dropna(subset=["country_first"])

# is_open: True when open_access has a non-null value other than 'Closed'
country_raw["is_open"] = (
    country_raw["open_access"].notna() & (country_raw["open_access"] != "Closed")
)

# Aggregate per country, then keep top 25 by Replace paper count —
# past that the bubble map gets crowded and unreadable.
country_agg = country_raw.groupby("country_first").agg(
    replace_papers=("is_open", "size"),
    open_papers=("is_open", "sum"),
).reset_index()
country_agg["open_access_pct"] = (
    country_agg["open_papers"] / country_agg["replace_papers"] * 100
).round(1)
country_agg = country_agg.sort_values("replace_papers", ascending=False).head(25)

# Global North / Global South split (traditional UN M49). WoS country_first
# values not listed here default to "Global South", which is the safer bias
# for coverage of newly emerging producers.
GLOBAL_NORTH = {
    "USA", "United States", "United States of America",
    "Canada",
    "United Kingdom", "England", "Scotland", "Wales", "Northern Ireland",
    "Germany", "France", "Italy", "Spain", "Netherlands", "Belgium", "Portugal",
    "Switzerland", "Austria", "Sweden", "Norway", "Denmark", "Finland", "Iceland",
    "Ireland", "Greece", "Luxembourg",
    "Poland", "Czech Republic", "Czechia", "Slovakia", "Hungary", "Slovenia",
    "Croatia", "Estonia", "Latvia", "Lithuania",
    "Australia", "New Zealand",
    "Japan", "South Korea", "Republic of Korea",
    "Israel", "Singapore",
}

country_list = []
for _, r in country_agg.iterrows():
    country_list.append({
        "country":         r["country_first"],
        "region":          "Global North" if r["country_first"] in GLOBAL_NORTH else "Global South",
        "replace_papers":  int(r["replace_papers"]),
        "open_access_pct": float(r["open_access_pct"]),
    })

country_oa = {
    "countries":    country_list,
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
}
write_json(OUTPUT_DIR / "country_oa.json", country_oa)
print(f"  Countries: {len(country_list)} (top-25 by Replace papers)")

# ════════════════════════════════════════════════════════════════
# STEP 2.7 support_spotlight.json — top-cited Support paper per curated service
# ════════════════════════════════════════════════════════════════
# The narrative's "3% spotlight" showcases four hand-picked Support-oriented
# services. For each, we surface (a) the total Support-paper count in that
# service and (b) the single most-cited Support paper. The narrative side
# supplies editorial framing (icon, curated title, body); 

SPOTLIGHT_SERVICES = [
    "Coastline Regulation",
    "Primary Production",
    "Pollination",
    "Water Regulation",
]

# ROW_NUMBER() partitioned by service picks the top-cited paper per service;
# tie-breaker is more recent publication year.
spotlight_sql = """
SELECT * FROM (
    SELECT
        c.ecosystem_service,
        COUNT(*) OVER (PARTITION BY c.ecosystem_service) AS n_in_service,
        p.wos_id, p.title, p.doi, p.pub_year, p.times_cited, p.authors,
        ROW_NUMBER() OVER (
            PARTITION BY c.ecosystem_service
            ORDER BY p.times_cited DESC NULLS LAST, p.pub_year DESC NULLS LAST
        ) AS rk
    FROM papers p
    JOIN classifications c ON p.wos_id = c.wos_id
    WHERE p.is_review = FALSE
      AND c.is_current = TRUE
      AND c.decision = 'Y'
      AND c.category = 'Support'
      AND c.ecosystem_service = ANY(%s)
      AND p.title IS NOT NULL
) t
WHERE rk = 1
"""
spot_top = pd.read_sql(spotlight_sql, conn, params=(SPOTLIGHT_SERVICES,))

def _first_author(authors_val):
    """Best-effort first-author extraction from a WoS authors field."""
    if pd.isna(authors_val) or not authors_val:
        return ""
    # WoS `authors` fields are typically pipe- or semicolon-separated; take
    # whatever comes before the first delimiter.
    for sep in (";", "|"):
        if sep in authors_val:
            first = authors_val.split(sep)[0].strip()
            return first
    return authors_val.strip()

spotlight_list = []
for svc in SPOTLIGHT_SERVICES:
    match = spot_top[spot_top["ecosystem_service"] == svc]
    if match.empty:
        print(f"No Support papers found for '{svc}' — skipping")
        continue
    row = match.iloc[0]
    spotlight_list.append({
        "service":  svc,
        "n_papers": int(row["n_in_service"]),
        "top_paper": {
            "wos_id":       row["wos_id"],
            "title":        row["title"],
            "doi":          row["doi"] if row["doi"] else None,
            "pub_year":     int(row["pub_year"]) if pd.notna(row["pub_year"]) else None,
            "times_cited":  int(row["times_cited"]) if pd.notna(row["times_cited"]) else 0,
            "first_author": _first_author(row["authors"]),
        },
    })

spotlight_out = {
    "spotlights":   spotlight_list,
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
}
write_json(OUTPUT_DIR / "support_spotlight.json", spotlight_out)
print(f"  Spotlight services: {len(spotlight_list)}/{len(SPOTLIGHT_SERVICES)}")

# In[16]:


# ════════════════════════════════════════════════════════════════
# STEP 3 papers_classified.parquet — explorer-grade row-level data
# ════════════════════════════════════════════════════════════════
 
papers_sql = """
SELECT
    p.wos_id,
    p.doi,
    p.title,
    p.pub_year,
    p.source_title,
    p.times_cited,
    p.open_access,
    p.authors,
    p.affiliations,
    p.wos_categories,
    p.keywords,
    p.addresses,
    p.funding_orgs,
    c.category,
    c.ecosystem_service,
    c.technology,
	-- Parsed WoS categories as a pipe-separated string for easy filtering
    -- (pipe '|' is safe because WoS category names never contain '|')
    COALESCE(
        (SELECT STRING_AGG(pf.feature_val, ' | ' ORDER BY pf.feature_val)
         FROM paper_features pf
         WHERE pf.wos_id = p.wos_id
           AND pf.feature_set = 'nlp_v1'
           AND pf.feature_key = 'wos_category'
           AND pf.is_current  = TRUE),
        p.wos_categories
    ) AS wos_categories_parsed,

    -- First-author country (single value, good for choropleth map)
    (SELECT pf.feature_val
     FROM paper_features pf
     WHERE pf.wos_id = p.wos_id
       AND pf.feature_set = 'nlp_v1'
       AND pf.feature_key = 'country_first'
       AND pf.is_current  = TRUE
     LIMIT 1
    ) AS country_first,

    -- All countries (pipe-separated, good for multi-country filtering)
    (SELECT STRING_AGG(pf.feature_val, ' | ' ORDER BY pf.feature_val)
     FROM paper_features pf
     WHERE pf.wos_id = p.wos_id
       AND pf.feature_set = 'nlp_v1'
       AND pf.feature_key = 'country'
       AND pf.is_current  = TRUE
    ) AS countries_all,

    -- First-author institution (single value, for filtering)
    (SELECT pf.feature_val
     FROM paper_features pf
     WHERE pf.wos_id = p.wos_id
       AND pf.feature_set = 'nlp_v1'
       AND pf.feature_key = 'institution_top'
       AND pf.is_current  = TRUE
     LIMIT 1
    ) AS institution_top,

    -- All institutions (pipe-separated)
    (SELECT STRING_AGG(pf.feature_val, ' | ' ORDER BY pf.feature_val)
     FROM paper_features pf
     WHERE pf.wos_id = p.wos_id
       AND pf.feature_set = 'nlp_v1'
       AND pf.feature_key = 'institution_all'
       AND pf.is_current  = TRUE
    ) AS institutions_all,

    -- Technology cluster (BERTopic-derived, 25 canonical categories)
    (SELECT pf.feature_val
     FROM paper_features pf
     WHERE pf.wos_id = p.wos_id
       AND pf.feature_set = 'nlp_v1'
       AND pf.feature_key = 'technology_cluster'
       AND pf.is_current  = TRUE
     LIMIT 1
    ) AS technology_cluster,

    -- Top funding agencies (pipe-separated, whitelist-matched)
    (SELECT STRING_AGG(pf.feature_val, ' | ' ORDER BY pf.feature_val)
     FROM paper_features pf
     WHERE pf.wos_id = p.wos_id
       AND pf.feature_set = 'nlp_v1'
       AND pf.feature_key = 'funding_top'
       AND pf.is_current  = TRUE
    ) AS funding_agencies
FROM papers p

JOIN classifications c ON p.wos_id = c.wos_id
WHERE p.is_review = FALSE
  AND c.is_current = TRUE
  AND c.decision = 'Y'
  AND c.ecosystem_service = ANY(%s)
"""
papers_df = pd.read_sql(papers_sql, conn, params=(list(VALID_SERVICES),))
 
# Add the 4-family category derived from the whitelist mapping.
papers_df["service_category"] = papers_df["ecosystem_service"].map(SERVICE_TO_CATEGORY)
 
# Column order for the explorer
COLUMN_ORDER = [
    "wos_id", "doi", "title", "pub_year",
    "source_title", "times_cited", "open_access",
    "authors", "affiliations", "wos_categories",
    "keywords", "addresses", "funding_orgs",
    "category", "ecosystem_service", "service_category", "technology",
    "wos_categories_parsed",
    "country_first",      # first-author country, single value
    "countries_all",      # all countries, pipe-separated
    "institution_top",    # first-author institution
    "institutions_all",   # all institutions, pipe-separated
    "technology_cluster",   # BERTopic cluster (25 categories)
    "funding_agencies",     # whitelist-matched funding agencies, pipe-separated
]
papers_df = papers_df[COLUMN_ORDER]
 
# Cast pub_year/times_cited to nullable Int (so missing values become <NA>
# instead of NaN floats — cleaner for the Streamlit explorer).
papers_df["pub_year"]    = papers_df["pub_year"].astype("Int64")
papers_df["times_cited"] = papers_df["times_cited"].astype("Int64")
 
# Sanity
assert len(papers_df) == decision_y, (
    f"Row count mismatch: parquet={len(papers_df)} vs decision_y={decision_y}"
)
 
parquet_path = OUTPUT_DIR / "papers_classified.parquet"
papers_df.to_parquet(parquet_path, compression="snappy", index=False)
 
size_mb = os.path.getsize(parquet_path) / (1024 * 1024)
print(f"  Rows: {len(papers_df):,}")
print(f"  Cols: {len(papers_df.columns)}  -> {COLUMN_ORDER}")
print(f"  Size: {size_mb:.1f} MB (snappy-compressed parquet)")


# In[17]:


# ═════════════════
# Done
# ═════════════════
conn.close()
elapsed = time.time() - t0
print(f"\n✓ All files written to {OUTPUT_DIR.resolve()}/")
for fname in ("corpus_meta.json", "services_summary.json", "annual_by_category.json", "country_oa.json", "support_spotlight.json", "papers_classified.parquet"):
    fpath = OUTPUT_DIR / fname
    size = os.path.getsize(fpath) / 1024  # KB
    unit = "KB" if size < 1024 else "MB"
    val  = size if size < 1024 else size / 1024
    print(f"  {fname:32s} {val:>7.1f} {unit}")
print(f"\n  Total elapsed: {elapsed:.1f}s")
