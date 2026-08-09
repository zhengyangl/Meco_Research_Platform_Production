#!/usr/bin/env python
"""
run_pipeline.py — Master orchestration for the MEco incremental pipeline.

Confirmed design (Aug 2026): TWO DECOUPLED CHAINS, not one linear pipeline —
because classify.py's confidence routing means some rows need a human to
fill in the Google review sheet before they can be ingested, and an
orchestrator should never block waiting on that.

    Chain A — "new-data"  (triggered by new files on Google Drive)
        detect new files → classify.py → ingest ONLY auto_ingest rows
        → text_analysis.py --task all → move processed files on Drive

    Chain B — "reviewed"  (periodic, decoupled from file detection)
        classify.py --pull-reviewed → ingest the completed rows
        → text_analysis.py --task all

    aggregate.py runs on its OWN weekly schedule — call this script's
    "aggregate" mode from cron, completely decoupled from A and B. Its
    output (narrative JSON + Explorer's fallback parquet snapshots)
    doesn't need to be fresher than that.

Local WoS metadata archive (confirmed design):
    Chain A downloads new files, uses them, then moves the ORIGINALS to a
    "processed/" subfolder on Drive. But Chain B may run days later and
    still needs the raw metadata (title/abstract/DOI/etc.) for whichever
    papers went to human review — those rows were never ingested in Chain A
    (only classified_auto_ingest.csv was). So every file Chain A downloads
    is ALSO saved permanently to a local archive directory
    (data/wos_archive/, never deleted). Chain B reads every file in that
    archive to reconstruct --wos-export metadata for ingest_incremental.py,
    rather than trying to reverse-lookup which original Drive file a given
    wos_id came from.

Usage:
    export DATABASE_URL="postgresql://user:password@host:5432/dbname"
    export OPENROUTER_API_KEY="sk-or-v1-..."
    export GOOGLE_SERVICE_ACCOUNT_FILE="/path/to/service_account.json"

    # Chain A — run after uploading new WoS export(s) to the Drive folder,
    # or on a schedule that just checks for new files.
    python run_pipeline.py new-data

    # Chain B — run periodically (e.g. daily) to pick up finished reviews.
    python run_pipeline.py reviewed

    # Weekly, decoupled from both chains above.
    python run_pipeline.py aggregate

    # Any mode: preview what would happen without making changes.
    python run_pipeline.py new-data --dry-run
"""

import os
import io
import sys
import json
import argparse
import logging
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import psycopg2
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_pipeline")

# ────────────────────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent

# TEMPORARY Drive folder for new WoS uploads — Julian created this for
# development. MUST be swapped for the real production folder ID before
# final deployment; see docs/handover.md.
DRIVE_FOLDER_ID = "1D6pNaDPJFiRqlcTpL-lux3tCyWs3HuRU"
PROCESSED_SUBFOLDER_NAME = "processed"

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

ARCHIVE_DIR = SCRIPT_DIR / "data" / "wos_archive"   # permanent, never cleared
WORKDIR = SCRIPT_DIR / "run_pipeline_work"          # scratch space, safe to clear
CLASSIFY_OUTPUT_DIR = WORKDIR / "classify_output"

CLASSIFY_SCRIPT = SCRIPT_DIR / "classify.py"
INGEST_SCRIPT = SCRIPT_DIR / "ingest_incremental.py"
TEXT_ANALYSIS_SCRIPT = SCRIPT_DIR / "text_analysis.py"
AGGREGATE_SCRIPT = SCRIPT_DIR / "aggregate.py"

# Candidate column names for the WoS unique ID, used only to de-duplicate
# rows when merging multiple raw exports together before handing off to
# classify.py / ingest_incremental.py (which do their own, more thorough,
# column normalization internally).
_WOS_ID_CANDIDATES = ["UT (Unique WOS ID)", "UT", "Unique WOS ID", "wos_id"]


