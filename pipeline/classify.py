#!/usr/bin/env python
"""
classify.py — Incremental Qwen-2.5-72B classification for new MEco corpus papers.

Pipeline position: runs AFTER new papers are detected/loaded (sources.py /
run_pipeline.py Drive-detection step), and BEFORE database ingestion.

Confidence-based routing (per Aug 2026 decision):
  - Decision + Category + EcosystemService + Technology + ReviewFlag are all
    produced by the same prompt used during model validation (unchanged).
  - Rows the model reports as "high" confidence are written to
    classified_auto_ingest.csv (review_status = "auto_high_confidence") and
    are safe to pass straight to ingestion.
  - Rows reported "medium" or "low" confidence — plus any row that failed the
    API call or failed JSON parsing — are pushed to a dedicated Google Sheet
    for human review. This is a SEPARATE spreadsheet from the crowd-sourced
    "report a misclassification" sheet used by explorer.py — that one is for
    published-data corrections, this one is a pre-ingestion QC queue. A local
    CSV copy is always written too, as a redundant audit trail.
  - Once a human has reviewed a row in the sheet, pull_reviewed_rows() reads
    the confirmed/corrected rows back, tags them review_status =
    "human_reviewed", and merges them into the SAME ingestion output as the
    auto-ingest rows — one schema, one ingestion path, not two.

Input columns: this script expects the RAW WoS export column names
(e.g. "Article Title", "Author Keywords", "Abstract", "UT (Unique WOS ID)")
and normalizes them internally — see WOS_COLUMN_ALIASES below.

Cost control: before calling the API, this script checks the database for
wos_ids that already have an is_current=TRUE classification and skips them.
This runs even in --dry-run mode (read-only against the DB) so a preview
accurately reflects what would actually be classified — which means
--dry-run now requires DATABASE_URL too, not just a valid input file.

Usage:
    # Normal run
    export DATABASE_URL="postgresql://user:password@host:5432/dbname"
    export OPENROUTER_API_KEY="sk-or-v1-..."
    export GOOGLE_SERVICE_ACCOUNT_FILE="/path/to/service_account.json"
    export REVIEW_SHEET_ID="1AbC...xyz"
    python classify.py --input new_papers.csv --output-dir output/

    # Pull back rows a human has finished reviewing in the sheet
    python classify.py --pull-reviewed --output-dir output/

    # Dry run: shows what WOULD be classified after DB dedup, makes no API
    # calls, writes nothing
    python classify.py --input new_papers.csv --dry-run
"""

import os
import re
import json
import time
import argparse
import logging
from pathlib import Path

import pandas as pd
from openai import OpenAI
from tqdm import tqdm
import gspread
import psycopg2
from google.oauth2.service_account import Credentials

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
TARGET_MODEL = "qwen/qwen-2.5-72b-instruct"
MAX_RETRIES = 5
MAX_TOKENS = 512
TEMPERATURE = 0.1
REQUEST_DELAY = 0.6  # seconds between calls
MAX_RETRY_PASSES = 2  # how many extra full passes over failed rows

# NOTE: prompt text is unchanged from the Task 0 validation script.
# If this prompt is ever revised, bump the version string below and record
# the change in docs/prompt_specification.md — classification_audit relies
# on this version tag to know which prompt produced which row.
PROMPT_VERSION = "v1_validation_baseline"

