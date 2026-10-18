"""
Build the dashboard data files from the Postgres corpus.

Runs as a script (all work happens at import). Requires DATABASE_URL and writes
JSON and parquet files to ./dashboard_data (relative to the working directory):
the narrative JSONs (corpus_meta, services_summary, annual_by_category, country_oa,
support_spotlight, wos_discovery, wos_cooccurrence, framing_discovery, framing)
and the Explorer parquet files (papers_classified, abstracts).

Narrative outputs read classifications_narrative_snapshot; the Explorer parquet
files read all current rows of classifications.

Usage:
    export DATABASE_URL="postgresql://user:password@host:5432/dbname"
    python aggregate.py
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
 
import pandas as pd
import psycopg2


# Configuration
import os as _os
DB_URI = _os.environ.get("DATABASE_URL")
if not DB_URI:
    raise EnvironmentError(
        "DATABASE_URL is not set.\n"
        "  export DATABASE_URL='postgresql://user:password@host:5432/dbname'\n"
        "Never hardcode credentials in this file."
    )
OUTPUT_DIR = Path("dashboard_data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Narrative outputs must not change when incremental papers are ingested: they read
# classifications_narrative_snapshot, and the corpus_meta paper counts filter on
# LEGACY_DATASET_IDS (dataset_id of the original historical load). Only the Explorer
# files (STEP 6, 6b) read all current classifications.
LEGACY_DATASET_IDS = [1]

if not LEGACY_DATASET_IDS:
    raise ValueError(
        "LEGACY_DATASET_IDS is empty. This must be set to the dataset_id(s) "
        "of the original historical import before running aggregate.py, or "
        "every narrative statistic will silently include incremental data "
        "the moment ingest_incremental.py has run once. Run:\n"
        "  SELECT dataset_id, source, version, import_date, record_count "
        "FROM datasets ORDER BY import_date;\n"
        "and set LEGACY_DATASET_IDS to the historical row's dataset_id."
    )


# (service, category) pairs; also the whitelist of valid ecosystem_service values.
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


def write_json(path: Path, payload: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


# STEP 0: database connection
t0 = time.time()
conn = psycopg2.connect(DB_URI)


# STEP 1: corpus_meta.json
meta_sql = """
SELECT
    COUNT(*)                                                       AS total_papers,
    COUNT(*) FILTER (WHERE is_review = FALSE)                      AS non_review,
    COUNT(*) FILTER (WHERE is_review = TRUE)                       AS reviews
FROM papers
WHERE dataset_id = ANY(%s)
"""
meta_df = pd.read_sql(meta_sql, conn, params=(LEGACY_DATASET_IDS,))
total      = int(meta_df["total_papers"][0])
non_review = int(meta_df["non_review"][0])
reviews    = int(meta_df["reviews"][0])
 
decision_y_sql = """
SELECT COUNT(*) AS decision_y
FROM papers p
JOIN classifications_narrative_snapshot c ON p.wos_id = c.wos_id
WHERE p.is_review = FALSE
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


# STEP 2: services_summary.json
svc_sql = """
SELECT
    c.ecosystem_service,
    c.category,
    COUNT(*) AS n
FROM papers p
JOIN classifications_narrative_snapshot c ON p.wos_id = c.wos_id
WHERE p.is_review = FALSE
  AND c.decision = 'Y'
  AND c.ecosystem_service = ANY(%s)
GROUP BY c.ecosystem_service, c.category
"""
raw = pd.read_sql(svc_sql, conn, params=(list(VALID_SERVICES),))
 
pivot = raw.pivot_table(
    index="ecosystem_service",
    columns="category",
    values="n",
    aggfunc="sum",
    fill_value=0,
).rename_axis(columns=None)
 
# Ensure all three paradigm columns exist even if one has no rows.
for col in ("Replace", "Enhance", "Support"):
    if col not in pivot.columns:
        pivot[col] = 0
 
# Emit services in SERVICES_DEF order; services with no papers get zero counts.

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
 