# ────────────────────────────────────────────────────────────────
# Google Drive helpers
# ────────────────────────────────────────────────────────────────
def get_drive_service():
    creds_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not creds_path:
        raise EnvironmentError(
            "GOOGLE_SERVICE_ACCOUNT_FILE is not set.\n"
            "  export GOOGLE_SERVICE_ACCOUNT_FILE='/path/to/service_account.json'\n"
            "Same service account used elsewhere in the pipeline — the Drive "
            "folder must be shared with it as Editor (or Content Manager for "
            "Shared Drives), the same way the Sheets are."
        )
    creds = Credentials.from_service_account_file(creds_path, scopes=DRIVE_SCOPES)
    return build("drive", "v3", credentials=creds)


def list_new_files(service, folder_id: str) -> list:
    """Files directly inside folder_id, excluding subfolders and trashed items."""
    query = (
        f"'{folder_id}' in parents and trashed = false "
        f"and mimeType != 'application/vnd.google-apps.folder'"
    )
    results = service.files().list(
        q=query, fields="files(id, name, mimeType)", pageSize=100
    ).execute()
    return results.get("files", [])


def ensure_processed_subfolder(service, parent_folder_id: str) -> str:
    """Find or create the 'processed/' subfolder, return its folder id."""
    query = (
        f"'{parent_folder_id}' in parents and trashed = false "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and name = '{PROCESSED_SUBFOLDER_NAME}'"
    )
    results = service.files().list(q=query, fields="files(id, name)").execute()
    existing = results.get("files", [])
    if existing:
        return existing[0]["id"]

    folder_metadata = {
        "name": PROCESSED_SUBFOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_folder_id],
    }
    created = service.files().create(body=folder_metadata, fields="id").execute()
    logger.info(f"Created '{PROCESSED_SUBFOLDER_NAME}/' subfolder ({created['id']})")
    return created["id"]


