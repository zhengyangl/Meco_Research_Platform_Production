# Data Schema Supplement

*Last updated: August 2026*

Field-by-field reference for the PostgreSQL schema. For what the data *means* (ecosystem services, R/E/S, confidence levels), see `data_dictionary.md`. For the big-picture design (why the schema looks like this), see `architecture.md`.

---

## 1. `datasets`

One row per import batch.

| Column | Type | Notes |
|---|---|---|
| `dataset_id` | SERIAL, PK | |
| `source` | TEXT | `'WoS'` for everything so far |
| `version` | TEXT | Batch label, e.g. `'2025-05'` or a date string for incremental batches |
| `import_date` | TIMESTAMPTZ | Defaults to now |
| `record_count` | INT | How many papers this batch added |

`dataset_id = 1` is the original historical import — the one the narrative page is locked to (`LEGACY_DATASET_IDS` in `aggregate.py`, confirmed and verified against the published numbers). Every incremental batch since gets its own `dataset_id`.

---

## 2. `papers`

One row per paper. Raw facts only — no LLM output, no derived features.

| Column | Type | Notes |
|---|---|---|
| `wos_id` | TEXT, PK | e.g. `'WOS:001382596900001'`. Primary key, not DOI — 4.1% of papers have no DOI. |
| `doi` | TEXT | Nullable |
| `dataset_id` | INT, FK → `datasets` | Which batch this paper came from |
| `title` | TEXT | |
| `abstract` | TEXT | |
| `keywords` | TEXT | Author Keywords + Keywords Plus, combined with `"; "` |
| `pub_year` | INT | |
| `addresses` | TEXT | Raw WoS addresses field |
| `funding_orgs` | TEXT | Raw funding text, free-form |
| `wos_categories` | TEXT | Raw WoS subject categories |
| `is_review` | BOOLEAN | True if the classification prompt flagged this as a review paper |
| `source_title` | TEXT | Journal name |
| `times_cited` | INT | Citation count at time of ingestion |
| `open_access` | TEXT | e.g. `'gold'`, `'green'`, `'Closed'` — `NULL` in the raw export is stored as `'Closed'` |
| `authors` | TEXT | Full author names |
| `affiliations` | TEXT | |

Written by `ingest_initial.py` (one-time) and `ingest_incremental.py` (ongoing). `ON CONFLICT (wos_id) DO NOTHING` on insert — a paper already in the table is never overwritten by an ingestion re-run.

---

## 3. `classifications`

The LLM's decision for each paper. Versioned.

| Column | Type | Notes |
|---|---|---|
| `classification_id` | SERIAL, PK | |
| `wos_id` | TEXT, FK → `papers` | |
| `run_id` | UUID | Ties this row to a `pipeline_runs` row |
| `model_version` | TEXT | e.g. `'GPT-4.1'`, `'Qwen-2.5-72B-instruct'` |
| `prompt_version` | TEXT | See `prompt_specification.md` |
| `decision` | CHAR(1) | `'Y'` or `'N'` |
| `category` | TEXT | `'Replace'` / `'Enhance'` / `'Support'`, blank if `decision = 'N'` |
| `ecosystem_service` | TEXT | One of the 22 services, blank if `decision = 'N'` |
| `technology` | TEXT | Free-text technology label |
| `is_current` | BOOLEAN | Default `TRUE` |
| `created_at` | TIMESTAMPTZ | Default now |

```sql
CREATE UNIQUE INDEX idx_one_current_per_paper
    ON classifications (wos_id)
    WHERE is_current = TRUE;
```

This index is what makes the versioning pattern work: a paper can have many historical rows, but only one can be `is_current = TRUE` at a time. `ingest_incremental.py` retires (`is_current = FALSE`) any existing current row for a `wos_id` before inserting a new one — this makes re-running an ingestion on the same batch safe (idempotent), and is also how reclassification after a model upgrade would work, if that's ever done.

**What's NOT in this table:** who reviewed a paper, when, or their notes. That's confirmed to live only in the Google review sheet — see Section 6 and `handover.md`.

---

## 4. `paper_features`

NLP-derived attributes. Same versioning pattern as `classifications` (an `is_current` flag, not overwrite-in-place).

| Column | Type | Notes |
|---|---|---|
| `feature_id` | SERIAL, PK | |
| `wos_id` | TEXT, FK → `papers` | |
| `feature_set` | TEXT | Currently always `'nlp_v1'` — groups features by which extraction method produced them |
| `feature_key` | TEXT | See table below |
| `feature_val` | TEXT | The extracted value |
| `is_current` | BOOLEAN | Default `TRUE` |
| `created_at` | TIMESTAMPTZ | Default now |

```sql
CREATE INDEX idx_features_current
    ON paper_features (wos_id, feature_key)
    WHERE is_current = TRUE;
```

### `feature_key` values in use

A paper can have multiple rows for the same `feature_key` (e.g. multiple countries) — `_top`/`_first` variants exist for cases where the dashboard needs a single value (e.g. for a choropleth map), and a plural variant holds every value.

| `feature_key` | Meaning | One row or many per paper? | Written by |
|---|---|---|---|
| `wos_category` | A parsed WoS subject category | Many | `text_analysis.py` → `parse_wos_categories()` |
| `country_first` | First author's country | One | `text_analysis.py` → `extract_countries()` |
| `country` | Any author's country | Many | `text_analysis.py` → `extract_countries()` |
| `institution_top` | First author's institution | One | `text_analysis.py` → `standardize_institutions()` |
| `institution_all` | Any author's institution | Many | `text_analysis.py` → `standardize_institutions()` |
| `funding_top` | Whitelist-matched funding agency | Many | `text_analysis.py` → `standardize_funding()` |
| `technology_cluster` | One of the 25 canonical clusters | One | `text_analysis.py` → `cluster_technologies()` |