# Sanity check against STEP 1 decision_y.
assert summary["grand_total"] == decision_y, (
    f"Mismatch: grand_total={summary['grand_total']} vs decision_y={decision_y}. "
    "Likely cause: ecosystem_service value in classifications not in SERVICES_DEF."
)
print(f"  Services with data: {sum(1 for s in services_list if s['total'] > 0)} / {len(services_list)}")
print(f"  Grand total: {summary['grand_total']:,}  (== decision_y ✓)")
print(f"  Paradigms — Replace: {paradigm_totals['replace']:,}  "
      f"Enhance: {paradigm_totals['enhance']:,}  Support: {paradigm_totals['support']:,}")


# STEP 3: annual_by_category.json

annual_sql = """
SELECT
    p.pub_year,
    c.category,
    COUNT(*) AS n
FROM papers p
JOIN classifications_narrative_snapshot c ON p.wos_id = c.wos_id
WHERE p.is_review = FALSE
  AND c.decision = 'Y'
  AND c.ecosystem_service = ANY(%s)
  AND p.pub_year IS NOT NULL
GROUP BY p.pub_year, c.category
ORDER BY p.pub_year, c.category
"""
annual_raw = pd.read_sql(annual_sql, conn, params=(list(VALID_SERVICES),))

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

# STEP 4: country_oa.json
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
JOIN classifications_narrative_snapshot c ON p.wos_id = c.wos_id
WHERE p.is_review = FALSE
  AND c.decision = 'Y'
  AND c.ecosystem_service = ANY(%s)
  AND c.category = 'Replace'
"""
country_raw = pd.read_sql(country_sql, conn, params=(list(VALID_SERVICES),))
country_raw = country_raw.dropna(subset=["country_first"])

country_raw["is_open"] = (
    country_raw["open_access"].notna() & (country_raw["open_access"] != "Closed")
)

# Keep the top 25 countries by Replace paper count (map readability).
country_agg = country_raw.groupby("country_first").agg(
    replace_papers=("is_open", "size"),
    open_papers=("is_open", "sum"),
).reset_index()
country_agg["open_access_pct"] = (
    country_agg["open_papers"] / country_agg["replace_papers"] * 100
).round(1)
country_agg = country_agg.sort_values("replace_papers", ascending=False).head(25)

# Countries not listed in GLOBAL_NORTH are labelled "Global South".
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

# STEP 5: support_spotlight.json (top-cited Support paper per curated service)
SPOTLIGHT_SERVICES = [
    "Coastline Regulation",
    "Primary Production",
    "Pollination",
    "Water Regulation",
]

# Ties on times_cited are broken by most recent pub_year.
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
    JOIN classifications_narrative_snapshot c ON p.wos_id = c.wos_id
    WHERE p.is_review = FALSE
      AND c.decision = 'Y'
      AND c.category = 'Support'
      AND c.ecosystem_service = ANY(%s)
      AND p.title IS NOT NULL
) t
WHERE rk = 1
"""
spot_top = pd.read_sql(spotlight_sql, conn, params=(SPOTLIGHT_SERVICES,))

def _first_author(authors_val):
    """First author from a ';' or '|' separated authors field ('' if missing)."""
    if pd.isna(authors_val) or not authors_val:
        return ""
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


# STEP 6: papers_classified.parquet (Explorer; all current classifications)
papers_sql = """
SELECT
    p.wos_id,
    p.doi,
    p.dataset_id,
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
 
# Service family from SERVICES_DEF.
papers_df["service_category"] = papers_df["ecosystem_service"].map(SERVICE_TO_CATEGORY)

# This step reads all current classifications, so it is checked against its own
# count rather than the STEP 1 decision_y.
decision_y_all_sql = """
SELECT COUNT(*) AS decision_y_all
FROM papers p
JOIN classifications c ON p.wos_id = c.wos_id
WHERE p.is_review = FALSE
  AND c.is_current = TRUE
  AND c.decision = 'Y'
  AND c.ecosystem_service = ANY(%s)