SYSTEM_PROMPT = """ You are an Ecosystem Service expert and a dedicated assistant designed to classify research articles (titles, keywords, abstracts given) based on the following instructions:
1. **Ecosystem Service Technology Analysis:**
Determine if the abstract describes a technological intervention that contributes to one or more of the following ecosystem services:
**Provisioning—Products obtained from ecosystems (Existing commercial market):**
- Biodiversity—The number of different species
- Food—Ingredients derived from wild and domesticated habitats
- Potable Water—Fresh water that is safe to consume
- Fuel—Materials used to generate energy
- Fibre/Hide/Wood—Materials used for clothing or construction
- Biochemicals—Molecules used in medicine
**Cultural—Benefits to quality of life and community (Existing commercial market):**
- Spiritual—Supporting the spiritual lives of people
- Recreation—Supporting the physical and mental health of people
- Aesthetic—The mental and physical health benefits of natural beauty
- Inspiration/Education—Art, music, literature, architecture, and engineering design
- Cultural Heritage—Value placed upon landscapes
- Cultural Identity—Societal identity regulated by the ecosystem (e.g., nomadic herding)
**Regulating—Benefits obtained by regulating ecosystem processes (Most amenable to technological replacement):**
- Atmospheric Regulation—Production and consumption of essential molecules (e.g., oxygen)
- Climate Regulation—Stabilization of climatic conditions
- Coastline Regulation—Stabilization of coastal lands (e.g., mangroves and reefs)
- Disease Regulation—Natural systems that reduce human disease or disease vectors
- Water Regulation—Timing and volume of water distribution across the landscape
- Waste Treatment—Filtering and treatment of waste products (incl. organics and water)
- Pollination—Distribution of pollen for the purpose of plant reproduction
**Supporting—Services that are not necessary for all other ecosystem services (Least amenable to technological replacement):**
- Soil Formation—The creation of new soil
- Nutrient Cycling—The movement of nutrients through the ecosystems
- Primary Production—The creation of sugars from sunlight
For this part:
**Decision:** Output "Y" if the abstract explicitly describes a practical technological method that contributes to one or more of these services; otherwise, output "N".
**Category:**
If Decision is "Y", choose **one** of the following:
- **"Support"** assists or maintains an existing natural process without intensifying it. Example: "Adding baffles so river flow still scours sediment but a little more efficiently."
- **"Enhance"** significantly boosts the efficiency or scale of a natural process while still relying on that process. Example: "Embedding enzymes in a filter to double the nitrification rate; process still needs microbes."
- **"Replace"** creates an artificial substitute that operates independently of the natural process. Example: "A photocatalytic panel that fixes nitrogen from air in total isolation from biological pathways."
(If uncertain between Enhance and Replace, choose Enhance.)
Leave blank if Decision is "N"
**EcosystemService:** If Decision is "Y", provide the exact ecosystem service from the list.
**Technology:** If Decision is "Y", provide a concise short name for the technology used.
2. **Review Paper Detection:**
Determine if the abstract indicates that the article is a review paper. If the abstract contains phrases like "review", "survey", "meta-analysis", or other similar indicators, then:
- **ReviewFlag:** Set to "review".
Otherwise, leave this field blank.

**Output Format (Strict JSON Only)**
Your output must be in JSON format only, following this structure:
{
  "Decision": "Y" or "N",
  "Category": "Support" or "Enhance" or "Replace" (leave blank if Decision = "N"),
  "EcosystemService": "(exact ecosystem service from the list)" (leave blank if Decision = "N"),
  "Technology": "(concise short name of the technology)" (leave blank if Decision = "N"),
  "ReviewFlag": "review" or "",
  "Confidence": "high" or "medium" or "low"
}

**How to report Confidence (be calibrated, not confident):**
- "high": The paper clearly and unambiguously matches one ecosystem service, and the Replace/Enhance/Support category is obvious from the abstract.
- "medium": The classification is reasonable but not certain — for example, more than one ecosystem service could arguably apply, or the Category is a judgment call.
- "low": The paper is only vaguely related to any ecosystem service, or the abstract does not give enough evidence to be sure.

Do NOT default to "high". A calibrated distribution across all papers should include a meaningful share of "medium" and "low". Reporting "low" when uncertain is more valuable than sounding confident."""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("classify")

# Internal name -> possible raw WoS export column name(s), first match wins.
# Confirm these against an actual current WoS export before first production
# run — export field names have occasionally drifted between WoS interfaces.
WOS_COLUMN_ALIASES = {
    "wos_id": ["UT (Unique WOS ID)", "UT", "Unique WOS ID"],
    "title": ["Article Title"],
    "keywords": ["Author Keywords"],
    "abstract": ["Abstract"],
}
REQUIRED_INPUT_COLUMNS = {"wos_id", "title", "keywords", "abstract"}

