#!/usr/bin/env python
"""
ingest_incremental.py — Write NEW papers + their classifications into PostgreSQL.

Pipeline position: runs AFTER classify.py has produced
  - classify_output/classified_auto_ingest.csv          (from a normal run)
  - classify_output/classified_human_reviewed.csv        (from --pull-reviewed,
                                                            once a human has
                                                            finished the sheet)

This differs from the original one-time ingest_initial.py in two ways:
  1. The join key is wos_id directly. classify.py already carries a clean
     wos_id per row (normalized from the raw WoS export), so there's no more
     need for the title-cleaning fuzzy join that the historical load used to
     reconcile two separately-exported files.
  2. It's meant to run repeatedly on small incremental batches (tens to a
     few hundred rows), not once on ~69k rows — so re-running it on a batch
     that's already partly ingested should be safe (idempotent), not
     duplicate data or crash.

It writes to: datasets, papers, classifications, classification_audit,
pipeline_runs — matching the confirmed DDL (Aug 2026). Note that
classification_audit only stores LLM call metadata (raw_output JSONB,
confidence FLOAT, model/prompt version) — it has no columns for who reviewed
a row or when. That information lives in the Google review sheet itself,
which remains the permanent record of human review activity.

Usage:
    export DATABASE_URL="postgresql://pipeline_user:***@127.0.0.1:5432/me_dashboard"

    python ingest_incremental.py \\
        --wos-export new_batch_raw_wos.xlsx \\
        --classified classify_output/classified_auto_ingest.csv classify_output/classified_human_reviewed.csv \\
        --dataset-version 2026-08

    # Dry run: load, merge, and report what WOULD be written — no DB connection
    python ingest_incremental.py \\
        --wos-export new_batch_raw_wos.xlsx \\
        --classified classify_output/classified_auto_ingest.csv \\
        --dataset-version 2026-08 --dry-run
"""

import os
import re
import json
import uuid
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values, Json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_incremental")

DATASET_SOURCE = "WoS"
MODEL_NAME = "qwen/qwen-2.5-72b-instruct"       # classification_audit.model_name
MODEL_VERSION = "Qwen-2.5-72B-instruct"          # classifications.model_version

# classification_audit.confidence is FLOAT, but Qwen reports a "high" /
# "medium" / "low" label, not a number. This mapping is a Julian-confirm-me
# placeholder — adjust if a different numeric scale is preferred.
CONFIDENCE_TO_FLOAT = {"high": 1.0, "medium": 0.6, "low": 0.3}

# Raw WoS export column -> internal metadata field. Same spirit as
# classify.py's WOS_COLUMN_ALIASES, but covers every column the `papers`
# table needs (classify.py only needed title/keywords/abstract/wos_id).
WOS_METADATA_ALIASES = {
    "wos_id": ["UT (Unique WOS ID)", "UT", "Unique WOS ID"],
    "doi": ["DOI"],
    "title": ["Article Title"],
    "abstract": ["Abstract"],
    "author_keywords": ["Author Keywords"],
    "keywords_plus": ["Keywords Plus"],
    "pub_year": ["Publication Year"],
    "addresses": ["Addresses"],
    "funding_orgs": ["Funding Orgs"],
    "wos_categories": ["WoS Categories"],
    "source_title": ["Source Title"],
    "times_cited": ["Times Cited, WoS Core"],
    "open_access": ["Open Access Designations"],
    "authors": ["Author Full Names"],
    "affiliations": ["Affiliations"],
}
REQUIRED_METADATA_COLUMNS = {"wos_id", "title"}


# ----------------------------------------------------------------------
# Loading + normalizing the raw WoS export
# ----------------------------------------------------------------------
def normalize_metadata_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}
    for internal_name, aliases in WOS_METADATA_ALIASES.items():
        if internal_name in df.columns:
            continue
        for alias in aliases:
            if alias in df.columns:
                rename_map[alias] = internal_name
                break
    if rename_map:
        logger.info(f"Normalizing WoS metadata columns: {rename_map}")
        df = df.rename(columns=rename_map)
    return df


