"""
Initial Data Ingestion
"""


# In[1]:


import uuid
import time
import re
from datetime import datetime, timezone
 
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


# In[2]:


# ════════════════════════════════════════════════════════════════
# CONFIG — change these paths to match your local setup
# ════════════════════════════════════════════════════════════════
WOS_FILE = "1_WoS og data.xlsx"
GPT_FILE = "ManuEco_full data.xlsx"
 
DB_URI = "postgresql://pipeline_user:me_dashboard@127.0.0.1:5432/me_dashboard"
 
# Metadata for this import batch
DATASET_SOURCE  = "WoS"
DATASET_VERSION = "2025-05"       # matches the Date of Export in df1
MODEL_VERSION   = "GPT-4.1"
PROMPT_VERSION  = "v1.0-jacobs2025"


# In[3]:


# ════════════════════════════════════════════════════════════════
# STEP 0 · Read source files
# ════════════════════════════════════════════════════════════════
print("Reading Excel files...")
t0 = time.time()
df1 = pd.read_excel(WOS_FILE)
df2 = pd.read_excel(GPT_FILE)
print(f"  df1 (WoS):  {len(df1):,} rows, {df1.shape[1]} columns")
print(f"  df2 (GPT):  {len(df2):,} rows, {df2.shape[1]} columns")
print(f"  Read time:  {time.time()-t0:.1f}s")


# In[7]:


# ════════════════════════════════════════════════════════════════
# STEP 1 · Clean and deduplicate
# ════════════════════════════════════════════════════════════════
print("\nCleaning and deduplicating...")
 
# Build a cleaned join key on both sides.
# Even though raw titles matched 100% in our earlier test, this protects
# against edge cases in future data batches.
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
 
# df1 has 91 duplicate titles (69,063 → 68,972 unique).
# Drop duplicates BEFORE merge to prevent row inflation.
dup_count = df1.duplicated(subset="_join_key", keep="first").sum()
print(f"  df1 duplicates found: {dup_count}")
df1 = df1.drop_duplicates(subset="_join_key", keep="first").reset_index(drop=True)
print(f"  df1 after dedup: {len(df1):,} rows")

# df2 also has duplicates — same paper, different capitalisation in the WoS
# export (e.g. ALL CAPS vs title case). After cleaning they share the same
# join key. 109 rows / 68,972 = 0.16%; safe to drop with keep='first'.
dup2_count = df2.duplicated(subset="_join_key", keep="first").sum()
print(f"  df2 duplicates found: {dup2_count}")
df2 = df2.drop_duplicates(subset="_join_key", keep="first").reset_index(drop=True)
print(f"  df2 after dedup: {len(df2):,} rows")


# In[15]:


# ════════════════════════════════════════════════════════════════
# STEP 2 · Merge the two datasets
# ════════════════════════════════════════════════════════════════
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
 
# Sanity check: every row in df2 must have a wos_id after merge
match_rate = merged["UT (Unique WOS ID)"].notna().mean()
print(f"  Merge match rate: {match_rate:.4%}")
assert match_rate > 0.999, f"Match rate too low ({match_rate:.2%}), aborting."
print(f"  Merged rows: {len(merged):,}")
 
# Derive is_review from the ReviewFlag column
merged["is_review"] = merged["ReviewFlag"].str.strip().str.lower() == "review"
print(f"  Reviews flagged: {merged['is_review'].sum():,}")
 
# Combine both keyword fields into one (separated by "; ")
merged["keywords_combined"] = (
    merged["Author Keywords"].fillna("") + "; " + merged["Keywords Plus"].fillna("")
).str.strip("; ")
merged.loc[merged["keywords_combined"] == "", "keywords_combined"] = None


# In[16]:


# ════════════════════════════════════════════════════════════════
# STEP 3 · Prepare rows for each database table
# ════════════════════════════════════════════════════════════════
print("\nPreparing database rows...")
 
run_id = uuid.uuid4()
 
# --- papers table ---
# Publication Year comes from df2 (only one copy in the merged frame).
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
        # NaN in Open Access Designations means the paper is NOT open access
        # — fill these with 'Closed' so the field is queryable.
        str(r["Open Access Designations"]).strip() if pd.notna(r["Open Access Designations"]) else "Closed",
        str(r["Author Full Names"]).strip() if pd.notna(r["Author Full Names"]) else None,
        str(r["Affiliations"]).strip() if pd.notna(r["Affiliations"]) else None,
    ))
print(f"  papers rows: {len(papers_rows):,}")
 
# --- classifications table ---
classifications_rows = []
for _, r in merged.iterrows():
    wos_id = str(r["UT (Unique WOS ID)"]).strip()
    decision = str(r["Decision"]).strip() if pd.notna(r["Decision"]) else None
 
    # Only populate category/ES/technology when Decision='Y'
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


# In[17]:


# ════════════════════════════════════════════════════════════════
# STEP 4 · Write to PostgreSQL 
# ════════════════════════════════════════════════════════════════
print(f"\nConnecting to database...")
conn = psycopg2.connect(DB_URI)
cur  = conn.cursor()
 
try:
    start_time = datetime.now(timezone.utc)
 
    # ── 4a. datasets ──────────────────────────────────────────
    print("  Writing datasets...")
    cur.execute(
        """INSERT INTO datasets (source, version, record_count)
           VALUES (%s, %s, %s)
           RETURNING dataset_id""",
        (DATASET_SOURCE, DATASET_VERSION, len(papers_rows))
    )
    dataset_id = cur.fetchone()[0]
    print(f"    dataset_id = {dataset_id}")
 
    # Patch dataset_id into every paper's row (index 2 in the tuple).
    # Each tuple now has 16 elements (original 11 + 5 new columns).
    papers_rows = [
        (r[0], r[1], dataset_id, r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10],
         r[11], r[12], r[13], r[14], r[15])
        for r in papers_rows
    ]

    # ── 4b. papers ────────────────────────────────────────────
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
 
    # ── 4c. classifications ───────────────────────────────────
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
 
    # ── 4d. pipeline_runs ─────────────────────────────────────
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
 
    # ── Commit everything at once ─────────────────────────────
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


# In[18]:


# ════════════════════════════════════════════════════════════════
# STEP 5 · Quick verification queries
# ════════════════════════════════════════════════════════════════
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

# The numbers we expect (Post-deduplication Gold Standard):
#   Total papers:            68,917
#   Non-review papers:       59,599
#   Decision = Y (All):      35,433
print("\nExpected: 68,917 papers | 59,599 non-review | 35,433 Decision=Y (All)| 31,593 Target Corpus")

cur.close()
conn.close()
print("\n✓ Verification complete. Check the numbers above.")