# Google Sheets — pre-ingestion human review queue.
# Deliberately a DIFFERENT spreadsheet from the crowd-sourced misclassification
# report sheet used in explorer.py. Same auth pattern (service account),
# separate credentials env var so the two integrations can be rotated/scoped
# independently.
GOOGLE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
REVIEW_SHEET_WORKSHEET = "needs_review"
# Default review-queue spreadsheet (pre-ingestion QC, separate from the
# crowd-sourced misclassification report sheet in explorer.py). Reuses the
# SAME service account as that sheet (meco-explorer-feedback@mindful-origin-
# 481219-u1.iam.gserviceaccount.com) — remember to share this sheet with that
# email as Editor, since a service account has no access until explicitly
# shared, even when it's the same account used elsewhere.
DEFAULT_REVIEW_SHEET_ID = "15MvAFOnq7b0dGKqzQZPCTwxhSgJdGNmQn8YZFw8BleA"
# raw_output is included so a human reviewer can see exactly what Qwen said,
# and so it survives the round trip back into classification_audit
# (raw_output JSONB) after review — that table doesn't have a place for
# reviewer_notes/reviewed_by/reviewed_at, so the sheet itself remains the
# permanent record of who reviewed what and when.
REVIEW_SHEET_COLUMNS = [
    "wos_id", "decision", "category", "ecosystem_service", "technology",
    "review_flag", "confidence", "status", "prompt_version", "raw_output",
    "reviewer_decision", "reviewer_category", "reviewer_service", "reviewer_technology",
    "reviewer_notes", "reviewed_by", "reviewed_at",
]


# ----------------------------------------------------------------------
# Cost control — skip papers that are already classified
# ----------------------------------------------------------------------
def get_db_uri() -> str:
    uri = os.environ.get("DATABASE_URL")
    if not uri:
        raise EnvironmentError(
            "DATABASE_URL is not set.\n"
            "  export DATABASE_URL='postgresql://user:password@host:5432/dbname'\n"
            "Needed even for --dry-run — the dedup check against already-"
            "classified papers is read-only but still needs a DB connection, "
            "so a dry-run preview reflects what would actually be classified."
        )
    return uri


def get_already_classified_wos_ids(wos_ids: list) -> set:
    """
    Check which of these wos_ids already have an is_current=TRUE row in
    classifications. Run BEFORE calling the API — the whole point is to
    never pay for (or wait on) an LLM call for a paper that's already been
    classified. Read-only, safe to run in --dry-run mode too.
    """
    if not wos_ids:
        return set()
    conn = psycopg2.connect(get_db_uri())
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT wos_id FROM classifications WHERE is_current = TRUE AND wos_id = ANY(%s)",
            (list(wos_ids),),
        )
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Client / API
# ----------------------------------------------------------------------
def get_client() -> OpenAI:
    """
    Build the OpenRouter client from an environment variable.

    Every maintainer registers their own OpenRouter account and exports
    their own key — never hardcode a key in this file or commit one to
    Git. See docs/handover.md for the registration steps.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY is not set.\n"
            "  export OPENROUTER_API_KEY='sk-or-v1-...'\n"
            "See docs/handover.md for how to register an OpenRouter account "
            "and generate your own key."
        )
    return OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")


def call_with_retry(client, model, system_prompt, content, max_retries=MAX_RETRIES):
    """Single classification call with exponential backoff on failure."""
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
            if (
                response is None
                or response.choices is None
                or len(response.choices) == 0
                or response.choices[0].message.content is None
            ):
                raise ValueError("Empty or malformed response")
            return response.choices[0].message.content, "Success"
        except Exception as e:
            wait = 2 ** attempt
            if attempt < max_retries - 1:
                logger.warning(f"  attempt {attempt + 1} failed ({e}); retrying in {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"  all {max_retries} attempts failed: {e}")
                return str(e), "Failed"


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------
def parse_llm_json(output_str):
    """Extract the classification fields from Qwen's raw text output."""
    try:
        match = re.search(r"\{.*\}", str(output_str), re.DOTALL)
        data = json.loads(match.group()) if match else json.loads(output_str)
        return {
            "decision": str(data.get("Decision", "")).strip(),
            "category": str(data.get("Category", "")).strip(),
            "ecosystem_service": str(data.get("EcosystemService", "")).strip(),
            "technology": str(data.get("Technology", "")).strip(),
            "review_flag": str(data.get("ReviewFlag", "")).strip().lower(),
            "confidence": str(data.get("Confidence", "")).strip().lower(),
        }
    except Exception:
        return {
            "decision": None,
            "category": None,
            "ecosystem_service": None,
            "technology": None,
            "review_flag": None,
            "confidence": None,
        }


