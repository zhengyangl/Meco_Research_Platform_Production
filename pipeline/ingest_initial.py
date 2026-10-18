"""
ingest_initial.py - One-time historical load of the MEco corpus into PostgreSQL.

Reads the WoS export (WOS_FILE) and the GPT classification file (GPT_FILE) from the
working directory, joins them on a cleaned article title, and writes datasets,
papers, classifications and pipeline_runs in a single transaction. Then prints
verification counts against the expected totals.

Requires DATABASE_URL and an empty database created from schema.sql: the narrative
page assumes this load receives dataset_id 1 (LEGACY_DATASET_IDS in aggregate.py).
Disaster-recovery use only; ongoing loads use ingest_incremental.py.

Usage:
    export DATABASE_URL="postgresql://user:password@host:5432/dbname"
    python ingest_initial.py
"""


import uuid
import time
import re
from datetime import datetime, timezone
 
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


# Config: input file paths are relative to the working directory
WOS_FILE = "1_WoS og data.xlsx"
GPT_FILE = "ManuEco_full data.xlsx"
 
import os as _os
DB_URI = _os.environ.get("DATABASE_URL")
if not DB_URI:
    raise EnvironmentError(
        "DATABASE_URL is not set.\n"
        "  export DATABASE_URL='postgresql://user:password@host:5432/dbname'\n"
        "Never hardcode credentials in this file."
    )
 
# Metadata for this import batch
DATASET_SOURCE  = "WoS"
DATASET_VERSION = "2025-05"       # matches the Date of Export in df1
MODEL_VERSION   = "GPT-4.1"
PROMPT_VERSION  = "v1.0-jacobs2025"


# Step 0: read source files
print("Reading Excel files...")
t0 = time.time()
df1 = pd.read_excel(WOS_FILE)
df2 = pd.read_excel(GPT_FILE)
print(f"  df1 (WoS):  {len(df1):,} rows, {df1.shape[1]} columns")
print(f"  df2 (GPT):  {len(df2):,} rows, {df2.shape[1]} columns")
print(f"  Read time:  {time.time()-t0:.1f}s")


# Step 1: clean and deduplicate
print("\nCleaning and deduplicating...")
 
# Join key: lower-cased title with collapsed whitespace and no trailing dots.
def clean_title(s):
    """Lowercase, collapse whitespace, strip trailing punctuation."""
    if pd.isna(s):
        return ""
    s = str(s).lower().strip()
    s = re.sub(r"\s+", " ", s)      # collapse multiple spaces
    s = re.sub(r"[.\s]+$", "", s)    # strip trailing dots/spaces
    return s
 
df1["_join_key"] = df1["Article Title"].apply(clean_title)
df2["_join_key"] = df2["Article Title"].apply(clean_title)
 
# Drop duplicate titles before the merge so it cannot inflate rows.
dup_count = df1.duplicated(subset="_join_key", keep="first").sum()
print(f"  df1 duplicates found: {dup_count}")
df1 = df1.drop_duplicates(subset="_join_key", keep="first").reset_index(drop=True)
print(f"  df1 after dedup: {len(df1):,} rows")

# df2 duplicates are the same paper in different capitalisation (e.g. ALL CAPS
# vs title case); they share a join key after cleaning.
dup2_count = df2.duplicated(subset="_join_key", keep="first").sum()
print(f"  df2 duplicates found: {dup2_count}")
df2 = df2.drop_duplicates(subset="_join_key", keep="first").reset_index(drop=True)
print(f"  df2 after dedup: {len(df2):,} rows")


# Step 2: merge the two datasets
print("\nMerging df1 and df2 on cleaned title...")
 
merged = pd.merge(
    df2,
    df1[["_join_key", "UT (Unique WOS ID)", "DOI", "Abstract",
         "Author Keywords", "Keywords Plus",
         "Addresses", "Funding Orgs", "WoS Categories",
         "Source Title", "Times Cited, WoS Core",
         "Open Access Designations", "Author Full Names", "Affiliations"]],
    on="_join_key",
    how="left",
    validate="one_to_one", 
)
 
