"""
clean_biom_data.py — Data cleaning pipeline for the BioM Innovation Database.

Input:  a single Excel file exported from the Google Sheet.
Output: five clean tables (cases, case_disciplines, case_keywords,
        case_patents, case_ecosystem_services) plus a diagnostic report
        of suspected row-level column shifts, all written as CSV.

Usage:
    python clean_biom_data.py --input BIOM_DATABASE_FULL.xlsx --output-dir clean_output/

See data_cleaning_notes.md for the reasoning behind each rule below.
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

# ════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════

PII_FIELDS_TO_DROP = [
    "Contact Name",
    "Address",
    "Telephone",
    "Email",
    "Interviewee Name and Expertise",
]

INTERNAL_METHODOLOGY_FIELDS = [
    "Interview Date", "Interview Type", "Interview: Product Phase",
    "Interview: Concept Year", "Interview: Prototype Year", "Interview: Commercial Year",
    "Interview: Patent Year(s)", "Interview: Mimic (to figure out 'level')",
    "Perceived Level", "Difference between actual and perceived",
    "Interview: Process Type", "Number of models previously explored",
    "Novel Solution", "Impact on Field", "Interview: Disciplines Involved",
    "Was a biologist on the team?", "Multidisciplinary Challenges?",
    "In-Depth Interview?", "Notification of Database Availability?",
    "Interview & General Notes", "Outcome",
    "Developer Name(s)", "Product Biomimetic Phrase", "City",
    "Copy of Patent in Dropbox Folder",
]

# Multi-value fields, extracted into their own long-format child tables.
MULTI_VALUE_FIELDS = {
    "Disciplines involved": ("case_disciplines", "discipline"),
    "Keywords": ("case_keywords", "keyword"),
    "Patent Keywords": ("case_keywords", "keyword"),
}

# Positionally paired, may have mismatched lengths — see extract_patents_table.
PATENT_YEAR_FIELD = "Patent Year(s)"
PATENT_NUMBER_FIELD = "Patent Number(s)"

BIOM_TYPE_COMPONENTS = ["Function", "Form", "Process", "Interaction"]

YES_NO_FIELDS = [
    "Patent mentions biomim*?",
    "Innovator?", "Sustainability?", "Bioutilization?",
    "Is this product Biomimetic?", "Is this an Ecosystem Service",
    "Do the official or commercial product descriptions or journal article "
    "by developer mention inspir*, Biom*, Bioni*, or mimi*?",
    "Aerospace or Transport?",
]
_YES_VALUES = {"yes", "y", "true", "1"}
_NO_VALUES = {"no", "n", "false", "0"}
_NA_VALUES = {"n/a", "na", "unknown", ""}

# Field-specific values treated as unknown/NA rather than flagged.
FIELD_SPECIFIC_NA_OVERRIDES = {
    "Innovator?": {
        "no?",
        "no - uses claus mattheck software",
        "no? building uses the swarm intelligence software.",
    },
}

# Confirmed-bad values for whitelist-checked fields — blanked, not
# force-mapped to anything.
WHITELIST_BLANK_VALUES = {
    "Kingdom": {"viridae"},
    "Group": {"bacteria", "viruses"},
    "Phylum": {"actinopoda", "alveolata", "bacillariophyta", "basidiomycota"},
    "Mimic Suprasystem": {"taxa"},
}

KINGDOM_WHITELIST = ["Animalia", "Fungi", "Monera", "Plantae", "Protista"]

GROUP_WHITELIST = ["Chordates", "Invertebrates", "Plants", "Fungi", "Other"]

PHYLUM_WHITELIST = [
    "Acanthocephala", "Acidobacteria", "Acoelomorpha", "Actinobacteria", "Amoebozoa",
    "Annelida", "Anthocerotophyta", "Anthophyta", "Apicomplexa", "Aquificae",
    "Arthropoda", "Bacteroidetes", "Brachiopoda", "Bryophyta", "Bryozoa",
    "Caldiserica", "Chaetognatha", "Chlamydiae", "Chlorobi", "Chloroflexi",
    "Chlorophyta", "Chordata", "Chrysiogenetes", "Ciliophora", "Cnidaria",
    "Coniferophyta", "Crenarchaeota", "Ctenophora", "Cyanobacteria", "Cycadophyta",
    "Cycliophora", "Deferribacteres", "Deinococcus-Thermus", "Dictyoglomi",
    "Dinoflagellata", "Echinodermata", "Elusimicrobia", "Entoprocta", "Euglenophyta",
    "Euryarchaeota", "Fibrobacteres", "Firmicutes", "Foraminifera", "Fusobacteria",
    "Gastrotricha", "Gemmatimonadetes", "Ginkgophyta", "Gnathostomulida", "Gnetophyta",
    "Hemichordata", "Heterokontophyta", "Kinorhyncha", "Korarchaeota", "Lentisphaerae",
    "Loricifera", "Lycopodiophyta", "Marchantiophyta", "Micrognathozoa", "Mollusca",
    "Myxomycota", "Nanoarchaeota", "Nematoda", "Nematomorpha", "Nemertea",
    "Nitrospira", "Onychophora", "Orthonectida", "Phoronida", "Placozoa",
    "Planctomycetes", "Platyhelminthes", "Porifera", "Priapulida", "Proteobacteria",
    "Pteridophyta", "Pteridospermatophyta", "Rhodophyta", "Rhombozoa", "Rotifera",
    "Sarcodina", "Sipuncula", "Spirochaetes", "Sporozoa", "Synergistetes",
    "Tardigrada", "Tenericutes", "Thaumarchaeota", "Thermodesulfobacteria",
    "Thermomicrobia", "Thermotogae", "Verrucomicrobia", "Xenoturbellida",
]

ORGANIZATION_LEVEL_WHITELIST = [
    "Molecule", "Organelle", "Cell", "Tissue", "Organ", "Organ System",
    "Organism", "Population", "Community", "Ecosystem", "Biosphere",
]  # Mimic System, Mimic Subsystem, Mimic Suprasystem

PRODUCT_PHASE_WHITELIST = [
    "Concept", "In Development", "Commercially Available",
    "Discontinued, was Commercially Available", "Prototype, Not commercial",
    "No longer in development",
]

PROCESS_TYPE_WHITELIST = ["Biology to Design", "Design to Biology", "Retroactive", "N/A"]

CONTINENT_WHITELIST = ["Africa", "Asia", "Europe", "North America", "Oceania", "South America"]

ECOSYSTEM_SERVICES_WHITELIST = [
    "Aesthetics", "Atmospheric regulation", "Biochemicals", "Biodiversity",
    "Climate regulation", "Coastline Regulation", "Cultural Heritage",
    "Cultural Identity", "Disease Regulation", "Fibre/Hide/Wood", "Food", "Fuel",
    "Inspiration/education", "Nutrient Cycling", "Pollination", "Potable Water",
    "Primary Production", "Recreation", "Soil Formation", "Spiritual Support",
    "Waste Treatment", "Water Regulation",
]

BIOM_INTENSITY_WHITELIST = ["0", "1", "2", "3", "N/A"]

CASE_STATUS_WHITELIST = [
    "Complete, with interview", "Complete, no interview",
    "Interview scheduled or email interview in progress", "Contacted",
]

SHIFT_CHECK_CHAIN = [
    ("Kingdom", KINGDOM_WHITELIST, "yesno"),
    ("Group", GROUP_WHITELIST, KINGDOM_WHITELIST),
    ("Phylum", PHYLUM_WHITELIST, GROUP_WHITELIST),
    ("Mimic System", ORGANIZATION_LEVEL_WHITELIST, PHYLUM_WHITELIST),
    ("BioM Intensity", BIOM_INTENSITY_WHITELIST, BIOM_TYPE_COMPONENTS + ["N/A"]),
]

SHIFT_SUSPECT_YESNO_FIELDS = [
    "Innovator?", "Is this product Biomimetic?", "Aerospace or Transport?",
    "Do the official or commercial product descriptions or journal article "
    "by developer mention inspir*, Biom*, Bioni*, or mimi*?",
]


# ════════════════════════════════════════════════════════════════
# Data-quality report
# ════════════════════════════════════════════════════════════════
class QualityReport:
    def __init__(self):
        self.issues = []

    def flag(self, message: str, severity: str = "WARNING"):
        self.issues.append((severity, message))

    def print_summary(self):
        print("\n" + "═" * 70)
        print("DATA QUALITY REPORT")
        print("═" * 70)
        if not self.issues:
            print("  No issues flagged.")
            return
        errors = [m for s, m in self.issues if s == "ERROR"]
        warnings = [m for s, m in self.issues if s == "WARNING"]
        print(f"  {len(errors)} error(s), {len(warnings)} warning(s)\n")
        for severity, message in self.issues:
            marker = "✗" if severity == "ERROR" else "⚠"
            print(f"  {marker} [{severity}] {message}")
        print("═" * 70)


# ════════════════════════════════════════════════════════════════
# Cleaning steps
# ════════════════════════════════════════════════════════════════
def load_excel(path: Path) -> pd.DataFrame:
    try:
        # "N/A" is a meaningful whitelisted value in this schema, not a
        # blank cell — must not let pandas auto-coerce it to NaN.
        df = pd.read_excel(path, keep_default_na=False, na_values=[""])
    except FileNotFoundError:
        sys.exit(f"Input file not found: {path}")
    except Exception as e:
        sys.exit(f"Could not read '{path}' as an Excel file: {e}")
    return df


def normalize_column_names(df: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    renamed = {}
    for col in df.columns:
        stripped = col.strip()
        if stripped != col:
            renamed[col] = stripped
    if renamed:
        report.flag(f"Stripped whitespace from {len(renamed)} column name(s): {list(renamed.keys())}", "WARNING")
        df = df.rename(columns=renamed)
    return df


def drop_pii(df: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    present = [c for c in PII_FIELDS_TO_DROP if c in df.columns]
    missing = [c for c in PII_FIELDS_TO_DROP if c not in df.columns]
    if present:
        df = df.drop(columns=present)
        report.flag(f"Dropped {len(present)} PII field(s): {present}", "WARNING")
    if missing:
        report.flag(
            f"Expected PII field(s) not found in the input — verify these "
            f"aren't present under a different column name: {missing}",
            "WARNING",
        )
    return df


def drop_internal_methodology_fields(df: pd.DataFrame) -> pd.DataFrame:
    present = [c for c in INTERNAL_METHODOLOGY_FIELDS if c in df.columns]
    return df.drop(columns=present)


def normalize_yes_no(df: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    for col in YES_NO_FIELDS:
        if col not in df.columns:
            continue

        field_overrides = FIELD_SPECIFIC_NA_OVERRIDES.get(col, set())

        def _map(val):
            if pd.isna(val):
                return pd.NA
            s = str(val).strip().lower()
            if s in _YES_VALUES:
                return True
            if s in _NO_VALUES:
                return False
            if s in _NA_VALUES:
                return pd.NA
            if s in field_overrides:
                return pd.NA
            return "UNRECOGNIZED"

        mapped = df[col].apply(_map)
        bad_mask = mapped == "UNRECOGNIZED"
        if bad_mask.any():
            bad_values = df.loc[bad_mask, col].unique().tolist()
            report.flag(
                f"Column '{col}': {bad_mask.sum()} row(s) had unrecognized "
                f"Yes/No value(s) {bad_values} — left as-is (not coerced), fix manually or extend _YES_VALUES/_NO_VALUES.",
                "ERROR",
            )
            mapped = mapped.where(~bad_mask, df[col])
        df[col] = mapped
    return df


def blank_known_bad_values(df: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    for col, bad_values in WHITELIST_BLANK_VALUES.items():
        if col not in df.columns:
            continue
        mask = df[col].apply(lambda v: pd.notna(v) and str(v).strip().lower() in bad_values)
        n = int(mask.sum())
        if n:
            found = sorted(df.loc[mask, col].astype(str).unique().tolist())
            report.flag(f"Column '{col}': blanked {n} confirmed-invalid value(s): {found}", "WARNING")
            df.loc[mask, col] = pd.NA
    return df


def blank_multivalue_continent(df: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    col = "Continent"
    if col not in df.columns:
        return df
    mask = df[col].apply(lambda v: pd.notna(v) and ";" in str(v))
    n = int(mask.sum())
    if n:
        examples = df.loc[mask, col].unique().tolist()[:5]
        report.flag(
            f"Column 'Continent': blanked {n} value(s) that looked like "
            f"multiple countries joined with ';' rather than a single "
            f"continent. Examples: {examples}",
            "WARNING",
        )
        df.loc[mask, col] = pd.NA
    return df


def normalize_whitelist_case(df: pd.DataFrame, col: str, whitelist: list, report: QualityReport) -> pd.DataFrame:
    if col not in df.columns:
        return df
    case_map = {w.lower(): w for w in whitelist}

    def _fix(v):
        if pd.isna(v):
            return v
        s = str(v).strip()
        if s in whitelist:
            return s
        canonical = case_map.get(s.lower())
        return canonical if canonical is not None else v

    fixed = df[col].apply(_fix)
    # NA-vs-NA can stringify inconsistently across dtypes — compare
    # directly instead of via astype(str) to avoid false-positive counts.
    n_changed = int(((fixed != df[col]) & fixed.notna() & df[col].notna()).sum())
    if n_changed:
        report.flag(f"Column '{col}': normalized casing on {n_changed} value(s) to match the whitelist exactly.", "WARNING")
    df[col] = fixed
    return df


def validate_whitelist(df: pd.DataFrame, col: str, whitelist: list, report: QualityReport):
    if col not in df.columns:
        return
    actual = df[col].dropna().unique().tolist()
    bad = [v for v in actual if str(v).strip() not in whitelist]
    if bad:
        report.flag(f"Column '{col}': {len(bad)} unexpected value(s) not in whitelist: {bad}", "ERROR")


def split_biom_type(df: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    col = "BioM Type"
    if col not in df.columns:
        return df

    for component in BIOM_TYPE_COMPONENTS:
        df[f"biom_type_{component.lower()}"] = df[col].apply(
            lambda v: (component in str(v)) if pd.notna(v) else pd.NA
        )
    df["biom_type_na"] = df[col].apply(lambda v: pd.notna(v) and str(v).strip() == "N/A")

    unrecognized = df[col].dropna().unique().tolist()
    unrecognized = [
        v for v in unrecognized
        if str(v).strip() != "N/A" and not any(c in str(v) for c in BIOM_TYPE_COMPONENTS)
    ]
    if unrecognized:
        report.flag(f"Column 'BioM Type': value(s) matched none of the four known components: {unrecognized}", "ERROR")

    return df.drop(columns=[col])


def extract_multi_value_tables(df: pd.DataFrame, id_col: str, report: QualityReport) -> tuple:
    disciplines_rows = []
    keywords_rows = []

    if "Disciplines involved" in df.columns:
        for _, row in df.iterrows():
            raw = row["Disciplines involved"]
            if pd.isna(raw):
                continue
            for item in str(raw).split("\n"):
                item = item.strip()
                if item:
                    disciplines_rows.append({"case_id": row[id_col], "discipline": item})

    for source_col, keyword_type in [("Keywords", "product"), ("Patent Keywords", "patent")]:
        if source_col not in df.columns:
            continue
        for _, row in df.iterrows():
            raw = row[source_col]
            if pd.isna(raw):
                continue
            for item in str(raw).split("\n"):
                item = item.strip()
                if item:
                    keywords_rows.append({"case_id": row[id_col], "keyword": item, "keyword_type": keyword_type})

    disciplines_df = pd.DataFrame(disciplines_rows)
    keywords_df = pd.DataFrame(keywords_rows)

    drop_cols = [c for c in ["Disciplines involved", "Keywords", "Patent Keywords"] if c in df.columns]
    df = df.drop(columns=drop_cols)

    report.flag(
        f"Extracted {len(disciplines_df)} discipline row(s) and {len(keywords_df)} "
        f"keyword row(s) into child tables.",
        "WARNING",
    )
    return df, disciplines_df, keywords_df


def extract_ecosystem_services_table(df: pd.DataFrame, id_col: str, report: QualityReport) -> tuple:
    rows = []
    col = "Which one?"
    es_col = "Is this an Ecosystem Service"
    if col not in df.columns:
        return df, pd.DataFrame(rows)

    filled_without_yes_count = 0
    for _, row in df.iterrows():
        raw = row[col]
        if pd.isna(raw) or str(raw).strip().lower() == "none":
            continue
        services = [s.strip() for s in str(raw).split(",") if s.strip()]
        is_es = row.get(es_col) if es_col in df.columns else None
        if is_es is not True:
            filled_without_yes_count += 1
        for service in services:
            rows.append({"case_id": row[id_col], "ecosystem_service": service})

    if filled_without_yes_count:
        report.flag(
            f"{filled_without_yes_count} row(s) have 'Which one?' filled in but "
            f"'Is this an Ecosystem Service' is not Yes — inconsistent, needs a human look.",
            "ERROR",
        )

    services_df = pd.DataFrame(rows)
    if len(services_df):
        bad = services_df.loc[~services_df["ecosystem_service"].isin(ECOSYSTEM_SERVICES_WHITELIST), "ecosystem_service"].unique().tolist()
        if bad:
            report.flag(f"Column 'Which one?': {len(bad)} unexpected value(s) not in the 22-service whitelist: {bad}", "ERROR")

    df = df.drop(columns=[col])
    report.flag(f"Extracted {len(services_df)} ecosystem-service row(s) into a child table.", "WARNING")
    return df, services_df


def extract_patents_table(df: pd.DataFrame, id_col: str, report: QualityReport) -> pd.DataFrame:
    rows = []
    if PATENT_YEAR_FIELD not in df.columns and PATENT_NUMBER_FIELD not in df.columns:
        return pd.DataFrame(rows)

    for _, row in df.iterrows():
        case_id = row[id_col]
        years_raw = row.get(PATENT_YEAR_FIELD)
        numbers_raw = row.get(PATENT_NUMBER_FIELD)

        years = [] if pd.isna(years_raw) else [y.strip() for y in str(years_raw).split("\n")]
        numbers = [] if pd.isna(numbers_raw) else [n.strip() for n in str(numbers_raw).split("\n")]

        if not years and not numbers:
            continue

        if years and numbers and len(years) != len(numbers):
            report.flag(
                f"case_id={case_id}: Patent Year(s) has {len(years)} entries but "
                f"Patent Number(s) has {len(numbers)} — pairing by position up to "
                f"the shorter list; the remaining entries are emitted unpaired. "
                f"Verify this row manually.",
                "ERROR",
            )

        max_len = max(len(years), len(numbers))
        for i in range(max_len):
            year = years[i] if i < len(years) and years[i] else None
            number = numbers[i] if i < len(numbers) and numbers[i] else None
            rows.append({"case_id": case_id, "patent_year_raw": year, "patent_number": number})

    return pd.DataFrame(rows)


# ════════════════════════════════════════════════════════════════
# Diagnostic: suspected row-level column shifts (never modifies data)
# ════════════════════════════════════════════════════════════════
def diagnose_shifted_rows(df_before_cleaning: pd.DataFrame, id_col: str) -> pd.DataFrame:
    suspects = []

    for field, own_whitelist, neighbor_whitelist in SHIFT_CHECK_CHAIN:
        if field not in df_before_cleaning.columns:
            continue
        neighbor_set = (
            {"yes", "no", "n/a"} if neighbor_whitelist == "yesno"
            else {str(v).lower() for v in neighbor_whitelist}
        )
        own_set = {str(v).lower() for v in own_whitelist}
        for _, row in df_before_cleaning.iterrows():
            val = row[field]
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            if val_str.lower() in own_set:
                continue
            if val_str.lower() in neighbor_set:
                suspects.append({
                    "case_id": row[id_col],
                    "field": field,
                    "value_found": val_str,
                    "matches_whitelist_of": "preceding field",
                    "confidence": "high — exact match to neighboring field's whitelist",
                })

    for field in SHIFT_SUSPECT_YESNO_FIELDS:
        if field not in df_before_cleaning.columns:
            continue
        field_overrides = FIELD_SPECIFIC_NA_OVERRIDES.get(field, set())
        for _, row in df_before_cleaning.iterrows():
            val = row[field]
            if pd.isna(val):
                continue
            val_str = str(val).strip()
            if val_str.lower() in field_overrides:
                continue
            if val_str.lower() not in _YES_VALUES | _NO_VALUES | _NA_VALUES:
                suspects.append({
                    "case_id": row[id_col],
                    "field": field,
                    "value_found": val_str[:80] + ("..." if len(val_str) > 80 else ""),
                    "matches_whitelist_of": "unknown neighboring free-text field",
                    "confidence": "medium — not Yes/No-shaped, but no whitelist to confirm which field it belongs to",
                })

    columns = ["case_id", "field", "value_found", "matches_whitelist_of", "confidence"]
    return pd.DataFrame(suspects, columns=columns)


def correct_academia_industry_shift(df: pd.DataFrame, id_col: str, report: QualityReport) -> pd.DataFrame:
    if "Academia or Industry" not in df.columns or "Company or Institution Name" not in df.columns:
        return df

    mask = df["Academia or Industry"].isna() & df["Company or Institution Name"].isin(["Academia", "Industry"])
    n_affected = int(mask.sum())
    if n_affected == 0:
        return df

    start_idx = list(df.columns).index("Academia or Industry")
    cols_from_start = list(df.columns[start_idx:])
    cols_after_start = cols_from_start[1:]

    affected_case_ids = df.loc[mask, id_col].tolist()

    for row_idx in df[mask].index:
        shifted_values = df.loc[row_idx, cols_after_start].tolist()
        shifted_values.append(pd.NA)
        df.loc[row_idx, cols_from_start] = shifted_values

    report.flag(
        f"Corrected {n_affected} row(s) with a verified 'Academia or Industry' "
        f"blank-cell shift (every field from 'Company or Institution Name' "
        f"onward shifted back one position). Affected case_ids: {affected_case_ids}",
        "WARNING",
    )
    return df


# ════════════════════════════════════════════════════════════════
# Year parsing
# ════════════════════════════════════════════════════════════════
def _parse_year_value(raw):
    """Returns (year: int or pd.NA, qualifier: 'approximate' | 'expected' | None)."""
    if pd.isna(raw):
        return pd.NA, None
    s = str(raw).strip()
    if not s:
        return pd.NA, None

    low = s.lower()
    is_expected = bool(re.search(r"\bexpected\b", low))
    is_approximate = bool(re.search(r"\b(circa|ca\.?|c\.|approx\.?|approximately)\b", low)) or bool(re.search(r"~", s))
    qualifier = "expected" if is_expected else ("approximate" if is_approximate else None)

    decade_match = re.search(r"\b(early|mid|late)?\s*'?(\d{2,4})'?s\b", low)
    if decade_match:
        modifier, digits = decade_match.groups()
        digits = int(digits)
        decade = 1900 + digits if digits < 100 else (digits // 10) * 10
        offset = {"early": 2, "mid": 5, "late": 8}.get(modifier, 0)
        return decade + offset, qualifier

    range_match = re.search(r"(\d{4})\s*[-/\u2013]\s*(\d{2,4})", s)
    if range_match:
        y1_str, y2_str = range_match.groups()
        y1 = int(y1_str)
        y2 = (y1 // 100) * 100 + int(y2_str) if len(y2_str) == 2 else int(y2_str)
        return min(y1, y2), qualifier

    plain_match = re.search(r"\b(1[89]\d{2}|20\d{2})\b", s)
    if plain_match:
        return int(plain_match.group(1)), qualifier

    return pd.NA, None


def parse_year_field(df: pd.DataFrame, col: str, report: QualityReport) -> pd.DataFrame:
    if col not in df.columns:
        return df

    raw = df[col]
    parsed = raw.apply(_parse_year_value)
    years = parsed.apply(lambda t: t[0])
    qualifiers = parsed.apply(lambda t: t[1])

    two_digit_decade_flagged = raw.apply(
        lambda v: bool(re.search(r"\b(early|mid|late)?\s*'?(\d{2})'?s\b", str(v).lower()))
        if pd.notna(v) else False
    )
    unparsed_mask = raw.notna() & years.isna()
    n_unparsed = int(unparsed_mask.sum())
    n_two_digit = int(two_digit_decade_flagged.sum())

    if n_unparsed:
        examples = raw[unparsed_mask].unique().tolist()[:10]
        report.flag(
            f"Column '{col}': {n_unparsed} value(s) didn't match any known "
            f"year format and were left blank in '{col}_year' (original text "
            f"preserved in '{col}_year_raw'). Examples: {examples}",
            "ERROR",
        )
    if n_two_digit:
        report.flag(
            f"Column '{col}': {n_two_digit} value(s) used a 2-digit decade "
            f"(e.g. '70s') — assumed to mean 19_0s, not 20_0s. Worth a quick "
            f"check if any of these could genuinely be 2000s or later.",
            "WARNING",
        )

    idx = list(df.columns).index(col)
    df = df.drop(columns=[col])
    df.insert(idx, f"{col}_year", years.astype("Int64"))
    df.insert(idx + 1, f"{col}_year_raw", raw)
    df.insert(idx + 2, f"{col}_year_qualifier", qualifiers)
    return df


def clean_product_text_fields(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["Product Name", "Product Description"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: str(v).strip() if pd.notna(v) and str(v).strip() else pd.NA)
    return df


def generate_display_name(df: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    def _fallback(row):
        name = row.get("Product Name")
        if pd.notna(name):
            return str(name)
        mimic = row.get("Mimic")
        if pd.notna(mimic) and str(mimic).strip():
            return f"{str(mimic).strip()}-inspired design"
        company = row.get("Company or Institution Name")
        if pd.notna(company) and str(company).strip():
            return f"{str(company).strip()} project"
        return "Untitled case"

    df["display_name"] = df.apply(_fallback, axis=1)
    n_fallback = df["Product Name"].isna().sum()
    if n_fallback:
        report.flag(f"'display_name' used a fallback (not the real Product Name) for {n_fallback} row(s).", "WARNING")
    return df


def ensure_id_column(df: pd.DataFrame, report: QualityReport) -> tuple:
    def _as_clean_int(df: pd.DataFrame) -> pd.DataFrame:
        try:
            df["case_id"] = pd.to_numeric(df["case_id"], errors="coerce").astype("Int64")
        except (ValueError, TypeError):
            pass
        return df

    for candidate in ["Case Number", "Case number", "case_number", "ID", "Id"]:
        if candidate in df.columns:
            report.flag(f"Using existing '{candidate}' column as the case identifier.", "WARNING")
            df = df.rename(columns={candidate: "case_id"})
            return _as_clean_int(df), "case_id"

    if str(df.columns[0]).startswith("Unnamed"):
        report.flag(
            f"First column has a blank header (reads as '{df.columns[0]}') — "
            f"treating it as the real case identifier rather than generating a new one.",
            "WARNING",
        )
        df = df.rename(columns={df.columns[0]: "case_id"})
        return _as_clean_int(df), "case_id"

    report.flag(
        "No existing ID column found (checked 'Case Number', 'ID', a blank "
        "first-column header, etc.) — generated a new sequential case_id.",
        "ERROR",
    )
    df = df.reset_index(drop=True)
    df.insert(0, "case_id", df.index + 1)
    return df, "case_id"


# ════════════════════════════════════════════════════════════════
# Main pipeline
# ════════════════════════════════════════════════════════════════
def run_pipeline(input_path: Path, output_dir: Path):
    report = QualityReport()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading {input_path} ...")
    df = load_excel(input_path)
    print(f"  {len(df)} row(s), {len(df.columns)} column(s) loaded.")

    df = normalize_column_names(df, report)
    df, id_col = ensure_id_column(df, report)
    df = correct_academia_industry_shift(df, id_col, report)
    df = clean_product_text_fields(df)
    df = generate_display_name(df, report)
    for year_col in ["Concept Year", "Prototype Year", "Commercial Year"]:
        df = parse_year_field(df, year_col, report)
    df = drop_pii(df, report)
    df = drop_internal_methodology_fields(df)

    # Snapshot taken after exclusions but before value rewrites, so the
    # diagnostic sees raw text for everything that's still in scope.
    shift_diagnostics = diagnose_shifted_rows(df, id_col)

    df = normalize_yes_no(df, report)
    df = split_biom_type(df, report)
    df = blank_known_bad_values(df, report)
    df = blank_multivalue_continent(df, report)

    for col, whitelist in [
        ("Case Status", CASE_STATUS_WHITELIST),
        ("Product Phase", PRODUCT_PHASE_WHITELIST),
        ("Kingdom", KINGDOM_WHITELIST),
        ("Group", GROUP_WHITELIST),
        ("Phylum", PHYLUM_WHITELIST),
        ("Mimic System", ORGANIZATION_LEVEL_WHITELIST),
        ("Mimic Subsystem", ORGANIZATION_LEVEL_WHITELIST),
        ("Mimic Suprasystem", ORGANIZATION_LEVEL_WHITELIST),
        ("Process Type", PROCESS_TYPE_WHITELIST),
        ("Continent", CONTINENT_WHITELIST),
    ]:
        df = normalize_whitelist_case(df, col, whitelist, report)

    validate_whitelist(df, "Case Status", CASE_STATUS_WHITELIST, report)
    validate_whitelist(df, "Product Phase", PRODUCT_PHASE_WHITELIST, report)
    validate_whitelist(df, "Kingdom", KINGDOM_WHITELIST, report)
    validate_whitelist(df, "Group", GROUP_WHITELIST, report)
    validate_whitelist(df, "Phylum", PHYLUM_WHITELIST, report)
    validate_whitelist(df, "Mimic System", ORGANIZATION_LEVEL_WHITELIST, report)
    validate_whitelist(df, "Mimic Subsystem", ORGANIZATION_LEVEL_WHITELIST, report)
    validate_whitelist(df, "Mimic Suprasystem", ORGANIZATION_LEVEL_WHITELIST, report)
    validate_whitelist(df, "Process Type", PROCESS_TYPE_WHITELIST, report)
    validate_whitelist(df, "Continent", CONTINENT_WHITELIST, report)
    validate_whitelist(df, "BioM Intensity", BIOM_INTENSITY_WHITELIST, report)

    df, disciplines_df, keywords_df = extract_multi_value_tables(df, id_col, report)
    patents_df = extract_patents_table(df, id_col, report)
    if len(patents_df):
        parsed = patents_df["patent_year_raw"].apply(_parse_year_value)
        patents_df.insert(1, "patent_year", parsed.apply(lambda t: t[0]).astype("Int64"))
        patents_df["patent_year_qualifier"] = parsed.apply(lambda t: t[1])
        n_unparsed = int((patents_df["patent_year_raw"].notna() & patents_df["patent_year"].isna()).sum())
        if n_unparsed:
            examples = patents_df.loc[
                patents_df["patent_year_raw"].notna() & patents_df["patent_year"].isna(), "patent_year_raw"
            ].unique().tolist()[:10]
            report.flag(
                f"case_patents: {n_unparsed} patent_year value(s) didn't match any "
                f"known year format, left blank in 'patent_year'. Examples: {examples}",
                "ERROR",
            )
    drop_cols = [c for c in [PATENT_YEAR_FIELD, PATENT_NUMBER_FIELD] if c in df.columns]
    df = df.drop(columns=drop_cols)
    df, ecosystem_services_df = extract_ecosystem_services_table(df, id_col, report)

    cases_path = output_dir / "cases.csv"
    disciplines_path = output_dir / "case_disciplines.csv"
    keywords_path = output_dir / "case_keywords.csv"
    patents_path = output_dir / "case_patents.csv"
    services_path = output_dir / "case_ecosystem_services.csv"
    shift_path = output_dir / "suspected_shifted_rows.csv"

    df.to_csv(cases_path, index=False)
    disciplines_df.to_csv(disciplines_path, index=False)
    keywords_df.to_csv(keywords_path, index=False)
    patents_df.to_csv(patents_path, index=False)
    ecosystem_services_df.to_csv(services_path, index=False)
    shift_diagnostics.to_csv(shift_path, index=False)

    print(f"\nWrote:")
    print(f"  {cases_path}  ({len(df)} rows, {len(df.columns)} columns)")
    print(f"  {disciplines_path}  ({len(disciplines_df)} rows)")
    print(f"  {keywords_path}  ({len(keywords_df)} rows)")
    print(f"  {patents_path}  ({len(patents_df)} rows)")
    print(f"  {services_path}  ({len(ecosystem_services_df)} rows)")
    print(f"  {shift_path}  ({len(shift_diagnostics)} suspected row(s) — REVIEW BEFORE TRUSTING cases.csv)")

    report.print_summary()
    return df, disciplines_df, keywords_df, patents_df, ecosystem_services_df, shift_diagnostics, report


def main():
    parser = argparse.ArgumentParser(description="Clean the BioM Innovation Database Excel export")
    parser.add_argument("--input", required=True, help="Path to the Excel file")
    parser.add_argument("--output-dir", default="clean_output", help="Where to write the cleaned CSVs")
    args = parser.parse_args()

    run_pipeline(Path(args.input), Path(args.output_dir))


if __name__ == "__main__":
    main()