"""
decision_y_all = int(pd.read_sql(decision_y_all_sql, conn, params=(list(VALID_SERVICES),))["decision_y_all"][0])
 
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
 
# Nullable Int64 so missing values are <NA> rather than float NaN.
papers_df["pub_year"]    = papers_df["pub_year"].astype("Int64")
papers_df["times_cited"] = papers_df["times_cited"].astype("Int64")
 
assert len(papers_df) == decision_y_all, (
    f"Row count mismatch: parquet={len(papers_df)} vs decision_y_all={decision_y_all}"
)
 
parquet_path = OUTPUT_DIR / "papers_classified.parquet"
papers_df.to_parquet(parquet_path, compression="snappy", index=False)
 
size_mb = os.path.getsize(parquet_path) / (1024 * 1024)
print(f"  Rows: {len(papers_df):,}")
print(f"  Cols: {len(papers_df.columns)}  -> {COLUMN_ORDER}")
print(f"  Size: {size_mb:.1f} MB (snappy-compressed parquet)")


# STEP 6b: abstracts.parquet (same rows as STEP 6 that have an abstract)
abstracts_sql = """
SELECT p.wos_id, p.abstract
FROM papers p
JOIN classifications c ON p.wos_id = c.wos_id
WHERE p.is_review = FALSE
  AND c.is_current = TRUE
  AND c.decision = 'Y'
  AND c.ecosystem_service = ANY(%s)
  AND p.abstract IS NOT NULL
"""
abstracts_df = pd.read_sql(abstracts_sql, conn, params=(list(VALID_SERVICES),))

abstracts_path = OUTPUT_DIR / "abstracts.parquet"
abstracts_df.to_parquet(abstracts_path, compression="snappy", index=False)

abstracts_size_mb = os.path.getsize(abstracts_path) / (1024 * 1024)
print(f"  Rows: {len(abstracts_df):,} (of {len(papers_df):,} explorer papers — "
      f"{len(papers_df) - len(abstracts_df):,} have no abstract)")
print(f"  Size: {abstracts_size_mb:.1f} MB (snappy-compressed parquet)")


# wos_discovery.json: top WoS categories, paradigm mix and pairwise co-occurrence

from collections import Counter
from itertools import combinations

TOP_N_DISCOVERY = 25

# Reads the narrative snapshot, so the output is unaffected by incremental papers.
legacy_discovery_sql = """
SELECT
    p.wos_id,
    COALESCE(
        (SELECT STRING_AGG(pf.feature_val, ' | ' ORDER BY pf.feature_val)
         FROM paper_features pf
         WHERE pf.wos_id = p.wos_id
           AND pf.feature_set = 'nlp_v1'
           AND pf.feature_key = 'wos_category'
           AND pf.is_current  = TRUE),
        p.wos_categories
    ) AS wos_categories_parsed,
    c.category
FROM papers p
JOIN classifications_narrative_snapshot c ON p.wos_id = c.wos_id
WHERE p.is_review = FALSE
  AND c.decision = 'Y'
  AND c.ecosystem_service = ANY(%s)