# ----------------------------------------------------------------------
# Core classification loop
# ----------------------------------------------------------------------
def classify_papers(df: pd.DataFrame, client: OpenAI, model: str = TARGET_MODEL) -> pd.DataFrame:
    """
    df must contain: wos_id, title, keywords, abstract.
    Returns df with raw_output, status, and parsed classification columns.
    """
    results = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc=f"Classifying with {model}"):
        content = (
            f"Title: {row['title']}\n"
            f"Keywords: {row['keywords']}\n"
            f"Abstract: {row['abstract']}"
        )
        raw_output, status = call_with_retry(client, model, SYSTEM_PROMPT, content)
        parsed = (
            parse_llm_json(raw_output)
            if status == "Success"
            else {k: None for k in
                  ["decision", "category", "ecosystem_service", "technology",
                   "review_flag", "confidence"]}
        )
        results.append({"wos_id": row["wos_id"], "raw_output": raw_output, "status": status, **parsed})
        time.sleep(REQUEST_DELAY)
    return pd.DataFrame(results)


def retry_failed(df_results: pd.DataFrame, df_source: pd.DataFrame, client: OpenAI,
                  model: str = TARGET_MODEL, max_passes: int = MAX_RETRY_PASSES) -> pd.DataFrame:
    """Re-run rows that failed the API call, up to max_passes extra passes."""
    for pass_num in range(max_passes):
        failed_ids = df_results.loc[df_results["status"] == "Failed", "wos_id"].tolist()
        if not failed_ids:
            break
        logger.info(f"Retry pass {pass_num + 1}: {len(failed_ids)} failed row(s)")
        df_retry_source = df_source[df_source["wos_id"].isin(failed_ids)]
        df_retry_results = classify_papers(df_retry_source, client, model)
        df_results = df_results[~df_results["wos_id"].isin(failed_ids)]
        df_results = pd.concat([df_results, df_retry_results], ignore_index=True)
    return df_results


def split_by_confidence(df_results: pd.DataFrame):
    """
    high confidence + successful call + clean parse -> auto-ingest
    everything else (medium, low, failed call, failed parse) -> needs review

    Both halves get a review_status column so that, downstream, ingestion
    can write ONE unified batch to the database while still knowing which
    rows were machine-only vs. human-checked.
    """
    is_high = df_results["confidence"] == "high"
    is_clean = df_results["status"] == "Success"
    auto_ingest = df_results[is_high & is_clean].copy()
    needs_review = df_results[~(is_high & is_clean)].copy()

    auto_ingest["review_status"] = "auto_high_confidence"
    needs_review["review_status"] = "pending_human_review"
    return auto_ingest, needs_review


# ----------------------------------------------------------------------
# Google Sheets — pre-ingestion human review queue
# ----------------------------------------------------------------------
def get_sheets_client() -> gspread.Client:
    """
    Auth against the review-queue Google Sheet using a service account.
    Uses the SAME credential pattern as the existing crowd-sourced
    misclassification sheet in explorer.py, but a separate env var so the
    two integrations stay independently configurable/rotatable.
    """
    creds_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    if not creds_path:
        raise EnvironmentError(
            "GOOGLE_SERVICE_ACCOUNT_FILE is not set.\n"
            "  export GOOGLE_SERVICE_ACCOUNT_FILE='/path/to/service_account.json'\n"
            "See docs/handover.md for how to create/download this service "
            "account key. This should be a DIFFERENT service account (or at "
            "least a different key) from the one used for the misclassification "
            "report sheet, so access can be scoped and rotated independently."
        )
    creds = Credentials.from_service_account_file(creds_path, scopes=GOOGLE_SHEETS_SCOPES)
    return gspread.authorize(creds)