def load_wos_export(path: str) -> pd.DataFrame:
    path = Path(path)
    if path.suffix in (".xls", ".xlsx"):
        df = pd.read_excel(path)
    elif path.suffix == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported WoS export format: {path.suffix}")

    df = normalize_metadata_columns(df)
    missing = REQUIRED_METADATA_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"WoS export is missing required column(s): {missing}. "
            f"Update WOS_METADATA_ALIASES if the export's field names differ."
        )
    df["wos_id"] = df["wos_id"].astype(str).str.strip()

    dup_count = df.duplicated(subset="wos_id", keep="first").sum()
    if dup_count:
        logger.warning(f"WoS export has {dup_count} duplicate wos_id(s); keeping first occurrence")
        df = df.drop_duplicates(subset="wos_id", keep="first").reset_index(drop=True)

    return df


# ----------------------------------------------------------------------
# Loading classify.py's output batches
# ----------------------------------------------------------------------
def load_classified_batches(paths) -> pd.DataFrame:
    """
    Concatenate classified_auto_ingest.csv and/or classified_human_reviewed.csv.
    Both files share the same schema (see classify.py), distinguished by
    review_status ("auto_high_confidence" vs "human_reviewed").
    """
    frames = []
    for p in paths:
        df = pd.read_csv(p)
        logger.info(f"Loaded {len(df)} row(s) from {p}")
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    combined["wos_id"] = combined["wos_id"].astype(str).str.strip()

    dup_count = combined.duplicated(subset="wos_id", keep="last").sum()
    if dup_count:
        logger.warning(
            f"{dup_count} wos_id(s) appear in more than one classified file "
            f"(e.g. present in both auto_ingest and human_reviewed) — keeping "
            f"the LAST occurrence. Check upstream if this is unexpected."
        )
        combined = combined.drop_duplicates(subset="wos_id", keep="last").reset_index(drop=True)

    return resolve_reviewer_overrides(combined)


def resolve_reviewer_overrides(df: pd.DataFrame) -> pd.DataFrame:
    """
    Where a human reviewer filled in reviewer_decision / reviewer_category /
    reviewer_service / reviewer_technology, those become the final values —
    each field overrides independently, so a reviewer can correct just the
    category without having to re-type everything else. Blank reviewer
    fields mean "confirmed as-is" for that field.
    """
    field_map = {
        "reviewer_decision": "decision",
        "reviewer_category": "category",
        "reviewer_service": "ecosystem_service",
        "reviewer_technology": "technology",
    }
    for reviewer_col, target_col in field_map.items():
        if reviewer_col not in df.columns:
            continue
        has_override = df[reviewer_col].notna() & (df[reviewer_col].astype(str).str.strip() != "")
        if has_override.any():
            logger.info(f"{has_override.sum()} row(s) have a {reviewer_col} override applied to {target_col}")
            df.loc[has_override, target_col] = df.loc[has_override, reviewer_col]
    return df


# ----------------------------------------------------------------------
# Merge + row preparation
# ----------------------------------------------------------------------
def merge_metadata_and_classifications(df_meta: pd.DataFrame, df_class: pd.DataFrame) -> pd.DataFrame:
    merged = pd.merge(df_class, df_meta, on="wos_id", how="left", validate="one_to_one")

    unmatched = merged["title"].isna()
    if unmatched.any():
        logger.warning(
            f"{unmatched.sum()} classified row(s) have no matching WoS metadata "
            f"(wos_id not found in --wos-export): "
            f"{merged.loc[unmatched, 'wos_id'].tolist()[:10]}"
            f"{' ...' if unmatched.sum() > 10 else ''}"
        )
        merged = merged[~unmatched].copy()

    keywords_combined = (
        merged.get("author_keywords", pd.Series(dtype=str)).fillna("")
        + "; "
        + merged.get("keywords_plus", pd.Series(dtype=str)).fillna("")
    ).str.strip("; ")
    merged["keywords_combined"] = keywords_combined.replace("", None)

    merged["is_review"] = merged["review_flag"].astype(str).str.strip().str.lower() == "review"

    return merged