# Nearly every df2 row must have matched a WoS record.
match_rate = merged["UT (Unique WOS ID)"].notna().mean()
print(f"  Merge match rate: {match_rate:.4%}")
assert match_rate > 0.999, f"Match rate too low ({match_rate:.2%}), aborting."
print(f"  Merged rows: {len(merged):,}")
 
# is_review comes from ReviewFlag
merged["is_review"] = merged["ReviewFlag"].str.strip().str.lower() == "review"
print(f"  Reviews flagged: {merged['is_review'].sum():,}")
 
# Author Keywords and Keywords Plus joined with "; "
merged["keywords_combined"] = (
    merged["Author Keywords"].fillna("") + "; " + merged["Keywords Plus"].fillna("")
).str.strip("; ")
merged.loc[merged["keywords_combined"] == "", "keywords_combined"] = None


# Step 3: prepare rows for each table
print("\nPreparing database rows...")
 
run_id = uuid.uuid4()
 
# papers rows (Publication Year comes from df2)
merged["pub_year_final"] = merged["Publication Year"]
 
papers_rows = []
for _, r in merged.iterrows():
    papers_rows.append((
        str(r["UT (Unique WOS ID)"]).strip(),          # wos_id (PK)
        r["DOI"] if pd.notna(r["DOI"]) else None,      # doi (nullable)
        None,                                            # dataset_id (filled after INSERT)
        str(r["Article Title"]).strip() if pd.notna(r["Article Title"]) else None,
        str(r["Abstract"]).strip() if pd.notna(r["Abstract"]) else None,
        r["keywords_combined"],
        int(r["pub_year_final"]) if pd.notna(r["pub_year_final"]) else None,
        str(r["Addresses"]).strip() if pd.notna(r["Addresses"]) else None,
        str(r["Funding Orgs"]).strip() if pd.notna(r["Funding Orgs"]) else None,
        str(r["WoS Categories"]).strip() if pd.notna(r["WoS Categories"]) else None,
        bool(r["is_review"]),
        str(r["Source Title"]).strip() if pd.notna(r["Source Title"]) else None,
        int(r["Times Cited, WoS Core"]) if pd.notna(r["Times Cited, WoS Core"]) else 0,
        # A blank Open Access Designations value means not open access: stored as 'Closed'.
        str(r["Open Access Designations"]).strip() if pd.notna(r["Open Access Designations"]) else "Closed",
        str(r["Author Full Names"]).strip() if pd.notna(r["Author Full Names"]) else None,
        str(r["Affiliations"]).strip() if pd.notna(r["Affiliations"]) else None,
    ))
print(f"  papers rows: {len(papers_rows):,}")
 
# classifications rows
classifications_rows = []
for _, r in merged.iterrows():
    wos_id = str(r["UT (Unique WOS ID)"]).strip()
    decision = str(r["Decision"]).strip() if pd.notna(r["Decision"]) else None
 
    # category, ecosystem service and technology are kept only when Decision is Y
    if decision == "Y":
        category = str(r["Category"]).strip() if pd.notna(r["Category"]) else None
        es       = str(r["EcosystemService"]).strip() if pd.notna(r["EcosystemService"]) else None
        tech     = str(r["Technology"]).strip() if pd.notna(r["Technology"]) else None
    else:
        category = None
        es       = None
        tech     = None
 
    classifications_rows.append((
        wos_id,             # wos_id 
        str(run_id),        # run_id
        MODEL_VERSION,      # model_version
        PROMPT_VERSION,     # prompt_version
        decision,           # decision
        category,           # category
        es,                 # ecosystem_service
        tech,               # technology
        True,               # is_current
    ))
print(f"  classifications rows: {len(classifications_rows):,}")


# Step 4: write to PostgreSQL
print(f"\nConnecting to database...")
conn = psycopg2.connect(DB_URI)
cur  = conn.cursor()
 
