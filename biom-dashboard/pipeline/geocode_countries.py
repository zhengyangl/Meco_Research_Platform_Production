"""
geocode_countries.py — Adds standardized geographic codes to cases.csv.

Runs as a second stage after clean_biom_data.py. Country and Continent are
kept as-is (they're already clean, whitelist-validated fields); this adds
two new columns so app.py never needs to do country-name matching itself:

    country_iso3            ISO 3166-1 alpha-3 code (e.g. "USA"), blank if unmatched
    country_name_canonical  pycountry's official name (e.g. "United States"), blank if unmatched

Usage:
    python geocode_countries.py --input data/clean/cases.csv
    python geocode_countries.py --input data/clean/cases.csv --output data/clean/cases_geocoded.csv
"""

import argparse
from pathlib import Path

import pandas as pd
import pycountry

# Variants pycountry's fuzzy matcher doesn't reliably resolve on its own.
# Not exhaustive — anything else falls through to the unmapped list printed
# at the end, rather than being silently dropped.
COUNTRY_ALIASES = {
    "usa": "USA", "u.s.a.": "USA", "u.s.": "USA", "united states": "USA",
    "uk": "GBR", "u.k.": "GBR", "great britain": "GBR",
    "south korea": "KOR", "korea": "KOR",
    "russia": "RUS", "vietnam": "VNM", "iran": "IRN",
}


def resolve_country(raw: str):
    """Returns (iso3_code, canonical_name), both None if unmatched."""
    key = str(raw).strip().lower()
    if key in COUNTRY_ALIASES:
        code = COUNTRY_ALIASES[key]
        match = pycountry.countries.get(alpha_3=code)
        return code, (match.name if match else None)
    try:
        match = pycountry.countries.search_fuzzy(str(raw).strip())[0]
        return match.alpha_3, match.name
    except LookupError:
        return None, None


def geocode_cases(df: pd.DataFrame) -> tuple:
    unique_countries = df["Country"].dropna().unique()
    lookup = {c: resolve_country(c) for c in unique_countries}

    df = df.copy()
    df["country_iso3"] = df["Country"].map(lambda c: lookup[c][0] if pd.notna(c) else None)
    df["country_name_canonical"] = df["Country"].map(lambda c: lookup[c][1] if pd.notna(c) else None)

    unmapped = sorted([c for c, (code, _) in lookup.items() if code is None])
    return df, unmapped


def main():
    parser = argparse.ArgumentParser(description="Add ISO3 geocoding columns to cases.csv")
    parser.add_argument("--input", required=True, help="Path to cases.csv")
    parser.add_argument("--output", default=None, help="Output path (defaults to overwriting --input)")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path

    df = pd.read_csv(input_path)
    if "Country" not in df.columns:
        raise SystemExit(f"'{input_path}' has no 'Country' column — is this the right file?")

    df, unmapped = geocode_cases(df)

    n_total = int(df["Country"].notna().sum())
    n_mapped = int(df["country_iso3"].notna().sum())
    n_distinct = df["country_iso3"].nunique()
    print(f"Geocoded {n_mapped} of {n_total} rows with a Country value ({n_distinct} distinct countries).")

    if unmapped:
        print(f"\n{len(unmapped)} country value(s) could not be matched and were left blank:")
        for c in unmapped:
            print(f"  - {c!r}")
        print("\nIf any of these are a real country under an unusual name, add it to")
        print("COUNTRY_ALIASES above and re-run. Otherwise it's a genuinely invalid")
        print("Country value and should stay unmapped, not guessed at.")

    df.to_csv(output_path, index=False)
    print(f"\nWrote {output_path}")


if __name__ == "__main__":
    main()