def get_review_sheet_id() -> str:
    """
    REVIEW_SHEET_ID env var takes priority; falls back to
    DEFAULT_REVIEW_SHEET_ID so the script works out of the box for the
    current review sheet without extra setup, while still staying
    overridable if the sheet is ever migrated or a different maintainer
    wants to point at a test sheet.
    """
    sheet_id = os.environ.get("REVIEW_SHEET_ID")
    if sheet_id:
        return sheet_id
    logger.info(f"REVIEW_SHEET_ID not set; using default review sheet ({DEFAULT_REVIEW_SHEET_ID})")
    return DEFAULT_REVIEW_SHEET_ID


def push_to_review_sheet(df_needs_review: pd.DataFrame) -> None:
    """
    Append rows needing human review to the dedicated review Google Sheet.
    Adds empty reviewer_decision / reviewer_notes / reviewed_by / reviewed_at
    columns for the human to fill in directly in the sheet.
    """
    if df_needs_review.empty:
        logger.info("No rows need human review — nothing pushed to the sheet.")
        return

    client = get_sheets_client()
    sheet = client.open_by_key(get_review_sheet_id())
    try:
        worksheet = sheet.worksheet(REVIEW_SHEET_WORKSHEET)
    except gspread.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=REVIEW_SHEET_WORKSHEET, rows=1000, cols=len(REVIEW_SHEET_COLUMNS))
        worksheet.append_row(REVIEW_SHEET_COLUMNS)

    df_out = df_needs_review.copy()
    for col in ["reviewer_decision", "reviewer_category", "reviewer_service",
                "reviewer_technology", "reviewer_notes", "reviewed_by", "reviewed_at"]:
        if col not in df_out.columns:
            df_out[col] = ""
    df_out = df_out.reindex(columns=REVIEW_SHEET_COLUMNS, fill_value="")

    worksheet.append_rows(df_out.astype(str).values.tolist(), value_input_option="USER_ENTERED")
    logger.info(f"Pushed {len(df_out)} row(s) to review sheet '{REVIEW_SHEET_WORKSHEET}'")


def pull_reviewed_rows() -> pd.DataFrame:
    """
    Read the review sheet and return only rows a human has finished with
    (reviewer_decision is filled in). Normalizes to the same schema as
    classify_papers() output so it can be concatenated with auto-ingest rows.

    Per-field overrides (reviewer_category / reviewer_service /
    reviewer_technology), in addition to reviewer_decision, are resolved
    downstream in ingest_incremental.py's resolve_reviewer_overrides().
    """
    client = get_sheets_client()
    sheet = client.open_by_key(get_review_sheet_id())
    worksheet = sheet.worksheet(REVIEW_SHEET_WORKSHEET)
    records = worksheet.get_all_records()
    df = pd.DataFrame(records)

    if df.empty:
        logger.info("Review sheet is empty.")
        return df

    df_done = df[df["reviewer_decision"].astype(str).str.strip() != ""].copy()
    logger.info(f"{len(df_done)} of {len(df)} review-sheet row(s) have been completed by a human")

    # reviewer_decision overrides the model's decision/category/service/technology
    # where the reviewer explicitly entered a correction; blank reviewer fields
    # mean "confirmed as-is".
    df_done["review_status"] = "human_reviewed"
    return df_done