try:
    start_time = datetime.now(timezone.utc)
 
    # datasets
    print("  Writing datasets...")
    cur.execute(
        """INSERT INTO datasets (source, version, record_count)
           VALUES (%s, %s, %s)
           RETURNING dataset_id""",
        (DATASET_SOURCE, DATASET_VERSION, len(papers_rows))
    )
    dataset_id = cur.fetchone()[0]
    print(f"    dataset_id = {dataset_id}")
 
    # Fill dataset_id (tuple index 2) in every papers row; each row has 16 elements.
    papers_rows = [
        (r[0], r[1], dataset_id, r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10],
         r[11], r[12], r[13], r[14], r[15])
        for r in papers_rows
    ]

    # papers
    print("  Writing papers...")
    papers_sql = """
        INSERT INTO papers
            (wos_id, doi, dataset_id, title, abstract, keywords,
             pub_year, addresses, funding_orgs, wos_categories, is_review,
             source_title, times_cited, open_access, authors, affiliations)
        VALUES %s
        ON CONFLICT (wos_id) DO NOTHING
    """
    execute_values(cur, papers_sql, papers_rows, page_size=2000)
    papers_written = cur.rowcount
    print(f"    Inserted: {papers_written:,} rows (note: shows last batch only, use Step 5 to verify total)")
 
    # classifications
    print("  Writing classifications...")
    class_sql = """
        INSERT INTO classifications
            (wos_id, run_id, model_version, prompt_version,
             decision, category, ecosystem_service, technology, is_current)
        VALUES %s
    """
    execute_values(cur, class_sql, classifications_rows, page_size=2000)
    class_written = cur.rowcount
    print(f"    Inserted: {class_written:,} rows")
 
    # pipeline_runs
    end_time = datetime.now(timezone.utc)
    print("  Writing pipeline_runs...")
    cur.execute(
        """INSERT INTO pipeline_runs
               (run_id, start_time, end_time, papers_processed,
                papers_failed, model_version, prompt_version)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (str(run_id), start_time, end_time,
         class_written, len(classifications_rows) - class_written,
         MODEL_VERSION, PROMPT_VERSION)
    )
 
    # Commit all four tables together
    conn.commit()
    print(f"\n✓ All done. Committed in {(end_time - start_time).total_seconds():.1f}s.")
    print(f"  dataset_id:        {dataset_id}")
    print(f"  run_id:            {run_id}")
    print(f"  papers written:    {papers_written:,}")
    print(f"  classif. written:  {class_written:,}")
 
except Exception as e:
    conn.rollback()
    print(f"\n✗ Error — rolled back. {e}")
    raise
 
finally:
    cur.close()
    conn.close()
    print("  Connection closed.")


# Step 5: verification queries
print("\nRunning verification queries...")
conn = psycopg2.connect(DB_URI)
cur  = conn.cursor()

checks = [
    ("Total papers",            "SELECT COUNT(*) FROM papers"),
    ("Papers with DOI",         "SELECT COUNT(*) FROM papers WHERE doi IS NOT NULL"),
    ("Papers without DOI",      "SELECT COUNT(*) FROM papers WHERE doi IS NULL"),
    ("Review papers",           "SELECT COUNT(*) FROM papers WHERE is_review = TRUE"),
    ("Non-review papers",       "SELECT COUNT(*) FROM papers WHERE is_review = FALSE"),
    ("Total classifications",   "SELECT COUNT(*) FROM classifications"),
    ("Decision = Y (All)",      "SELECT COUNT(*) FROM classifications WHERE decision = 'Y'"),
    ("Decision = N (All)",      "SELECT COUNT(*) FROM classifications WHERE decision = 'N'"),
    ("Target Corpus (Y + Non-rev)", """
        SELECT COUNT(*) 
        FROM papers p
        JOIN classifications c ON p.wos_id = c.wos_id
        WHERE p.is_review = FALSE AND c.decision = 'Y'
    """),
    ("Current classifications", "SELECT COUNT(*) FROM classifications WHERE is_current = TRUE"),
]

for label, sql in checks:
    cur.execute(sql)
    val = cur.fetchone()[0]
    print(f"  {label:30s} {val:>10,}")

# Expected totals after de-duplication:
#   Total papers:            68,917
#   Non-review papers:       59,599
#   Decision = Y (All):      35,433
print("\nExpected: 68,917 papers | 59,599 non-review | 35,433 Decision=Y (All)| 31,559 Target Corpus")

cur.close()
conn.close()
print("\n✓ Verification complete. Check the numbers above.")