def build_papers_rows(merged: pd.DataFrame, dataset_id: int):
    rows = []
    for _, r in merged.iterrows():
        rows.append((
            r["wos_id"],
            r.get("doi") if pd.notna(r.get("doi")) else None,
            dataset_id,
            str(r["title"]).strip() if pd.notna(r.get("title")) else None,
            str(r["abstract"]).strip() if pd.notna(r.get("abstract")) else None,
            r.get("keywords_combined"),
            int(r["pub_year"]) if pd.notna(r.get("pub_year")) else None,
            str(r["addresses"]).strip() if pd.notna(r.get("addresses")) else None,
            str(r["funding_orgs"]).strip() if pd.notna(r.get("funding_orgs")) else None,
            str(r["wos_categories"]).strip() if pd.notna(r.get("wos_categories")) else None,
            bool(r["is_review"]),
            str(r["source_title"]).strip() if pd.notna(r.get("source_title")) else None,
            int(r["times_cited"]) if pd.notna(r.get("times_cited")) else 0,
            str(r["open_access"]).strip() if pd.notna(r.get("open_access")) else "Closed",
            str(r["authors"]).strip() if pd.notna(r.get("authors")) else None,
            str(r["affiliations"]).strip() if pd.notna(r.get("affiliations")) else None,
        ))
    return rows


def build_classification_rows(merged: pd.DataFrame, run_id: uuid.UUID):
    rows = []
    for _, r in merged.iterrows():
        decision = str(r["decision"]).strip() if pd.notna(r.get("decision")) else None
        if decision == "Y":
            category = str(r["category"]).strip() if pd.notna(r.get("category")) else None
            service = str(r["ecosystem_service"]).strip() if pd.notna(r.get("ecosystem_service")) else None
            tech = str(r["technology"]).strip() if pd.notna(r.get("technology")) else None
        else:
            category = service = tech = None

        prompt_version = r.get("prompt_version") if pd.notna(r.get("prompt_version")) else None

        rows.append((
            r["wos_id"], str(run_id), MODEL_VERSION, prompt_version,
            decision, category, service, tech, True,  # is_current
        ))
    return rows


def safe_json_for_audit(raw_output) -> Json:
    """
    classification_audit.raw_output is JSONB. Qwen's raw_output is usually a
    clean JSON string, but on failed calls it can be an error message or
    stray text — never let a malformed value break the insert.
    """
    if pd.isna(raw_output):
        return Json(None)
    try:
        return Json(json.loads(raw_output))
    except Exception:
        match = re.search(r"\{.*\}", str(raw_output), re.DOTALL)
        if match:
            try:
                return Json(json.loads(match.group()))
            except Exception:
                pass
        return Json({"raw_text": str(raw_output)})


def build_audit_rows(merged: pd.DataFrame, run_id: uuid.UUID):
    """
    Matches the confirmed classification_audit DDL:
        (wos_id, model_name, model_version, prompt_version,
         raw_output JSONB, confidence FLOAT, run_id, created_at DEFAULT NOW())
    One row per LLM call — this logs what the model said, not who reviewed
    it. Reviewer identity/notes/timestamp stay in the Google Sheet.
    """
    rows = []
    for _, r in merged.iterrows():
        conf_label = str(r.get("confidence", "")).strip().lower()
        conf_float = CONFIDENCE_TO_FLOAT.get(conf_label)  # None if missing/unrecognized
        prompt_version = r.get("prompt_version") if pd.notna(r.get("prompt_version")) else None
        rows.append((
            r["wos_id"],
            MODEL_NAME,
            MODEL_VERSION,
            prompt_version,
            safe_json_for_audit(r.get("raw_output")),
            conf_float,
            str(run_id),
        ))
    return rows


