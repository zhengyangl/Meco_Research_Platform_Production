-- ════════════════════════════════════════════════════════════════
-- schema.sql — MEco database setup, from scratch
-- ════════════════════════════════════════════════════════════════
-- Run this once, on a freshly installed PostgreSQL instance, to set up
-- everything the pipeline needs: the database, the pipeline_user role,
-- and all five tables.
--
-- This DDL matches what's actually running in production — confirmed
-- against the live database (see docs/data_schema_supplement.md for the
-- field-by-field explanation of every table below).
--
-- ── How to run this ──────────────────────────────────────────────
-- 1. SSH into the server.
-- 2. Log in as the default PostgreSQL superuser:
--        sudo -i -u postgres psql
-- 3. Paste this whole file in, OR run it directly from the shell:
--        sudo -u postgres psql -f schema.sql
-- 4. CHANGE THE PASSWORD BELOW FIRST — do not use the placeholder.
--
-- After this runs, update DATABASE_URL (see .env.example) to:
--   postgresql://pipeline_user:<your password>@127.0.0.1:5432/me_dashboard
-- ════════════════════════════════════════════════════════════════


-- ── 1. Database ──────────────────────────────────────────────────
CREATE DATABASE me_dashboard;

-- Everything below runs INSIDE me_dashboard. If you're pasting this
-- interactively into `psql` as postgres, connect to the new database
-- first:
--   \c me_dashboard
-- If running this whole file with `psql -f schema.sql`, the \c below
-- does that for you.
\c me_dashboard


-- ── 2. Pipeline user ─────────────────────────────────────────────
-- ⚠ CHANGE THIS PASSWORD before running — do not use this placeholder
-- in production. Update DATABASE_URL to match whatever you set here.
CREATE USER pipeline_user WITH PASSWORD 'CHANGE_ME_BEFORE_RUNNING';
GRANT ALL PRIVILEGES ON DATABASE me_dashboard TO pipeline_user;

-- PostgreSQL 15+ requires explicit schema privileges even after the
-- database-level grant above — without this, pipeline_user can connect
-- but can't create tables.
GRANT ALL ON SCHEMA public TO pipeline_user;


-- ── 3. Tables ────────────────────────────────────────────────────

-- One row per import batch. dataset_id = 1 (the first row inserted
-- below by ingest_initial.py) becomes the "legacy" batch that the
-- narrative page is permanently locked to — see architecture.md
-- Section 3.3.
CREATE TABLE datasets (
    dataset_id   SERIAL PRIMARY KEY,
    source       TEXT,            -- 'WoS', 'Scopus', etc.
    version      TEXT,            -- e.g. '2026-05'
    import_date  TIMESTAMPTZ DEFAULT NOW(),
    record_count INT
);

-- One row per paper (raw facts only — no LLM output, no derived features).
CREATE TABLE papers (
    wos_id         TEXT PRIMARY KEY,   -- e.g. 'WOS:001382596900001'
    doi            TEXT,                -- nullable, ~4.1% of papers have no DOI
    dataset_id     INT REFERENCES datasets(dataset_id),
    title          TEXT,
    abstract       TEXT,
    keywords       TEXT,
    pub_year       INT,
    addresses      TEXT,
    funding_orgs   TEXT,
    wos_categories TEXT,
    is_review      BOOLEAN,
    source_title   TEXT,                -- Journal name
    times_cited    INT,                 -- Core citation count
    open_access    TEXT,                -- OA status (e.g., 'Open Access', 'Closed')
    authors        TEXT,                -- Full author names
    affiliations   TEXT                 -- Cleaned institution lists
);

-- Classification results — versioned so history is never lost.
CREATE TABLE classifications (
    classification_id SERIAL PRIMARY KEY,
    wos_id            TEXT REFERENCES papers(wos_id),
    run_id            UUID,
    model_version     TEXT,
    prompt_version    TEXT,
    decision          CHAR(1),     -- Y / N
    category          TEXT,        -- Replace / Enhance / Support
    ecosystem_service TEXT,
    technology        TEXT,
    is_current        BOOLEAN DEFAULT TRUE,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Only one "current" result per paper allowed. This is what makes the
-- retire-then-insert versioning pattern in ingest_incremental.py safe.
CREATE UNIQUE INDEX idx_one_current_per_paper
    ON classifications (wos_id)
    WHERE is_current = TRUE;

-- NLP-derived features — kept separate so methods can evolve without
-- altering core facts in `papers`. Same versioning pattern as
-- classifications. See data_schema_supplement.md Section 4 for the
-- feature_key values actually in use (wos_category, country_first,
-- country, institution_top, institution_all, funding_top,
-- technology_cluster).
CREATE TABLE paper_features (
    feature_id   SERIAL PRIMARY KEY,
    wos_id       TEXT REFERENCES papers(wos_id),
    feature_set  TEXT,              -- e.g. 'nlp_v1'
    feature_key  TEXT,              -- e.g. 'country', 'technology_cluster'
    feature_val  TEXT,
    is_current   BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_features_current
    ON paper_features (wos_id, feature_key)
    WHERE is_current = TRUE;

-- Full audit trail — every LLM call is logged here. Does NOT store who
-- reviewed a paper or when — that lives only in the Google review
-- sheet (confirmed design, see data_schema_supplement.md Section 5).
CREATE TABLE classification_audit (
    id             SERIAL PRIMARY KEY,
    wos_id         TEXT,
    model_name     TEXT,
    model_version  TEXT,
    prompt_version TEXT,
    raw_output     JSONB,
    confidence     FLOAT,
    run_id         UUID,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Pipeline run log — one row per script run (and per run_pipeline.py
-- orchestrator invocation) — useful when something goes wrong.
CREATE TABLE pipeline_runs (
    run_id           UUID PRIMARY KEY,
    start_time       TIMESTAMPTZ,
    end_time         TIMESTAMPTZ,
    papers_processed INT,
    papers_failed    INT,
    model_version    TEXT,
    prompt_version   TEXT,
    git_commit_hash  TEXT
);


-- ── 4. Grant table-level privileges to pipeline_user ────────────────
-- The database-level GRANT above covers connecting; these cover
-- actually reading/writing the tables and using the SERIAL sequences.
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO pipeline_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO pipeline_user;

-- Make sure tables created in the FUTURE (if this script is ever
-- extended) are also granted automatically.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL PRIVILEGES ON TABLES TO pipeline_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL PRIVILEGES ON SEQUENCES TO pipeline_user;


-- ── 5. Verify ────────────────────────────────────────────────────
-- Run these after the script finishes to confirm everything's in place.
-- (Also useful any time later as a quick health check.)
\dt
SELECT COUNT(*) AS total_papers FROM papers;
SELECT COUNT(*) AS total_classifications FROM classifications;
