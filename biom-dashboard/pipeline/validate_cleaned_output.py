"""
validate_cleaned_output.py — Structural validation for clean_biom_data's
output tables (cases.csv + the 4 child tables).

Run this AFTER the cleaning pipeline, pointing it at the same
input file and output directory, to confirm the tables are internally
consistent — row count preserved, no duplicate IDs, every child-table
case_id resolves to a real case, and the column-count change is
explainable — before trusting them for a database ingest or dashboard
build.

This does NOT re-run any cleaning logic. It only reads the already-
written CSVs and cross-checks them against each other and against the
original Excel file.

Usage:
    python validate_cleaned_output.py --input "BIOM DATABASE FULL.xlsx" --output-dir clean_output
"""

import argparse
from pathlib import Path

import pandas as pd


def check_row_count(input_path: Path, cases_df: pd.DataFrame) -> list:
    issues = []
    raw = pd.read_excel(input_path, keep_default_na=False, na_values=[""])
    raw = raw.dropna(how="all")  # a fully-blank trailing row (seen before in this data) isn't a real case
    n_raw, n_cases = len(raw), len(cases_df)
    if n_raw != n_cases:
        issues.append(
            f"Row count mismatch: {n_raw} row(s) loaded from the source file, "
            f"but cases.csv has {n_cases} row(s). Some row(s) may have been "
            f"silently dropped or duplicated somewhere in the pipeline."
        )
    else:
        print(f"  \u2713 Row count preserved: {n_cases} rows in both the source file and cases.csv")
    return issues


def check_case_id_uniqueness(cases_df: pd.DataFrame) -> list:
    issues = []
    if "case_id" not in cases_df.columns:
        return ["cases.csv has no 'case_id' column at all — can't run any of the ID-based checks."]

    missing = cases_df["case_id"].isna()
    n_missing = int(missing.sum())
    if n_missing:
        # A missing case_id is a distinct, arguably worse problem than a
        # duplicate: nunique() doesn't count it, and a single NaN isn't
        # flagged by duplicated() either, so this can silently slip past
        # a naive "any duplicates?" check the way it did here.
        missing_rows = cases_df.index[missing].tolist()
        issues.append(
            f"{n_missing} row(s) in cases.csv have a missing/blank case_id "
            f"(row position(s) in the file, 0-indexed: {missing_rows}). "
            f"These rows can never be linked to from a child table."
        )

    dupes = cases_df["case_id"][cases_df["case_id"].duplicated(keep=False) & cases_df["case_id"].notna()]
    if len(dupes):
        issues.append(f"Duplicate case_id value(s) in cases.csv: {sorted(dupes.unique().tolist())}")

    if not n_missing and not len(dupes):
        print(f"  \u2713 No duplicate or missing case_id values ({cases_df['case_id'].nunique()} unique IDs for {len(cases_df)} rows)")
    return issues


def check_referential_integrity(cases_df: pd.DataFrame, child_tables: dict) -> list:
    """Every case_id in a child table must exist in cases.csv. An orphan
    case_id — one with no matching parent row — is a strong signal that
    something got misaligned somewhere between extraction and output,
    even if every individual table looked fine on its own."""
    issues = []
    if "case_id" not in cases_df.columns:
        return issues  # already reported above
    valid_ids = set(cases_df["case_id"])
    for name, child_df in child_tables.items():
        if len(child_df) == 0:
            print(f"  \u2713 {name}: empty, nothing to check")
            continue
        if "case_id" not in child_df.columns:
            issues.append(f"{name}: no 'case_id' column found — can't check referential integrity.")
            continue
        orphans = set(child_df["case_id"]) - valid_ids
        if orphans:
            issues.append(
                f"{name}: {len(orphans)} case_id value(s) reference a case "
                f"that doesn't exist in cases.csv: {sorted(orphans)}"
            )
        else:
            print(
                f"  \u2713 {name}: every case_id has a matching row in cases.csv "
                f"({child_df['case_id'].nunique()} distinct case_ids referenced, "
                f"{len(child_df)} total rows)"
            )
    return issues


def check_column_reconciliation(input_path: Path, cases_df: pd.DataFrame) -> list:
    """Informational, not a hard pass/fail — the exact expected column
    count depends on several moving pieces that change as the exclusion
    lists evolve. Prints a breakdown so it can be sanity-checked by eye
    rather than trusted as a single opaque number."""
    raw = pd.read_excel(input_path, keep_default_na=False, na_values=[""])
    n_raw_cols, n_cases_cols = len(raw.columns), len(cases_df.columns)

    print(f"\n  Column reconciliation: {n_raw_cols} raw columns \u2192 {n_cases_cols} columns in cases.csv")
    print("  Expected adjustments (verify these roughly add up, don't just trust the final number):")
    print("    +0   case_id (renamed from a blank-header source column, not a net-new field)")
    print("    -5   PII fields dropped (Contact Name, Address, Telephone, Email, Interviewee Name and Expertise)")
    print("    -N   internal-methodology / excluded fields dropped (count = current INTERNAL_METHODOLOGY_FIELDS length)")
    print("    -3   multi-value fields extracted out (Disciplines involved, Keywords, Patent Keywords)")
    print("    -2   Patent Year(s) / Patent Number(s) extracted to case_patents")
    print("    -1   Which one? extracted to case_ecosystem_services")
    print("    -1  +5  BioM Type dropped, 4 booleans + biom_type_na added (net +4)")
    print("    -3  +9  Concept/Prototype/Commercial Year dropped, _year/_year_raw/_year_qualifier x3 added (net +6)")
    print("    +1   display_name added")
    return []


def main():
    parser = argparse.ArgumentParser(description="Validate the BioM cleaning pipeline's output tables")
    parser.add_argument("--input", required=True, help="Path to the original Excel file")
    parser.add_argument("--output-dir", default="clean_output", help="Directory containing the pipeline's output CSVs")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    input_path = Path(args.input)

    cases_df = pd.read_csv(output_dir / "cases.csv")
    child_tables = {
        "case_disciplines.csv": pd.read_csv(output_dir / "case_disciplines.csv"),
        "case_keywords.csv": pd.read_csv(output_dir / "case_keywords.csv"),
        "case_patents.csv": pd.read_csv(output_dir / "case_patents.csv"),
        "case_ecosystem_services.csv": pd.read_csv(output_dir / "case_ecosystem_services.csv"),
    }

    print("\u2550" * 70)
    print("STRUCTURAL VALIDATION")
    print("\u2550" * 70)

    all_issues = []
    all_issues += check_row_count(input_path, cases_df)
    all_issues += check_case_id_uniqueness(cases_df)
    all_issues += check_referential_integrity(cases_df, child_tables)
    all_issues += check_column_reconciliation(input_path, cases_df)

    print("\n" + "\u2550" * 70)
    if all_issues:
        print(f"{len(all_issues)} issue(s) found \u2014 review before trusting these tables:")
        for issue in all_issues:
            print(f"  \u2717 {issue}")
    else:
        print("\u2713 All structural checks passed. Safe to proceed with these tables.")
    print("\u2550" * 70)


if __name__ == "__main__":
    main()
