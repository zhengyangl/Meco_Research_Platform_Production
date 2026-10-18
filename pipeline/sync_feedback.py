#!/usr/bin/env python
"""
sync_feedback.py — Apply approved misclassification corrections from the
Feedback Sheet (submitted via the Explorer's "Report a Misclassification" form)
to the Postgres classifications table.

Behaviour:
  - Processes only rows with review_status == "Approved" and applied_to_db != "Yes".
  - A correction retires the paper's current classification row and inserts a new
    one, regardless of dataset_id. Only category and ecosystem_service can change;
    decision and technology are copied from the current row.
  - Corrected rows carry model_version "human_correction", and a matching
    classification_audit row stores the reviewer's reason.
  - The narrative page reads classifications_narrative_snapshot, so corrections
    here do not alter its figures.
  - Each processed row's applied_to_db cell is written back to the sheet
    ("Yes", "No changes to apply", or an "Error — ..." message). The column letter
    is looked up from the header row.
  - The sheet is opened via .sheet1, as in the Explorer's _get_feedback_sheet().
  - Run by `python run_pipeline.py feedback`.

Usage:
    export DATABASE_URL="postgresql://pipeline_user:***@127.0.0.1:5432/me_dashboard"
    export GOOGLE_SERVICE_ACCOUNT_FILE="/path/to/service_account.json"
    export FEEDBACK_SHEET_ID="..."   # optional, falls back to the default below

    python sync_feedback.py --dry-run   # preview only, no DB writes, no sheet writes
    python sync_feedback.py             # apply for real
"""

import os
import json
import uuid
import argparse
import logging
from datetime import datetime, timezone

import psycopg2
import gspread
from google.oauth2.service_account import Credentials
from psycopg2.extras import Json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_feedback")

GOOGLE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]
# Fallback when FEEDBACK_SHEET_ID is not set.
DEFAULT_FEEDBACK_SHEET_ID = "1NV89GAdZJfdDSRS1M5ndxjALg8YSvK94WV8iqhnPmbs"

# Ecosystem service whitelist; keep in sync with the copies in aggregate.py and explorer.py.
VALID_ECOSYSTEM_SERVICES = {
    "Biodiversity", "Food", "Potable Water", "Fuel", "Fibre/Hide/Wood", "Biochemicals",
    "Atmospheric Regulation", "Climate Regulation", "Coastline Regulation",
    "Disease Regulation", "Water Regulation", "Waste Treatment", "Pollination",
    "Primary Production", "Soil Formation", "Nutrient Cycling",
    "Inspiration/Education", "Aesthetic", "Recreation", "Cultural Heritage",
    "Spiritual", "Cultural Identity",
}
VALID_CATEGORIES = {"Support", "Enhance", "Replace"}

# Free-text placeholder answers that must not be written as a category/service.
PLACEHOLDER_VALUES = {
    "", "not sure", "not sure — just flagging", "not sure - just flagging",
    "n/a", "na", "none", "unsure",
}

MODEL_VERSION_HUMAN = "human_correction"


def get_sheets_client() -> gspread.Client:
    creds_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not creds_path:
        raise EnvironmentError(
            "GOOGLE_SERVICE_ACCOUNT_FILE is not set.\n"
            "  export GOOGLE_SERVICE_ACCOUNT_FILE='/path/to/service_account.json'"
        )
    creds = Credentials.from_service_account_file(creds_path, scopes=GOOGLE_SHEETS_SCOPES)
    return gspread.authorize(creds)


def get_feedback_sheet_id() -> str:
    sheet_id = os.environ.get("FEEDBACK_SHEET_ID")
    if sheet_id:
        return sheet_id
    logger.info(f"FEEDBACK_SHEET_ID not set; using default ({DEFAULT_FEEDBACK_SHEET_ID}) — "
                f"UNVERIFIED, see module docstring item 1")
    return DEFAULT_FEEDBACK_SHEET_ID


def is_placeholder(value: str) -> bool:
    return str(value).strip().lower() in PLACEHOLDER_VALUES


def get_feedback_worksheet(sheets_client: gspread.Client):
    """Open the first worksheet (.sheet1), the one the Explorer submits to."""
    sheet = sheets_client.open_by_key(get_feedback_sheet_id())
    return sheet.sheet1