# ----------------------------------------------------------------------
# Database writes
# ----------------------------------------------------------------------
def get_git_commit_hash():
    """Best-effort git commit hash for pipeline_runs traceability; None if unavailable."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5,
            cwd=Path(__file__).resolve().parent,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def get_db_uri() -> str:
    uri = os.environ.get("DATABASE_URL")
    if not uri:
        raise EnvironmentError(
            "DATABASE_URL is not set.\n"
            "  export DATABASE_URL='postgresql://user:password@host:5432/dbname'\n"
            "See docs/handover.md for connection details. Never hardcode "
            "credentials in this file."
        )
    return uri


def write_to_database(merged: pd.DataFrame, dataset_version: str, run_id: uuid.UUID):
    conn = psycopg2.connect(get_db_uri())
    cur = conn.cursor()
    try:
        start_time = datetime.now(timezone.utc)

        # datasets
        cur.execute(
            """INSERT INTO datasets (source, version, record_count)
               VALUES (%s, %s, %s) RETURNING dataset_id""",
            (DATASET_SOURCE, dataset_version, len(merged)),
        )
        dataset_id = cur.fetchone()[0]
        logger.info(f"dataset_id = {dataset_id}")

        # papers — new papers only; existing wos_ids are left untouched here
        papers_rows = build_papers_rows(merged, dataset_id)
        execute_values(
            cur,
            """INSERT INTO papers
                   (wos_id, doi, dataset_id, title, abstract, keywords,
                    pub_year, addresses, funding_orgs, wos_categories, is_review,
                    source_title, times_cited, open_access, authors, affiliations)
               VALUES %s
               ON CONFLICT (wos_id) DO NOTHING""",
            papers_rows,
            page_size=2000,
        )
        logger.info(f"papers: {len(papers_rows)} row(s) submitted (ON CONFLICT DO NOTHING)")

        # classifications — retire any prior is_current row for these wos_ids
        # first (no-op if the wos_id is genuinely new), then insert the new
        # current classification. Makes this script safe to re-run on a
        # batch that was already partially ingested.
        wos_ids = [r["wos_id"] for _, r in merged.iterrows()]
        cur.execute(
            "UPDATE classifications SET is_current = FALSE WHERE wos_id = ANY(%s) AND is_current = TRUE",
            (wos_ids,),
        )
        logger.info(f"classifications: retired {cur.rowcount} prior is_current row(s)")

        class_rows = build_classification_rows(merged, run_id)
        execute_values(
            cur,
            """INSERT INTO classifications
                   (wos_id, run_id, model_version, prompt_version,
                    decision, category, ecosystem_service, technology, is_current)
               VALUES %s""",
            class_rows,
            page_size=2000,
        )
        logger.info(f"classifications: inserted {len(class_rows)} row(s)")

        # classification_audit — one row per LLM call (raw_output JSONB,
        # confidence FLOAT). Reviewer identity/notes are NOT stored here —
        # see module docstring.
        audit_rows = build_audit_rows(merged, run_id)
        execute_values(
            cur,
            """INSERT INTO classification_audit
                   (wos_id, model_name, model_version, prompt_version,
                    raw_output, confidence, run_id)
               VALUES %s""",
            audit_rows,
            page_size=2000,
        )
        logger.info(f"classification_audit: inserted {len(audit_rows)} row(s)")

        # pipeline_runs
        end_time = datetime.now(timezone.utc)
        cur.execute(
            """INSERT INTO pipeline_runs
                   (run_id, start_time, end_time, papers_processed,
                    papers_failed, model_version, prompt_version, git_commit_hash)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (str(run_id), start_time, end_time, len(class_rows), 0,
             MODEL_VERSION,
             merged["prompt_version"].iloc[0] if "prompt_version" in merged.columns else None,
             get_git_commit_hash()),
        )

        conn.commit()
        logger.info(f"Committed in {(end_time - start_time).total_seconds():.1f}s")
        return dataset_id

    except Exception as e:
        conn.rollback()
        logger.error(f"Rolled back: {e}")
        raise
    finally:
        cur.close()
        conn.close()


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Incremental ingestion of newly classified papers")
    parser.add_argument("--wos-export", required=True, help="Raw WoS export (xlsx/csv) for this batch")
    parser.add_argument("--classified", nargs="+", required=True,
                         help="One or more classify.py output CSVs to combine "
                              "(e.g. classified_auto_ingest.csv classified_human_reviewed.csv)")
    parser.add_argument("--dataset-version", required=True, help="e.g. 2026-08")
    parser.add_argument("--dry-run", action="store_true", help="Load, merge, and report — no DB connection")
    args = parser.parse_args()

    df_meta = load_wos_export(args.wos_export)
    df_class = load_classified_batches(args.classified)
    merged = merge_metadata_and_classifications(df_meta, df_class)

    logger.info("=" * 60)
    logger.info(f"Rows ready to ingest : {len(merged)}")
    if "review_status" in merged.columns:
        logger.info(f"By review_status:\n{merged['review_status'].value_counts().to_string()}")
    logger.info(f"Decision breakdown:\n{merged['decision'].value_counts(dropna=False).to_string()}")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("Dry run: no database connection made, nothing written.")
        return

    if merged.empty:
        logger.info("Nothing to ingest after merge — exiting without writing.")
        return

    run_id = uuid.uuid4()
    dataset_id = write_to_database(merged, args.dataset_version, run_id)
    logger.info(f"Done. dataset_id={dataset_id} run_id={run_id}")


if __name__ == "__main__":
    main()