"""
_legacy_papers_df = pd.read_sql(legacy_discovery_sql, conn, params=(list(VALID_SERVICES),))


def _split_wos(val):
    if pd.isna(val) or not val:
        return []
    return [c.strip() for c in str(val).split("|") if c.strip()]

_disc_df = _legacy_papers_df[["wos_categories_parsed", "category"]].copy()
_disc_df["wos_cats"] = _disc_df["wos_categories_parsed"].map(_split_wos)

# One row per (paper, WoS category) pair.
_exp = _disc_df.explode("wos_cats").dropna(subset=["wos_cats"])
cat_stats = _exp.groupby("wos_cats").agg(
    n_papers  = ("category", "size"),
    n_replace = ("category", lambda x: (x == "Replace").sum()),
    n_enhance = ("category", lambda x: (x == "Enhance").sum()),
    n_support = ("category", lambda x: (x == "Support").sum()),
).reset_index().sort_values("n_papers", ascending=False)

top_cats     = cat_stats.head(TOP_N_DISCOVERY).copy()
top_cats_set = set(top_cats["wos_cats"])

# Co-occurrence counts for unordered pairs of top-N categories within a paper.
cooccur = Counter()
for cats in _disc_df["wos_cats"]:
    in_top = sorted({c for c in cats if c in top_cats_set})
    for a, b in combinations(in_top, 2):
        cooccur[(a, b)] += 1

categories_out = []
for _, row in top_cats.iterrows():
    total_para = int(row["n_replace"] + row["n_enhance"] + row["n_support"])
    dom = max(
        ("Replace", row["n_replace"]),
        ("Enhance", row["n_enhance"]),
        ("Support", row["n_support"]),
        key=lambda x: x[1],
    )[0]
    categories_out.append({
        "raw_name":          row["wos_cats"],
        "n_papers":          int(row["n_papers"]),
        "n_replace":         int(row["n_replace"]),
        "n_enhance":         int(row["n_enhance"]),
        "n_support":         int(row["n_support"]),
        "replace_pct":       round(row["n_replace"] / total_para, 3) if total_para else 0,
        "enhance_pct":       round(row["n_enhance"] / total_para, 3) if total_para else 0,
        "support_pct":       round(row["n_support"] / total_para, 3) if total_para else 0,
        "dominant_paradigm": dom,
    })

edges_out = [
    {"a": a, "b": b, "cooccur": int(n)}
    for (a, b), n in sorted(cooccur.items(), key=lambda x: x[1], reverse=True)
]

discovery_out = {
    "top_n":         TOP_N_DISCOVERY,
    "categories":    categories_out,
    "cooccurrences": edges_out,
    "generated_at":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
}
write_json(OUTPUT_DIR / "wos_discovery.json", discovery_out)

print(f"\n── WoS discovery · top {TOP_N_DISCOVERY} categories ──")
print(f"{'#':>2}  {'category':<45s}  {'papers':>7}  {'R':>5}  {'E':>5}  {'S':>5}  dom")
for i, c in enumerate(categories_out, 1):
    print(f"{i:>2}  {c['raw_name'][:45]:<45s}  {c['n_papers']:>7,}  "
          f"{c['replace_pct']:>5.0%}  {c['enhance_pct']:>5.0%}  {c['support_pct']:>5.0%}  "
          f"{c['dominant_paradigm']}")

print(f"\n── Top 25 co-occurrence pairs ──")
for e in edges_out[:25]:
    print(f"  {e['a'][:38]:<38s}  ↔  {e['b'][:38]:<38s}  {e['cooccur']:>6,}")


# wos_cooccurrence.json: network nodes and edges built from the discovery data above.
# Clusters are hand-assigned; edges need both endpoints in the top-N nodes and
# co-occurrence >= EDGE_THRESHOLD_NET.
CLUSTER_MAP = {
    "Materials Science, Multidisciplinary": "Hard-Sci",
    "Chemistry, Multidisciplinary":         "Hard-Sci",
    "Nanoscience & Nanotechnology":         "Hard-Sci",
    "Chemistry, Physical":                  "Hard-Sci",
    "Physics, Applied":                     "Hard-Sci",
    "Physics, Condensed Matter":            "Hard-Sci",
    "Polymer Science":                      "Hard-Sci",
    "Chemistry, Organic":                   "Hard-Sci",
    "Chemistry, Analytical":                "Hard-Sci",
    "Chemistry, Inorganic & Nuclear":       "Hard-Sci",
    "Chemistry, Applied":                   "Hard-Sci",

    "Materials Science, Biomaterials":      "Bio-Applied",
    "Engineering, Biomedical":              "Bio-Applied",
    "Cell & Tissue Engineering":            "Bio-Applied",
    "Cell Biology":                         "Bio-Applied",
    "Biotechnology & Applied Microbiology": "Bio-Applied",
    "Biochemistry & Molecular Biology":     "Bio-Applied",
    "Biophysics":                           "Bio-Applied",
    "Pharmacology & Pharmacy":              "Bio-Applied",

    "Robotics":                             "Applied-Eng",
    "Engineering, Chemical":                "Applied-Eng",
    "Engineering, Environmental":           "Applied-Eng",
    "Engineering, Multidisciplinary":       "Applied-Eng",
    "Multidisciplinary Sciences":           "Applied-Eng",
    "Energy & Fuels":                       "Applied-Eng",
}

# Short chart labels for WoS category names.
DISPLAY_NAMES = {
    "Materials Science, Multidisciplinary": "Materials Sci.",
    "Chemistry, Multidisciplinary":         "Chemistry",
    "Nanoscience & Nanotechnology":         "Nanoscience",
    "Chemistry, Physical":                  "Physical Chem.",
    "Physics, Applied":                     "Physics (Applied)",
    "Physics, Condensed Matter":            "Physics (Cond. Matter)",
    "Polymer Science":                      "Polymer Sci.",
    "Chemistry, Organic":                   "Organic Chem.",
    "Chemistry, Analytical":                "Analytical Chem.",
    "Chemistry, Inorganic & Nuclear":       "Inorganic Chem.",
    "Chemistry, Applied":                   "Applied Chem.",
    "Materials Science, Biomaterials":      "Biomaterials",
    "Engineering, Biomedical":              "Biomedical Eng.",
    "Cell & Tissue Engineering":            "Cell/Tissue Eng.",
    "Cell Biology":                         "Cell Biology",
    "Biotechnology & Applied Microbiology": "Biotech",
    "Biochemistry & Molecular Biology":     "Biochemistry",
    "Biophysics":                           "Biophysics",
    "Pharmacology & Pharmacy":              "Pharmacology",
    "Robotics":                             "Robotics",
    "Engineering, Chemical":                "Chem. Eng.",
    "Engineering, Environmental":           "Env. Eng.",
    "Engineering, Multidisciplinary":       "Eng. (Multi.)",
    "Multidisciplinary Sciences":           "Multi-Sci.",
    "Energy & Fuels":                       "Energy",
}

EDGE_THRESHOLD_NET = 200        # min co-occurrences to keep an edge
TOP_N_NET          = 25         # number of top categories used as nodes

_net_cats = categories_out[:TOP_N_NET]
_net_names = {c["raw_name"] for c in _net_cats}

nodes_net = []
for c in _net_cats:
    raw = c["raw_name"]
    cluster = CLUSTER_MAP.get(raw)
    if cluster is None:
        print(f"  ⚠ '{raw}' has no cluster in CLUSTER_MAP — skipping")
        continue
    nodes_net.append({
        "raw_name":          raw,
        "display":           DISPLAY_NAMES.get(raw, raw),
        "cluster":           cluster,
        "n_papers":          c["n_papers"],
        "dominant_paradigm": c["dominant_paradigm"],
        "replace_pct":       c["replace_pct"],
        "enhance_pct":       c["enhance_pct"],
        "support_pct":       c["support_pct"],
    })

edges_net = []
for e in edges_out:
    if e["a"] in _net_names and e["b"] in _net_names and e["cooccur"] >= EDGE_THRESHOLD_NET:
        a_cluster = CLUSTER_MAP.get(e["a"])
        b_cluster = CLUSTER_MAP.get(e["b"])
        edges_net.append({
            "a":       e["a"],
            "b":       e["b"],
            "cooccur": e["cooccur"],
            "cross":   a_cluster != b_cluster,
        })

# eco_absence.pure_ecology_present is hardcoded False, not computed.
env_eng_papers = next((c["n_papers"] for c in categories_out
                       if c["raw_name"] == "Engineering, Environmental"), 0)
env_eng_rank = next((i + 1 for i, c in enumerate(categories_out)
                     if c["raw_name"] == "Engineering, Environmental"), None)

net_out = {
    "top_n_baked":     TOP_N_NET,
    "edge_threshold":  EDGE_THRESHOLD_NET,
    "nodes":           nodes_net,
    "edges":           edges_net,
    "eco_absence": {
        "env_eng_papers":     env_eng_papers,
        "env_eng_rank":       env_eng_rank,
        "corpus_total":       decision_y,
        "pure_ecology_present": False,
    },
    "generated_at":    datetime.now(timezone.utc).isoformat(timespec="seconds"),
}
write_json(OUTPUT_DIR / "wos_cooccurrence.json", net_out)
print(f"  Network nodes: {len(nodes_net)}, edges (≥{EDGE_THRESHOLD_NET}): {len(edges_net)}")

# framing_discovery.json: terms that distinguish Replace from Support abstracts
# (Enhance excluded). Abstracts are lowercased and regex-tokenised; stopwords are
# dropped before bigrams are formed. Unigrams are stemmed with simple_stem, bigrams
# keep surface forms. Terms need a minimum total count and are ranked by the
# log-ratio of per-1k frequencies.

import re
import math
from collections import Counter, defaultdict

MIN_ABSTRACT_CHARS = 100
MIN_TOTAL_UNIGRAM  = 100
MIN_TOTAL_BIGRAM   = 50
TOP_PER_SIDE       = 20

STANDARD_STOPWORDS = {
    "a", "an", "the",
    "i", "you", "he", "she", "it", "we", "they",
    "me", "him", "her", "us", "them",
    "this", "that", "these", "those",
    "my", "your", "his", "its", "our", "their",
    "is", "are", "was", "were", "be", "been", "being",
    "am", "has", "have", "had", "do", "does", "did",
    "will", "would", "shall", "should", "may", "might",
    "must", "can", "could",
    "of", "in", "on", "at", "to", "from", "by", "for",
    "with", "about", "into", "through", "between", "within",
    "and", "or", "but", "if", "then", "so", "because", "as",
    "than", "though", "although", "since", "unless",
    "not", "no", "own", "same", "other", "some", "any", "all",
    "most", "more", "less", "few", "both", "each", "such",
    "when", "where", "why", "how", "which", "who", "whom", "whose",
    "here", "there", "now", "very",
}

PAPER_STOPWORDS = {
    # Meta
    "paper", "study", "article", "work", "research", "method", "methods",
    "approach", "approaches", "results", "result", "conclusion",
    "conclusions", "abstract", "section",
    # Reporting verbs (and their forms)
    "show", "showed", "shown", "shows",
    "present", "presented", "presents",
    "propose", "proposed", "proposes", "proposal",
    "describe", "described", "describes",
    "report", "reported", "reports",
    "demonstrate", "demonstrated", "demonstrates",
    "find", "finds", "found",
    "investigate", "investigates", "investigated",
    "examine", "examines", "examined",
    "analyze", "analyzes", "analyzed", "analysed", "analyses",
    "discuss", "discusses", "discussed",
    "observe", "observes", "observed",
    "consider", "considers", "considered",
    "obtain", "obtains", "obtained",
    "provide", "provides", "provided",
    "allow", "allows", "allowed",
    "offer", "offers", "offered",
    "use", "uses", "used", "using", "usage",
    "give", "gives", "given", "gave",
    "make", "makes", "made", "making",
    # Discourse markers
    "however", "therefore", "thus", "furthermore", "moreover",
    "additionally", "thereby", "hence", "meanwhile", "whereas",
    # Vague qualifiers
    "various", "several", "many", "much", "different", "similar",
    "common", "general", "specific", "important", "significant",
    "main", "major", "minor", "key", "certain", "particular",
    "high", "higher", "highest", "low", "lower", "lowest",
    "large", "larger", "largest", "small", "smaller", "smallest",
    "good", "better", "best", "well", "great",
    "one", "two", "three", "four", "five",
    "first", "second", "third", "next", "final",
    "also", "only", "just", "even", "still",
    # Publication scaffolding
    "fig", "figure", "figures", "table", "tables",
    "ref", "refs", "references", "cited", "doi",
    "et", "al",
    # Filler
    "based", "compared", "including", "included",
    "respectively", "possible", "possibly",
    "new", "novel",
}
STOPWORDS = STANDARD_STOPWORDS | PAPER_STOPWORDS


def simple_stem(word):
    """Strip one common suffix (ing, ies, ed, es, s ...); words under 5 chars unchanged."""
    if len(word) < 5:
        return word
    for suf in ("ings", "ing", "ies", "ied", "eds", "ed", "es", "s"):
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[:-len(suf)]
    return word


framing_sql = """
SELECT p.wos_id, p.abstract, c.category
FROM papers p
JOIN classifications_narrative_snapshot c ON p.wos_id = c.wos_id
WHERE p.is_review = FALSE
  AND c.decision = 'Y'
  AND c.category IN ('Replace', 'Support')
  AND p.abstract IS NOT NULL
  AND LENGTH(p.abstract) >= %s