`wos_category`, `country_first`/`country`, `institution_top`/`institution_all`, and `funding_top` are recomputed for the **whole** corpus every run (full recompute — cheap at this corpus size). `technology_cluster` is the one exception: it only writes rows for papers that don't already have one, so it never overwrites the original hand-labeled clusters. See `data_dictionary.md` Section 7 for why.

---

## 5. `classification_audit`

One row per LLM API call. This is the audit trail — what the model actually said, not what a human did with it afterward.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL, PK | |
| `wos_id` | TEXT | Not a formal FK (a row can exist here for a paper that failed ingestion) |
| `model_name` | TEXT | e.g. `'qwen/qwen-2.5-72b-instruct'` — the API-facing model slug |
| `model_version` | TEXT | e.g. `'Qwen-2.5-72B-instruct'` — the human-readable version tag used in `classifications` too |
| `prompt_version` | TEXT | |
| `raw_output` | JSONB | The model's raw JSON response. If the raw text wasn't valid JSON (e.g. an API error message), it's wrapped as `{"raw_text": "..."}` rather than failing the insert. |
| `confidence` | FLOAT | See mapping below |
| `run_id` | UUID | |
| `created_at` | TIMESTAMPTZ | Default now |

### Confidence label → float mapping

The model reports confidence as a word (`high`/`medium`/`low`), but this column is FLOAT. Mapping, confirmed Aug 2026:

| Label | Float value |
|---|---|
| `high` | 1.0 |
| `medium` | 0.6 |
| `low` | 0.3 |

**Confirmed design: this table never stores reviewer identity, notes, or timestamps.** Once a paper goes to human review, the reviewer's name, notes, and decision live only in the Google Sheet — not written back into this table or any other. If you need "who reviewed this paper," the Sheet is the only place to look (see `handover.md`).

---

## 6. `pipeline_runs`

One row per pipeline run — both individual script runs and `run_pipeline.py`'s own orchestrator-level summary rows.

| Column | Type | Notes |
|---|---|---|
| `run_id` | UUID, PK | |
| `start_time` | TIMESTAMPTZ | |
| `end_time` | TIMESTAMPTZ | |
| `papers_processed` | INT | |
| `papers_failed` | INT | |
| `model_version` | TEXT | `'orchestrator'` for `run_pipeline.py`'s own summary rows, distinguishing them from actual classification runs |
| `prompt_version` | TEXT | For orchestrator rows, this holds the mode instead (`'new-data'` / `'reviewed'` / `'aggregate'`) |
| `git_commit_hash` | TEXT | Best-effort — `NULL` if the script isn't running from inside a git checkout |

---

## 7. Raw WoS export column mapping

`classify.py` and `ingest_incremental.py` each normalize the raw WoS export's column names to internal names. Both maintain their own alias list (`WOS_COLUMN_ALIASES` and `WOS_METADATA_ALIASES` respectively) — `ingest_incremental.py`'s is the fuller one, since it needs every field that ends up in `papers`, not just the four `classify.py` needs to build a prompt.

| Internal name | Raw WoS export column | Used by |
|---|---|---|
| `wos_id` | `UT (Unique WOS ID)` | both |
| `doi` | `DOI` | ingest_incremental.py |
| `title` | `Article Title` | both |
| `abstract` | `Abstract` | both |
| `keywords` | `Author Keywords` | classify.py |
| `author_keywords` | `Author Keywords` | ingest_incremental.py |
| `keywords_plus` | `Keywords Plus` | ingest_incremental.py |
| `pub_year` | `Publication Year` | ingest_incremental.py |
| `addresses` | `Addresses` | ingest_incremental.py |
| `funding_orgs` | `Funding Orgs` | ingest_incremental.py |
| `wos_categories` | `WoS Categories` | ingest_incremental.py |
| `source_title` | `Source Title` | ingest_incremental.py |
| `times_cited` | `Times Cited, WoS Core` | ingest_incremental.py |
| `open_access` | `Open Access Designations` | ingest_incremental.py |
| `authors` | `Author Full Names` | ingest_incremental.py |
| `affiliations` | `Affiliations` | ingest_incremental.py |

If WoS ever changes its export column names, update the alias list at the top of the relevant script — nothing else needs to change.

---

## 8. Who writes what (quick reference)

| Script | Writes to | Reads from |
|---|---|---|
| `ingest_initial.py` | `datasets`, `papers`, `classifications`, `pipeline_runs` | — (reads raw Excel files, one-time) |
| `classify.py` | Nothing in the DB directly (writes CSVs + the Google review sheet) | `classifications` (checks which `wos_id`s are already classified, before calling the API) |
| `ingest_incremental.py` | `datasets`, `papers`, `classifications`, `classification_audit`, `pipeline_runs` | — (reads classify.py's output files) |
| `text_analysis.py` | `paper_features` | `papers`, `classifications`, `paper_features` (for `cluster_technologies()`'s centroid recompute) |
| `aggregate.py` | Nothing in the DB (writes `dashboard_data/` files only) | `papers`, `classifications`, `paper_features`, `datasets` |
| `explorer.py` | Nothing in the DB (Google Sheet for misclassification reports only) | `papers`, `classifications`, `paper_features` |
| `run_pipeline.py` | `pipeline_runs` (its own orchestrator-level summary rows) | — (calls the other scripts as subprocesses) |