def find_column_letter(worksheet, header_name: str) -> str:
    """Return the A1 column letter of header_name, read from row 1 (survives column reorders)."""
    headers = worksheet.row_values(1)
    if header_name not in headers:
        raise ValueError(
            f"Column '{header_name}' not found in the sheet's header row: {headers}"
        )
    idx = headers.index(header_name) + 1  # 1-indexed
    letter = ""
    while idx > 0:
        idx, remainder = divmod(idx - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter


def get_db_uri() -> str:
    uri = os.environ.get("DATABASE_URL")
    if not uri:
        raise EnvironmentError(
            "DATABASE_URL is not set.\n"
            "  export DATABASE_URL='postgresql://user:password@host:5432/dbname'"
        )
    return uri


def fetch_current_classification(cur, wos_id: str):
    """Return (decision, category, ecosystem_service, technology, model_version,
    prompt_version) for the current row, or None if not found."""
    cur.execute(
        """SELECT c.decision, c.category, c.ecosystem_service,
                  c.technology, c.model_version, c.prompt_version
           FROM papers p
           JOIN classifications c ON c.wos_id = p.wos_id AND c.is_current = TRUE
           WHERE p.wos_id = %s""",
        (wos_id,),
    )
    return cur.fetchone()


def apply_correction(cur, wos_id: str, new_category: str, new_service: str,
                      decision: str, technology: str, run_id: uuid.UUID,
                      reason: str, reporter_email: str, reviewed_by: str):
    """Retire the current classification, insert the corrected one, and write an audit row."""
    cur.execute(
        "UPDATE classifications SET is_current = FALSE WHERE wos_id = %s AND is_current = TRUE",
        (wos_id,),
    )
    cur.execute(
        """INSERT INTO classifications
               (wos_id, run_id, model_version, prompt_version,
                decision, category, ecosystem_service, technology, is_current)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)""",
        (wos_id, str(run_id), MODEL_VERSION_HUMAN, None,
         decision, new_category, new_service, technology),
    )
    # Not an LLM call: raw_output holds the reviewer's reason (classification_audit
    # has no column for reviewer notes), so it stays queryable from the DB.
    cur.execute(
        """INSERT INTO classification_audit
               (wos_id, model_name, model_version, prompt_version,
                raw_output, confidence, run_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (wos_id, "human_reviewer", MODEL_VERSION_HUMAN, None,
         Json({"reason": reason, "reporter_email": reporter_email, "reviewed_by": reviewed_by}),
         None, str(run_id)),
    )


def main():
    parser = argparse.ArgumentParser(description="Sync approved feedback-sheet corrections into the DB")
    parser.add_argument("--dry-run", action="store_true",
                         help="Preview what would happen — no DB writes, no sheet writes")
    args = parser.parse_args()

    sheets_client = get_sheets_client()
    worksheet = get_feedback_worksheet(sheets_client)
    records = worksheet.get_all_records()
    logger.info(f"Loaded {len(records)} row(s) from feedback sheet")

    to_process = [
        (i, r) for i, r in enumerate(records, start=2)  # row 1 is the header
        if str(r.get("review_status", "")).strip() == "Approved"
        and str(r.get("applied_to_db", "")).strip() != "Yes"
    ]
    logger.info(f"{len(to_process)} row(s) are Approved and not yet applied")

    if not to_process:
        logger.info("Nothing to do.")
        return

    if not args.dry_run:
        conn = psycopg2.connect(get_db_uri())
        cur = conn.cursor()

    sheet_updates = []  # (row_number, new applied_to_db value)
    n_applied = n_skipped = n_error = 0

    for row_num, r in to_process:
        wos_id = str(r.get("wos_id", "")).strip()
        if not wos_id:
            logger.warning(f"Row {row_num}: blank wos_id, skipping")
            n_error += 1
            continue

        suggested_category = str(r.get("suggested_category", "")).strip()
        suggested_service = str(r.get("suggested_service", "")).strip()
        has_category_correction = suggested_category and not is_placeholder(suggested_category)
        has_service_correction = suggested_service and not is_placeholder(suggested_service)

        if not has_category_correction and not has_service_correction:
            logger.info(f"Row {row_num} ({wos_id}): no usable correction (placeholder/blank "
                        f"suggested fields) — marking as no-op, not applying")
            sheet_updates.append((row_num, "No changes to apply"))
            n_skipped += 1
            continue

        if args.dry_run:
            logger.info(f"[DRY RUN] Row {row_num} ({wos_id}): would apply "
                        f"category={suggested_category or '(unchanged)'} "
                        f"service={suggested_service or '(unchanged)'}")
            continue

        current = fetch_current_classification(cur, wos_id)
        if current is None:
            logger.warning(f"Row {row_num} ({wos_id}): no current classification found in DB — skipping")
            sheet_updates.append((row_num, "Error — paper not found in DB"))
            n_error += 1
            continue

        decision, category, ecosystem_service, technology, _, _ = current

        if has_service_correction and suggested_service not in VALID_ECOSYSTEM_SERVICES:
            logger.warning(f"Row {row_num} ({wos_id}): suggested_service "
                            f"'{suggested_service}' is not one of the 22 valid services — skipping")
            sheet_updates.append((row_num, f"Error — invalid ecosystem_service '{suggested_service}'"))
            n_error += 1
            continue

        if has_category_correction and suggested_category not in VALID_CATEGORIES:
            logger.warning(f"Row {row_num} ({wos_id}): suggested_category "
                            f"'{suggested_category}' is not Support/Enhance/Replace — skipping")
            sheet_updates.append((row_num, f"Error — invalid category '{suggested_category}'"))
            n_error += 1
            continue

        new_category = suggested_category if has_category_correction else category
        new_service = suggested_service if has_service_correction else ecosystem_service

        run_id = uuid.uuid4()
        try:
            apply_correction(
                cur, wos_id, new_category, new_service, decision, technology, run_id,
                reason=str(r.get("reason", "")),
                reporter_email=str(r.get("reporter_email", "")),
                reviewed_by=str(r.get("reviewed_by", "")),
            )
            conn.commit()
            logger.info(f"Row {row_num} ({wos_id}): applied — category={new_category}, "
                        f"service={new_service}")
            sheet_updates.append((row_num, "Yes"))
            n_applied += 1
        except Exception as e:
            conn.rollback()
            logger.error(f"Row {row_num} ({wos_id}): DB write failed, rolled back — {e}")
            sheet_updates.append((row_num, f"Error — {e}"))
            n_error += 1

    if not args.dry_run:
        cur.close()
        conn.close()

        # Write results back to the applied_to_db column.
        applied_to_db_col_letter = find_column_letter(worksheet, "applied_to_db")
        for row_num, value in sheet_updates:
            worksheet.update_acell(f"{applied_to_db_col_letter}{row_num}", value)

    logger.info("=" * 60)
    logger.info(f"Applied : {n_applied}")
    logger.info(f"Skipped (no usable correction) : {n_skipped}")
    logger.info(f"Errors  : {n_error}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