"""
fr_raw = pd.read_sql(framing_sql, conn, params=(MIN_ABSTRACT_CHARS,))
n_replace = int((fr_raw["category"] == "Replace").sum())
n_support = int((fr_raw["category"] == "Support").sum())
print(f"\n── Framing discovery · Replace vs Support ──")
print(f"  Replace abstracts: {n_replace:,}  ·  Support abstracts: {n_support:,}")
print(f"  (filtered to length ≥ {MIN_ABSTRACT_CHARS} chars)")


uni_counts = {"Replace": Counter(), "Support": Counter()}
bi_counts  = {"Replace": Counter(), "Support": Counter()}
stem_forms = defaultdict(Counter)   # stem -> {surface_form: count}
TOKEN_RE = re.compile(r"[a-z]+(?:-[a-z]+)+|[a-z]+")

for _, row in fr_raw.iterrows():
    text = row["abstract"].lower()
    tokens = [t for t in TOKEN_RE.findall(text)
              if len(t) >= 3 and t not in STOPWORDS]
    stems = [simple_stem(t) for t in tokens]
    for t, s in zip(tokens, stems):
        stem_forms[s][t] += 1
    uni_counts[row["category"]].update(stems)
    for i in range(len(tokens) - 1):
        bi_counts[row["category"]][f"{tokens[i]} {tokens[i+1]}"] += 1


def rank_terms(cr_map, cs_map, min_total):
    """Score terms (total count >= min_total) by smoothed Replace/Support log-ratio."""
    all_terms = set(cr_map) | set(cs_map)
    out = []
    for t in all_terms:
        cr = cr_map.get(t, 0)
        cs = cs_map.get(t, 0)
        if cr + cs < min_total:
            continue
        rpk = cr / n_replace * 1000
        spk = cs / n_support * 1000
        log_r = math.log((rpk + 0.1) / (spk + 0.1))  # +0.1 smoothing for zero counts
        out.append({
            "term":            t,
            "display":         stem_forms[t].most_common(1)[0][0]
                                if t in stem_forms else t,
            "replace_count":   cr,
            "support_count":   cs,
            "replace_per_1k":  round(rpk, 2),
            "support_per_1k":  round(spk, 2),
            "log_ratio":       round(log_r, 3),
            "total_count":     cr + cs,
        })
    return out


uni_stats = rank_terms(uni_counts["Replace"], uni_counts["Support"], MIN_TOTAL_UNIGRAM)
bi_stats  = rank_terms(bi_counts["Replace"],  bi_counts["Support"],  MIN_TOTAL_BIGRAM)


def top_each_side(stats, n):
    """Return the n highest (Replace) and n lowest (Support) log_ratio terms."""
    sorted_by_ratio = sorted(stats, key=lambda x: x["log_ratio"])
    support_leaning = sorted_by_ratio[:n]              # most negative
    replace_leaning = sorted_by_ratio[-n:][::-1]       # most positive
    return replace_leaning, support_leaning


# Bigrams use half as many terms per side as unigrams.
r_uni, s_uni = top_each_side(uni_stats, TOP_PER_SIDE)
r_bi,  s_bi  = top_each_side(bi_stats,  TOP_PER_SIDE // 2)

framing_disc = {
    "n_replace_abstracts": n_replace,
    "n_support_abstracts": n_support,
    "min_abstract_chars":  MIN_ABSTRACT_CHARS,
    "unigrams": {
        "replace_leaning": r_uni,
        "support_leaning": s_uni,
    },
    "bigrams": {
        "replace_leaning": r_bi,
        "support_leaning": s_bi,
    },
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
}
write_json(OUTPUT_DIR / "framing_discovery.json", framing_disc)


def _print_side(rows):
    print(f"  {'term':<25s} {'R/1k':>7s} {'S/1k':>7s} {'log_r':>7s} {'total':>7s}")
    for r in rows:
        print(f"  {r['display'][:25]:<25s} {r['replace_per_1k']:>7.2f} "
              f"{r['support_per_1k']:>7.2f} {r['log_ratio']:>7.3f} "
              f"{r['total_count']:>7,}")

print(f"\n── Top {TOP_PER_SIDE} unigrams (Replace-leaning) ──")
_print_side(r_uni)
print(f"\n── Top {TOP_PER_SIDE} unigrams (Support-leaning) ──")
_print_side(s_uni)
print(f"\n── Top {TOP_PER_SIDE // 2} bigrams (Replace-leaning) ──")
_print_side(r_bi)
print(f"\n── Top {TOP_PER_SIDE // 2} bigrams (Support-leaning) ──")
_print_side(s_bi)



# framing.json: curated words for the framing chart
FRAMING_WORDS = [
    # Replace-leaning
    {"display": "photocatalytic",         "side": "Replace", "source": "unigram"},
    {"display": "antibacterial activity",  "side": "Replace", "source": "bigram"},
    {"display": "reactive oxygen species", "side": "Replace", "source": "bigram"},  # merges "reactive oxygen" + "oxygen species"
    {"display": "electron transfer",       "side": "Replace", "source": "bigram"},
    {"display": "molecularly imprinted",   "side": "Replace", "source": "bigram"},
    {"display": "carbon nanotubes",        "side": "Replace", "source": "bigram"},
    {"display": "water contact",           "side": "Replace", "source": "bigram"},
    # Support-leaning
    {"display": "drag reduction",          "side": "Support", "source": "bigram"},
    {"display": "shark skin",              "side": "Support", "source": "bigram"},
    {"display": "aerodynamic",             "side": "Support", "source": "unigram"},
    {"display": "topography",              "side": "Support", "source": "unigram"},
    {"display": "fluid dynamics",          "side": "Support", "source": "bigram"},
    {"display": "underwater vehicles",     "side": "Support", "source": "bigram"},
    {"display": "sustainability",          "side": "Support", "source": "unigram"},
    {"display": "ecological",              "side": "Support", "source": "unigram"},
]

# Look up each curated word's stats in framing_discovery.json by display name.
with open(OUTPUT_DIR / "framing_discovery.json", encoding="utf-8") as f:
    _framing_disc = json.load(f)

_disc_lookup = {}
for _bucket in ("unigrams", "bigrams"):
    for _side in ("replace_leaning", "support_leaning"):
        for _entry in _framing_disc[_bucket][_side]:
            _disc_lookup[_entry["display"]] = _entry

framing_words_out = []
for _w in FRAMING_WORDS:
    _disp = _w["display"]
    if _disp in _disc_lookup:
        _stats = _disc_lookup[_disp]
    elif _disp == "reactive oxygen species":
        _a = _disc_lookup["reactive oxygen"]
        _b = _disc_lookup["oxygen species"]
        _stats = {
            "replace_per_1k": round((_a["replace_per_1k"] + _b["replace_per_1k"]) / 2, 2),
            "support_per_1k": round((_a["support_per_1k"] + _b["support_per_1k"]) / 2, 2),
            "total_count":    _a["total_count"] + _b["total_count"],
        }
    else:
        print(f"  ⚠ '{_disp}' not found in framing_discovery.json — skipping")
        continue
    framing_words_out.append({
        "display":         _disp,
        "side":            _w["side"],
        "replace_per_1k":  _stats["replace_per_1k"],
        "support_per_1k":  _stats["support_per_1k"],
        "total_count":     _stats["total_count"],
    })

framing_out = {
    "words":               framing_words_out,
    "n_replace_abstracts": _framing_disc["n_replace_abstracts"],
    "n_support_abstracts": _framing_disc["n_support_abstracts"],
    "generated_at":        datetime.now(timezone.utc).isoformat(timespec="seconds"),
}
write_json(OUTPUT_DIR / "framing.json", framing_out)
print(f"  Framing words: {len(framing_words_out)}/{len(FRAMING_WORDS)}")


conn.close()
elapsed = time.time() - t0
print(f"\n✓ All files written to {OUTPUT_DIR.resolve()}/")
for fname in ("corpus_meta.json", "services_summary.json", "annual_by_category.json", "country_oa.json", "support_spotlight.json","wos_discovery.json", "wos_cooccurrence.json","framing_discovery.json", "framing.json", "papers_classified.parquet", "abstracts.parquet"):
    fpath = OUTPUT_DIR / fname
    size = os.path.getsize(fpath) / 1024 
    unit = "KB" if size < 1024 else "MB"
    val  = size if size < 1024 else size / 1024
    print(f"  {fname:32s} {val:>7.1f} {unit}")
print(f"\n  Total elapsed: {elapsed:.1f}s")