# ----------------------------------------------------------------------
# I/O
# ----------------------------------------------------------------------
def normalize_wos_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rename raw WoS export columns (e.g. "Article Title") to the internal
    names this script uses (e.g. "title"), based on WOS_COLUMN_ALIASES.
    If a column already has the internal name, it's left alone.
    """
    rename_map = {}
    for internal_name, aliases in WOS_COLUMN_ALIASES.items():
        if internal_name in df.columns:
            continue
        for alias in aliases:
            if alias in df.columns:
                rename_map[alias] = internal_name
                break
    if rename_map:
        logger.info(f"Normalizing WoS columns: {rename_map}")
        df = df.rename(columns=rename_map)
    return df


def load_new_papers(source_path: str) -> pd.DataFrame:
    """Load the new-papers file (raw WoS export or already-normalized)."""
    path = Path(source_path)
    if path.suffix == ".csv":
        df = pd.read_csv(path)
    elif path.suffix in (".parquet", ".pq"):
        df = pd.read_parquet(path)
    elif path.suffix in (".xls", ".xlsx"):
        df = pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported input format: {path.suffix} (use .csv, .xlsx, or .parquet)")

    df = normalize_wos_columns(df)

    missing = REQUIRED_INPUT_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Input file is missing required column(s) after normalization: {missing}. "
            f"Expected at least: {sorted(REQUIRED_INPUT_COLUMNS)}. "
            f"If the raw WoS export uses different field names than expected, "
            f"update WOS_COLUMN_ALIASES at the top of this file."
        )
    return df


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Incremental Qwen classification for new MEco papers")
    parser.add_argument("--input", help="Raw WoS export (csv/xlsx/parquet) of new papers")
    parser.add_argument("--output-dir", default="classify_output", help="Directory for output files")
    parser.add_argument("--model", default=TARGET_MODEL)
    parser.add_argument("--dry-run", action="store_true", help="Validate input only; no API calls, no files written")
    parser.add_argument(
        "--pull-reviewed", action="store_true",
        help="Skip classification; instead pull completed rows back from the "
             "review sheet and write them ready for ingestion.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Mode 2: pull back human-reviewed rows, don't classify anything new ---
    if args.pull_reviewed:
        df_done = pull_reviewed_rows()
        reviewed_path = output_dir / "classified_human_reviewed.csv"
        df_done.to_csv(reviewed_path, index=False)
        logger.info(f"{len(df_done)} human-reviewed row(s) ready for ingestion -> {reviewed_path}")
        logger.info(
            "Combine this file with classified_auto_ingest.csv (concat) before "
            "handing off to the ingestion step — same schema, one ingestion path."
        )
        return

    if not args.input:
        parser.error("--input is required unless --pull-reviewed is set")

    df_new = load_new_papers(args.input)
    logger.info(f"Loaded {len(df_new)} new paper(s) from {args.input}")

    already_classified = get_already_classified_wos_ids(df_new["wos_id"].tolist())
    if already_classified:
        before = len(df_new)
        df_new = df_new[~df_new["wos_id"].isin(already_classified)].reset_index(drop=True)
        logger.info(
            f"Skipping {before - len(df_new)} paper(s) that already have an "
            f"is_current=TRUE classification — not re-calling the API for them."
        )

    if df_new.empty:
        logger.info("Nothing left to classify after skipping already-classified papers.")
        return

    if args.dry_run:
        logger.info(
            f"Dry run: {len(df_new)} paper(s) would actually be classified "
            f"(after DB dedup). No API calls made, no output written."
        )
        return

    client = get_client()
    df_results = classify_papers(df_new, client, model=args.model)
    df_results = retry_failed(df_results, df_new, client, model=args.model)
    df_results["prompt_version"] = PROMPT_VERSION

    auto_ingest, needs_review = split_by_confidence(df_results)

    # Local CSVs are always written as a redundant audit trail, even for the
    # rows that also get pushed to the review sheet.
    auto_path = output_dir / "classified_auto_ingest.csv"
    review_backup_path = output_dir / "classified_needs_review.csv"
    auto_ingest.to_csv(auto_path, index=False)
    needs_review.to_csv(review_backup_path, index=False)

    try:
        push_to_review_sheet(needs_review)
    except EnvironmentError as e:
        logger.warning(
            f"Could not push to review sheet ({e}). "
            f"The rows are still safe in {review_backup_path} — push them "
            f"manually later, or fix the credentials and re-run with "
            f"--pull-reviewed once ready."
        )

    logger.info("=" * 60)
    logger.info(f"Total classified   : {len(df_results)}")
    logger.info(f"Auto-ingest ready  : {len(auto_ingest)}  -> {auto_path}")
    logger.info(f"Needs human review : {len(needs_review)}  -> {review_backup_path} + review sheet")
    logger.info(f"Status breakdown:\n{df_results['status'].value_counts().to_string()}")
    logger.info(f"Confidence breakdown:\n{df_results['confidence'].value_counts(dropna=False).to_string()}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