def download_file(service, file_id: str, file_name: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file_name
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    dest_path.write_bytes(buf.getvalue())
    return dest_path


def move_file_to_processed(service, file_id: str, current_parent_id: str, processed_folder_id: str):
    service.files().update(
        fileId=file_id,
        addParents=processed_folder_id,
        removeParents=current_parent_id,
        fields="id, parents",
    ).execute()


# ────────────────────────────────────────────────────────────────
# Local archive + file merging
# ────────────────────────────────────────────────────────────────
def archive_file(local_path: Path) -> Path:
    """Permanent copy — never deleted, never overwritten (timestamp-prefixed
    to avoid collisions if the same filename is uploaded twice)."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archived_path = ARCHIVE_DIR / f"{stamp}_{local_path.name}"
    archived_path.write_bytes(local_path.read_bytes())
    return archived_path


def _read_wos_file(path: Path) -> pd.DataFrame:
    if path.suffix in (".xls", ".xlsx"):
        return pd.read_excel(path)
    elif path.suffix == ".csv":
        return pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported WoS export format: {path.suffix} ({path.name})")


def merge_wos_files(paths: list, output_path: Path) -> Path:
    """
    Concatenate multiple raw WoS exports into one file. Only de-duplicates
    if a recognizable ID column is found — classify.py and
    ingest_incremental.py both do their own (more careful) de-duplication
    downstream regardless, so this is just a courtesy to avoid double-
    billing the OpenRouter API for an obviously-duplicate row.
    """
    frames = [_read_wos_file(Path(p)) for p in paths]
    combined = pd.concat(frames, ignore_index=True)

    id_col = next((c for c in _WOS_ID_CANDIDATES if c in combined.columns), None)
    if id_col:
        before = len(combined)
        combined = combined.drop_duplicates(subset=id_col, keep="first").reset_index(drop=True)
        if before != len(combined):
            logger.info(f"Merged batch: dropped {before - len(combined)} duplicate row(s) on '{id_col}'")
    else:
        logger.warning(
            f"No recognizable WoS ID column found in {[c for c in combined.columns[:5]]}... "
            f"— skipping dedup at merge time (downstream scripts will still dedupe on wos_id)."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_excel(output_path, index=False)
    logger.info(f"Merged {len(paths)} file(s) into {output_path} ({len(combined)} rows)")
    return output_path


# ────────────────────────────────────────────────────────────────
# Subprocess + logging helpers
# ────────────────────────────────────────────────────────────────
def run_step(cmd: list, dry_run: bool, description: str):
    logger.info(f"$ {' '.join(str(c) for c in cmd)}")
    if dry_run:
        logger.info(f"[DRY RUN] Not executing: {description}")
        return
    result = subprocess.run(cmd, cwd=SCRIPT_DIR)
    if result.returncode != 0:
        raise RuntimeError(f"{description} failed (exit code {result.returncode})")


def get_db_uri() -> str:
    uri = os.environ.get("DATABASE_URL")
    if not uri:
        raise EnvironmentError(
            "DATABASE_URL is not set.\n"
            "  export DATABASE_URL='postgresql://user:password@host:5432/dbname'"
        )
    return uri


def log_orchestrator_run(mode: str, papers_processed: int, run_id: uuid.UUID,
                          start_time: datetime, end_time: datetime, dry_run: bool):
    """One summary row per run_pipeline.py invocation, in the same
    pipeline_runs table classify.py/ingest_incremental.py write their own
    per-script rows to. model_version='orchestrator' distinguishes these
    from actual classification runs."""
    if dry_run:
        logger.info(f"[DRY RUN] Would log pipeline_runs row: mode={mode}, papers={papers_processed}")
        return
    try:
        conn = psycopg2.connect(get_db_uri())
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO pipeline_runs
                   (run_id, start_time, end_time, papers_processed,
                    papers_failed, model_version, prompt_version)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (str(run_id), start_time, end_time, papers_processed, 0,
             "orchestrator", mode),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not log orchestrator run to pipeline_runs: {e}")


# ────────────────────────────────────────────────────────────────
# Chain A — new-data
# ────────────────────────────────────────────────────────────────
def chain_new_data(dry_run: bool):
    run_id = uuid.uuid4()
    start_time = datetime.now(timezone.utc)

    service = get_drive_service()
    new_files = list_new_files(service, DRIVE_FOLDER_ID)

    if not new_files:
        logger.info("No new files found in the Drive folder — nothing to do.")
        return

    logger.info(f"Found {len(new_files)} new file(s): {[f['name'] for f in new_files]}")
    if dry_run:
        logger.info("[DRY RUN] Stopping here — would download, classify, ingest, "
                     "run text_analysis, and move these files to processed/.")
        log_orchestrator_run("new-data", 0, run_id, start_time,
                              datetime.now(timezone.utc), dry_run=True)
        return

    # Download + permanently archive every file
    local_paths = []
    for f in new_files:
        local_path = download_file(service, f["id"], f["name"], WORKDIR / "downloads")
        archive_file(local_path)
        local_paths.append(local_path)

    # Merge into a single batch for this run
    combined_path = merge_wos_files(local_paths, WORKDIR / "combined_new_batch.xlsx")
    combined_df = _read_wos_file(combined_path)

    # classify.py — new papers only
    run_step(
        [sys.executable, str(CLASSIFY_SCRIPT), "--input", str(combined_path),
         "--output-dir", str(CLASSIFY_OUTPUT_DIR)],
        dry_run, "classify.py",
    )

    # ingest ONLY the auto_ingest batch — needs_review rows wait for Chain B
    auto_ingest_path = CLASSIFY_OUTPUT_DIR / "classified_auto_ingest.csv"
    dataset_version = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_step(
        [sys.executable, str(INGEST_SCRIPT),
         "--wos-export", str(combined_path),
         "--classified", str(auto_ingest_path),
         "--dataset-version", dataset_version],
        dry_run, "ingest_incremental.py (auto-ingest)",
    )

    # NLP features — full recompute, cheap enough at current corpus size
    run_step(
        [sys.executable, str(TEXT_ANALYSIS_SCRIPT), "--task", "all"],
        dry_run, "text_analysis.py --task all",
    )

    # Mark Drive files as processed
    processed_folder_id = ensure_processed_subfolder(service, DRIVE_FOLDER_ID)
    for f in new_files:
        move_file_to_processed(service, f["id"], DRIVE_FOLDER_ID, processed_folder_id)
    logger.info(f"Moved {len(new_files)} file(s) to '{PROCESSED_SUBFOLDER_NAME}/'")

    end_time = datetime.now(timezone.utc)
    log_orchestrator_run("new-data", len(combined_df), run_id, start_time, end_time, dry_run=False)
    logger.info(f"Chain A complete in {(end_time - start_time).total_seconds():.1f}s")


# ────────────────────────────────────────────────────────────────
# Chain B — reviewed
# ────────────────────────────────────────────────────────────────
def chain_reviewed(dry_run: bool):
    run_id = uuid.uuid4()
    start_time = datetime.now(timezone.utc)

    run_step(
        [sys.executable, str(CLASSIFY_SCRIPT), "--pull-reviewed",
         "--output-dir", str(CLASSIFY_OUTPUT_DIR)],
        dry_run, "classify.py --pull-reviewed",
    )

    if dry_run:
        logger.info("[DRY RUN] Stopping here — would check for completed "
                     "reviewed rows and ingest them if any are found.")
        log_orchestrator_run("reviewed", 0, run_id, start_time,
                              datetime.now(timezone.utc), dry_run=True)
        return

    reviewed_path = CLASSIFY_OUTPUT_DIR / "classified_human_reviewed.csv"
    if not reviewed_path.exists() or pd.read_csv(reviewed_path).empty:
        logger.info("No completed human-reviewed rows found — nothing to ingest.")
        log_orchestrator_run("reviewed", 0, run_id, start_time,
                              datetime.now(timezone.utc), dry_run=False)
        return

    archived_files = sorted(ARCHIVE_DIR.glob("*"))
    if not archived_files:
        raise RuntimeError(
            f"No files found in the local WoS archive ({ARCHIVE_DIR}) — cannot "
            f"reconstruct metadata for the reviewed rows. Has Chain A ('new-data') "
            f"ever been run successfully?"
        )
    combined_archive_path = merge_wos_files(archived_files, WORKDIR / "archive_combined.xlsx")

    dataset_version = datetime.now(timezone.utc).strftime("%Y-%m-%d") + "-reviewed"
    run_step(
        [sys.executable, str(INGEST_SCRIPT),
         "--wos-export", str(combined_archive_path),
         "--classified", str(reviewed_path),
         "--dataset-version", dataset_version],
        dry_run, "ingest_incremental.py (reviewed)",
    )

    run_step(
        [sys.executable, str(TEXT_ANALYSIS_SCRIPT), "--task", "all"],
        dry_run, "text_analysis.py --task all",
    )

    n_reviewed = len(pd.read_csv(reviewed_path))
    end_time = datetime.now(timezone.utc)
    log_orchestrator_run("reviewed", n_reviewed, run_id, start_time, end_time, dry_run=False)
    logger.info(f"Chain B complete in {(end_time - start_time).total_seconds():.1f}s "
                f"({n_reviewed} reviewed row(s) ingested)")


# ────────────────────────────────────────────────────────────────
# aggregate — weekly, decoupled
# ────────────────────────────────────────────────────────────────
def chain_aggregate(dry_run: bool):
    run_id = uuid.uuid4()
    start_time = datetime.now(timezone.utc)

    run_step([sys.executable, str(AGGREGATE_SCRIPT)], dry_run, "aggregate.py")

    end_time = datetime.now(timezone.utc)
    log_orchestrator_run("aggregate", 0, run_id, start_time, end_time, dry_run=dry_run)
    if not dry_run:
        logger.info(f"aggregate.py complete in {(end_time - start_time).total_seconds():.1f}s")


# ────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="MEco master pipeline orchestrator")
    parser.add_argument(
        "mode", choices=["new-data", "reviewed", "aggregate"],
        help="new-data: detect+classify+ingest new Drive uploads (auto-confidence only). "
             "reviewed: pull finished human reviews and ingest them. "
             "aggregate: regenerate narrative JSON + Explorer fallback files.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would happen — lists files / checks for reviewed rows, "
             "but makes no API calls, no DB writes, no file moves.",
    )
    args = parser.parse_args()

    logger.info(f"run_pipeline.py — mode={args.mode} dry_run={args.dry_run}")

    if args.mode == "new-data":
        chain_new_data(args.dry_run)
    elif args.mode == "reviewed":
        chain_reviewed(args.dry_run)
    elif args.mode == "aggregate":
        chain_aggregate(args.dry_run)


if __name__ == "__main__":
    main()
