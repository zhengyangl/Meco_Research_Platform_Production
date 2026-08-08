#!/usr/bin/env python
# coding: utf-8

# In[37]:


"""
NLP Feature Engineering Pipeline
=====================================================
Extracts structured attributes from raw WoS text fields and writes them
to the paper_features table.
"""

import argparse
import time
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values

# ════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════
DB_URI      = "postgresql://pipeline_user:me_dashboard@127.0.0.1:5432/me_dashboard"
FEATURE_SET = "nlp_v1"   # bump to 'nlp_v2' when methods are revised


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════
def _retire_features(cur, feature_key: str) -> int:
    """
    Mark all current rows for (feature_set, feature_key) as is_current=FALSE.
    """
    cur.execute(
        """
        UPDATE paper_features
           SET is_current = FALSE
         WHERE feature_set = %s
           AND feature_key = %s
           AND is_current  = TRUE
        """,
        (FEATURE_SET, feature_key),
    )
    return cur.rowcount


def _insert_features(cur, rows: list) -> int:
    """
    Bulk-insert feature rows into paper_features.
    """
    sql = """
        INSERT INTO paper_features
            (wos_id, feature_set, feature_key, feature_val, is_current)
        VALUES %s
    """
    execute_values(cur, sql, rows, page_size=2000)
    return len(rows)


# ════════════════════════════════════════════════════════════════
# WoS Categories Parsing
# ════════════════════════════════════════════════════════════════
def parse_wos_categories(conn) -> dict:
    """
    Split the semicolon-delimited wos_categories field into one
    paper_features row per category per paper.

    Input  : papers.wos_categories
             e.g. "Chemistry, Multidisciplinary; Engineering, Biomedical"
    Output : paper_features rows with feature_key='wos_category'
             e.g. ('WOS:001', 'nlp_v1', 'wos_category', 'Chemistry, Multidisciplinary', True)
    """
    print("\n" + "═" * 60)
    print("T5e · Parsing WoS Categories")
    print("═" * 60)
    t0 = time.time()
    cur = conn.cursor()

    # ── Read source data ─────────────────────────────────────────
    cur.execute("""
        SELECT wos_id, wos_categories
        FROM   papers
        WHERE  wos_categories IS NOT NULL
          AND  wos_categories <> ''
    """)
    source_rows = cur.fetchall()
    print(f"  Papers with wos_categories : {len(source_rows):,}")

    # ── Build feature rows ────────────────────────────────────────
    # Split on ';', strip whitespace, skip blanks.
    # One paper → potentially many category rows.
    feature_rows = []
    skipped_empty = 0

    for wos_id, cats_str in source_rows:
        cats = [c.strip() for c in cats_str.split(";") if c.strip()]
        if not cats:
            skipped_empty += 1
            continue
        for cat in cats:
            feature_rows.append((wos_id, FEATURE_SET, "wos_category", cat, True))

    unique_cats = len({r[3] for r in feature_rows})
    print(f"  Feature rows to insert     : {len(feature_rows):,}")
    print(f"  Unique category labels     : {unique_cats:,}")
    if skipped_empty:
        print(f"  Skipped (empty after split): {skipped_empty:,}")

    # ── Versioning: retire old rows before inserting new ones ────
    retired = _retire_features(cur, "wos_category")
    if retired > 0:
        print(f"  Retired old rows           : {retired:,}")

    # ── Insert ───────────────────────────────────────────────────
    _insert_features(cur, feature_rows)
    conn.commit()
    elapsed = time.time() - t0
    print(f"\n  ✓ Done in {elapsed:.1f}s")

    # ── Verification: top 15 categories ──────────────────────────
    print("\n  Top 15 WoS Categories in corpus:")
    cur.execute("""
        SELECT   feature_val,
                 COUNT(*)                        AS papers,
                 ROUND(COUNT(*) * 100.0
                     / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM     paper_features
        WHERE    feature_set = %s
          AND    feature_key = 'wos_category'
          AND    is_current  = TRUE
        GROUP BY feature_val
        ORDER BY papers DESC
        LIMIT    15
    """, (FEATURE_SET,))
    print(f"  {'Category':<52} {'Papers':>7}  {'%':>5}")
    print("  " + "-" * 66)
    for cat, n, pct in cur.fetchall():
        print(f"  {cat:<52} {n:>7,}  {pct:>4.1f}%")

    # ── Summary stats ─────────────────────────────────────────────
    cur.execute("""
        SELECT COUNT(DISTINCT wos_id) AS papers_covered,
               COUNT(*)               AS total_rows
        FROM   paper_features
        WHERE  feature_set = %s
          AND  feature_key = 'wos_category'
          AND  is_current  = TRUE
    """, (FEATURE_SET,))
    covered, total = cur.fetchone()
    print(f"\n  Papers covered : {covered:,} / {len(source_rows):,} "
          f"({covered/len(source_rows)*100:.1f}%)")
    print(f"  Total rows     : {total:,}")

    cur.close()
    return {"papers_covered": covered, "total_rows": total, "unique_cats": unique_cats}


# ════════════════════════════════════════════════════════════════
# Country Extraction 
# ════════════════════════════════════════════════════════════════
def extract_countries(conn) -> dict:
    """
    Extract standardised country names from papers.addresses.

    Input  : papers.addresses
    Output : paper_features rows with
               feature_key='country'       (all countries, one row each)
               feature_key='country_first' (first address segment only)

    Method:
      1. Strip author-group brackets [...]
      2. Split by ";"
      3. Take last comma-token from each segment → candidate country string
      4. Normalise via WoS alias dict + pycountry fuzzy lookup
    """
    import re
    import pycountry

    print("\n" + "═" * 60)
    print("T5b · Extracting Countries")
    print("═" * 60)
    t0 = time.time()
    cur = conn.cursor()

    # ── WoS-specific alias dictionary ────────────────────────────
    # WoS uses non-standard names for several countries. These must be
    # mapped BEFORE pycountry lookup, which won't recognise them.
    ALIASES = {
        # USA
        "usa": "United States",
        "u.s.a.": "United States",
        "u s a": "United States",
        "us": "United States",
        # China
        "peoples r china": "China",
        "peoples rep china": "China",
        "pr china": "China",
        "p.r. china": "China",
        "p r china": "China",
        "prc": "China",
        "china mainland": "China",
        # UK
        "england": "United Kingdom",
        "scotland": "United Kingdom",
        "wales": "United Kingdom",
        "northern ireland": "United Kingdom",
        "uk": "United Kingdom",
        "u.k.": "United Kingdom",
        "great britain": "United Kingdom",
        # South Korea
        "south korea": "South Korea",
        "korea": "South Korea",
        "rep korea": "South Korea",
        "republic of korea": "South Korea",
        "dem peoples rep korea": "North Korea",
        # Russia
        "russia": "Russia",
        "russian federation": "Russia",
        # Taiwan
        "taiwan": "Taiwan",
        "peoples r china taiwan": "Taiwan",
        # Iran
        "iran": "Iran",
        "islamic republic of iran": "Iran",
        # Czechia
        "czech republic": "Czechia",
        # Vietnam
        "viet nam": "Vietnam",
        # Other common WoS variants
        "uae": "United Arab Emirates",
        "u arab emirates": "United Arab Emirates",
        "saudi arabia": "Saudi Arabia",
        "ksa": "Saudi Arabia",
        "trinidad tobago": "Trinidad and Tobago",
        "bosnia & hercegovina": "Bosnia and Herzegovina",
        # WoS 截断 / 非标准写法
        "antigua & barbu":   "Antigua and Barbuda",
        "bosnia & herceg":   "Bosnia and Herzegovina",
        "brunei":            "Brunei Darussalam",
        "cote ivoire":       "Côte d'Ivoire",
        "curacao":           "Curaçao",
        "dominican rep":     "Dominican Republic",
        "kosovo":            "Kosovo",
        "macedonia":         "North Macedonia",
        "palestine":         "Palestine, State of",
        "turkey":            "Turkey",
        "turkiye":           "Turkey",
    }

    _pc_lookup = {}
    for _c in pycountry.countries:
        _pc_lookup[_c.name.lower()] = _c.name
        if hasattr(_c, 'common_name'):
            _pc_lookup[_c.common_name.lower()] = _c.name
        if hasattr(_c, 'official_name'):
            _pc_lookup[_c.official_name.lower()] = _c.name

    def normalise_country(raw: str) -> str | None:
        if not raw:
            return None

        clean = raw.strip().rstrip('.,;').strip()
        clean_lower = clean.lower()

        if not clean_lower:
            return None

        if clean_lower in ALIASES:
            return ALIASES[clean_lower]

        if clean_lower in _pc_lookup:
            return _pc_lookup[clean_lower]

        if ' ' in clean:
            last_word = clean.split()[-1].lower()
            if last_word in ALIASES:
                return ALIASES[last_word]
            if last_word in _pc_lookup:
                return _pc_lookup[last_word]

        return None  

    # ── Read source data ─────────────────────────────────────────
    cur.execute("""
        SELECT wos_id, addresses
        FROM   papers
        WHERE  addresses IS NOT NULL
          AND  addresses <> ''
    """)
    source_rows = cur.fetchall()
    print(f"  Papers with addresses : {len(source_rows):,}")

    # ── 1: collect every unique raw candidate string ────────
    print("  Pass 1: collecting unique country candidates...")
    raw_candidates = set()
    parsed_segments = {}   # wos_id → list of [last_token_per_segment]

    for wos_id, addresses in source_rows:
        clean_addr = re.sub(r'\[.*?\]', '', addresses)
        segments = [s.strip() for s in clean_addr.split(';') if s.strip()]
        tokens = []
        for seg in segments:
            parts = [p.strip() for p in seg.split(',') if p.strip()]
            if parts:
                tok = parts[-1]
                tokens.append(tok)
                raw_candidates.add(tok)
        parsed_segments[wos_id] = tokens

    print(f"  Unique raw candidates : {len(raw_candidates):,}  "
          f"(vs {sum(len(v) for v in parsed_segments.values()):,} total segments)")

    # ── 2: resolve every unique candidate exactly once ──────
    print("  Pass 2: resolving candidates (pycountry)...")
    resolution_cache = {}   # raw_string → canonical_name or None
    unresolved_samples = []

    for i, raw in enumerate(sorted(raw_candidates)):
        resolved = normalise_country(raw)
        resolution_cache[raw] = resolved
        if resolved is None and len(unresolved_samples) < 20:
            unresolved_samples.append(raw)
        if (i + 1) % 100 == 0:
            print(f"    {i+1}/{len(raw_candidates)} candidates resolved...", end="\r")

    resolved_count = sum(1 for v in resolution_cache.values() if v is not None)
    print(f"\n  Resolved : {resolved_count:,} / {len(raw_candidates):,} candidates "
          f"({resolved_count/len(raw_candidates)*100:.1f}%)")

    # ── Pass 3: build feature rows using the cache ────────────────
    print("  Pass 3: building feature rows...")
    country_rows   = []
    first_rows     = []
    failed         = 0

    for wos_id, tokens in parsed_segments.items():
        countries_this_paper = []
        for tok in tokens:
            resolved = resolution_cache.get(tok)
            if resolved and resolved not in countries_this_paper:
                countries_this_paper.append(resolved)

        for country in countries_this_paper:
            country_rows.append((wos_id, FEATURE_SET, 'country', country, True))

        if countries_this_paper:
            first_rows.append(
                (wos_id, FEATURE_SET, 'country_first', countries_this_paper[0], True)
            )
        else:
            failed += 1

    print(f"  Total 'country' rows   : {len(country_rows):,}")
    print(f"  Total 'country_first'  : {len(first_rows):,}")
    print(f"  Papers with no country : {failed:,}")
    if unresolved_samples:
        print(f"  Sample unresolved strings (up to 20):")
        for s in unresolved_samples:
            print(f"    '{s}'")

    # ── Versioning + Insert ───────────────────────────────────────
    for key, rows in [('country', country_rows), ('country_first', first_rows)]:
        retired = _retire_features(cur, key)
        if retired > 0:
            print(f"  Retired old '{key}' rows : {retired:,}")
        _insert_features(cur, rows)

    conn.commit()
    elapsed = time.time() - t0
    print(f"\n  ✓ Done in {elapsed:.1f}s")

    # ── Verification: top 20 countries ───────────────────────────
    print("\n  Top 20 Countries (all, not just first-author):")
    cur.execute("""
        SELECT   feature_val,
                 COUNT(*)                        AS papers,
                 ROUND(COUNT(*) * 100.0
                     / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM     paper_features
        WHERE    feature_set = %s
          AND    feature_key = 'country'
          AND    is_current  = TRUE
        GROUP BY feature_val
        ORDER BY papers DESC
        LIMIT    20
    """, (FEATURE_SET,))
    print(f"  {'Country':<35} {'Papers':>7}  {'%':>5}")
    print("  " + "-" * 50)
    for country, n, pct in cur.fetchall():
        print(f"  {country:<35} {n:>7,}  {pct:>4.1f}%")

    cur.execute("""
        SELECT COUNT(DISTINCT wos_id)
        FROM   paper_features
        WHERE  feature_set = %s
          AND  feature_key = 'country_first'
          AND  is_current  = TRUE
    """, (FEATURE_SET,))
    covered = cur.fetchone()[0]
    print(f"\n  Papers with country_first : {covered:,} / {len(source_rows):,} "
          f"({covered/len(source_rows)*100:.1f}%)")

    cur.close()
    return {
        "country_rows":  len(country_rows),
        "first_rows":    len(first_rows),
        "failed":        failed,
    }


# ════════════════════════════════════════════════════════════════
# Institution Standardisation
# ════════════════════════════════════════════════════════════════

def standardize_institutions(conn) -> dict:
    """
    T5a — Extract and clean institution names from papers.affiliations.

    The main cleaning steps are:
      1. Split by ";"
      2. Strip " - COUNTRY" suffixes added by some WoS exports
      3. Deduplicate within the same paper (preserving order)

    Outputs:
      feature_key='institution_top'  — first-author institution (single value)
      feature_key='institution_all'  — all unique institutions (one row each)
    """
    import re

    print("\n" + "═" * 60)
    print("T5a · Institution Standardization")
    print("═" * 60)
    t0 = time.time()
    cur = conn.cursor()

    # Regex to strip WoS country suffixes like " - China", " - UK", " - USA"
    # Pattern: space-dash-space followed by a short uppercase or title-case word
    # We strip these because the institution name itself is what matters
    # Administrative or umbrella organisations that should be skipped
    # when determining the first-author's actual research institution.
    # These appear in WoS affiliations as supervisory/funding bodies,
    # not as the place where the research was actually conducted.
    SKIP_LIST = {
        "ministry of education",
        "ministry of science and technology",
        "ministry of health",
        "chinese academy of engineering",          # umbrella, not a lab
        "chinese academy of social sciences",
        "national natural science foundation of china",
        "state key laboratory",                    # prefix, not institution
    }

    SUFFIX_RE = re.compile(r'\s*-\s*[A-Z][A-Za-z\s]{0,20}$')

    def clean_institution(raw: str) -> str:
        """Strip country suffix and extra whitespace from an institution name."""
        cleaned = SUFFIX_RE.sub('', raw.strip()).strip()
        # Also remove trailing parenthetical abbreviations that add no info
        return cleaned if cleaned else raw.strip()

    # ── Read source data ──────────────────────────────────────────
    cur.execute("""
        SELECT wos_id, affiliations
        FROM   papers
        WHERE  affiliations IS NOT NULL
          AND  affiliations <> ''
    """)
    source_rows = cur.fetchall()
    print(f"  Papers with affiliations : {len(source_rows):,}")

    # ── Build feature rows ────────────────────────────────────────
    top_rows = []    # feature_key='institution_top'
    all_rows = []    # feature_key='institution_all'
    skipped  = 0

    for wos_id, affiliations in source_rows:
        # Split by ";", clean each institution name
        raw_insts = [s.strip() for s in affiliations.split(';') if s.strip()]
        if not raw_insts:
            skipped += 1
            continue

        # Clean and deduplicate (preserving order)
        seen = set()
        cleaned_insts = []
        for raw in raw_insts:
            cleaned = clean_institution(raw)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                cleaned_insts.append(cleaned)

        if not cleaned_insts:
            skipped += 1
            continue

        # institution_top = first institution NOT in the skip list.
        # Skips administrative bodies like "Ministry of Education" that
        # appear as supervisory affiliations rather than research sites.
        institution_top = None

        for inst in cleaned_insts:
            if inst.lower() not in SKIP_LIST:
                institution_top = inst
                break
        # Fall back to the first institution if everything is in SKIP_LIST
        if institution_top is None:
            institution_top = cleaned_insts[0]

        top_rows.append(
            (wos_id, FEATURE_SET, 'institution_top', institution_top, True)
        )

        # institution_all = every unique institution for this paper
        for inst in cleaned_insts:
            all_rows.append(
                (wos_id, FEATURE_SET, 'institution_all', inst, True)
            )

    total_unique_insts = len({r[3] for r in all_rows})
    print(f"  institution_top rows     : {len(top_rows):,}")
    print(f"  institution_all rows     : {len(all_rows):,}")
    print(f"  Unique institution names : {total_unique_insts:,}")
    print(f"  Papers skipped           : {skipped:,}")

    # ── Versioning + Insert ───────────────────────────────────────
    for key, rows in [('institution_top', top_rows), ('institution_all', all_rows)]:
        retired = _retire_features(cur, key)
        if retired > 0:
            print(f"  Retired old '{key}' rows : {retired:,}")
        _insert_features(cur, rows)

    conn.commit()
    elapsed = time.time() - t0
    print(f"\n  ✓ Done in {elapsed:.1f}s")

    # ── Verification: top 20 institutions ────────────────────────
    print("\n  Top 20 Institutions (first-author):")
    cur.execute("""
        SELECT   feature_val,
                 COUNT(*)                        AS papers,
                 ROUND(COUNT(*) * 100.0
                     / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM     paper_features
        WHERE    feature_set = %s
          AND    feature_key = 'institution_top'
          AND    is_current  = TRUE
        GROUP BY feature_val
        ORDER BY papers DESC
        LIMIT    20
    """, (FEATURE_SET,))
    print(f"  {'Institution':<55} {'Papers':>6}  {'%':>5}")
    print("  " + "-" * 70)
    for inst, n, pct in cur.fetchall():
        print(f"  {inst:<55} {n:>6,}  {pct:>4.1f}%")

    # Coverage
    cur.execute("""
        SELECT COUNT(DISTINCT wos_id)
        FROM   paper_features
        WHERE  feature_set = %s
          AND  feature_key = 'institution_top'
          AND  is_current  = TRUE
    """, (FEATURE_SET,))
    covered = cur.fetchone()[0]
    print(f"\n  Coverage : {covered:,} / {len(source_rows):,} "
          f"({covered/len(source_rows)*100:.1f}%)")

    cur.close()
    return {
        "top_rows":          len(top_rows),
        "all_rows":          len(all_rows),
        "unique_insts":      total_unique_insts,
        "skipped":           skipped,
    }


# ════════════════════════════════════════════════════════════════
# Technology Clustering
# ════════════════════════════════════════════════════════════════

def cluster_technologies(conn) -> dict:
    """
    Planned approach:
      Step 1: lowercase + TF-IDF dedup → feature_key='technology_norm'
                      (~500-1000 unique labels from ~5000+ raw values)
      Step 2: BERTopic with nr_topics='auto' on normalised labels
                      → feature_key='technology_cluster' 
    """
    print("\n[T5d] cluster_technologies() — not yet implemented")
    return {}


# ════════════════════════════════════════════════════════════════
# Funding Organisation Standardisation
# ════════════════════════════════════════════════════════════════
def standardize_funding(conn) -> dict:
    """
    Extract standardised funding agency names from papers.funding_orgs.

    Strategy:
      1. Split each row by ";"
      2. Strip grant numbers (text inside brackets) and URLs
      3. Substring-match against a whitelist of top ~60 global funders
      4. Write feature_key='funding_top' (one row per matched funder per paper)
    """
    import re

    print("\n" + "═" * 60)
    print("T5c · Funding Organisation Standardization")
    print("═" * 60)
    t0 = time.time()
    cur = conn.cursor()

    # ── Whitelist: (canonical_name, [substrings_to_match]) ────────
    # Ordered from most specific to least specific to avoid false matches.
    # Substring matching is case-insensitive.
    FUNDER_WHITELIST = [
        # China
        ("National Natural Science Foundation of China (NSFC)",
            ["national natural science foundation of china", "nsfc",
             "natural science foundation of china",
             "national nature science foundation of china",
             "national natural science foundation"]),
        ("National Key R&D Program of China",
            ["national key research and development program",
             "national key r&d program"]),
        ("Chinese Academy of Sciences (CAS)",
            ["chinese academy of sciences"]),
        ("Ministry of Science and Technology of China",
            ["ministry of science and technology of china", "most china"]),
        ("China Postdoctoral Science Foundation",
            ["china postdoctoral science foundation"]),
        ("Fundamental Research Funds for Central Universities (China)",
            ["fundamental research funds for the central universities"]),
        ("Chinese Provincial/Municipal Science Foundation",
            ["natural science foundation of", "science and technology",
             "provincial key", "municipal science"]),


        # USA
        ("National Science Foundation (NSF)",
            ["national science foundation", " nsf "]),
        ("National Institutes of Health (NIH)",
            ["national institutes of health", " nih "]),
        ("Department of Energy (DOE)",
            ["department of energy", " doe "]),
        ("DARPA",
            ["darpa", "defense advanced research projects"]),
        ("National Aeronautics and Space Administration (NASA)",
            ["nasa", "national aeronautics and space administration"]),
        ("Army Research Office (ARO)",
            ["army research office", " aro "]),
        ("Office of Naval Research (ONR)",
            ["office of naval research", " onr "]),
        ("Air Force Office of Scientific Research (AFOSR)",
            ["air force office of scientific research", "afosr"]),

        # Europe (EU)
        ("European Research Council (ERC)",
            ["european research council", " erc "]),
        ("Horizon 2020 (EU)",
            ["horizon 2020", "horizon2020"]),
        ("Horizon Europe (EU)",
            ["horizon europe"]),
        ("Marie Curie / MSCA",
            ["marie curie", "marie sklodowska-curie", "msca"]),

        # UK
        ("EPSRC (UK)",
            ["engineering and physical sciences research council", "epsrc"]),
        ("BBSRC (UK)",
            ["biotechnology and biological sciences research council", "bbsrc"]),
        ("MRC (UK)",
            ["medical research council", " mrc "]),
        ("Wellcome Trust",
            ["wellcome trust"]),
        ("Royal Society (UK)",
            ["royal society"]),

        # Germany
        ("DFG (Germany)",
            ["deutsche forschungsgemeinschaft", " dfg "]),
        ("BMBF (Germany)",
            ["bundesministerium fur bildung", "bmbf"]),
        ("Helmholtz Association",
            ["helmholtz"]),
        ("Max Planck Society",
            ["max planck"]),

        # France
        ("ANR (France)",
            ["agence nationale de la recherche", " anr "]),
        ("CNRS (France)",
            ["centre national de la recherche scientifique", " cnrs "]),

        # Japan
        ("JSPS (Japan)",
            ["japan society for the promotion of science", "jsps"]),
        ("MEXT (Japan)",
            ["ministry of education, culture, sports, science", "mext"]),
        ("JST (Japan)",
            ["japan science and technology agency", " jst "]),
        ("AMED (Japan)",
            ["japan agency for medical research and development",
             "japanese agency for medical research", "amed"]),

        # South Korea
        ("NRF (Korea)",
            ["national research foundation of korea", "nrf korea",
             "national research foundation (nrf)"]),
        ("IITP (Korea)",
            ["institute of information", "iitp"]),

        # Canada
        ("NSERC (Canada)",
            ["natural sciences and engineering research council", "nserc"]),
        ("CIHR (Canada)",
            ["canadian institutes of health research", "cihr"]),
        ("SSHRC (Canada)",
            ["social sciences and humanities research council", "sshrc"]),
        ("FRQ (Quebec)",
            ["fonds de recherche du quebec", "fonds de recherche", "frq"]),

        # Australia
        ("ARC (Australia)",
            ["australian research council", " arc "]),
        ("NHMRC (Australia)",
            ["national health and medical research council", "nhmrc"]),

        # Switzerland
        ("SNSF (Switzerland)",
            ["swiss national science foundation", "snsf"]),
        ("FWF (Austria)",
            ["austrian science fund", " fwf "]),

        # Netherlands
        ("NWO (Netherlands)",
            ["netherlands organisation for scientific research", " nwo "]),

        # Singapore
        ("NRF (Singapore)",
            ["national research foundation, singapore",
             "national research foundation singapore"]),
        ("A*STAR (Singapore)",
            ["agency for science, technology and research", "a*star", "a-star"]),
        ("NSTC (Taiwan)",
            ["national science and technology council, taiwan",
             "national science and technology council taiwan",
             "ministry of science and technology, taiwan"]),

        # Spain
        ("MICINN / MCIN (Spain)",
            ["ministerio de ciencia", "micinn", " mcin ", "mcin/aei",
             "spanish ministry of science and innovation",
             "severo ochoa programme"]),
        ("Spanish Government / AEI",
            ["agencia estatal de investigacion", " aei "]),

        # Italy
        ("MIUR (Italy)",
            ["ministero dell'istruzione", "ministero istruzione", "miur"]),

        # India
        ("DST (India)",
            ["department of science and technology", " dst "]),
        ("SERB (India)",
            ["science and engineering research board", "serb"]),
        ("DBT (India)",
            ["department of biotechnology india", " dbt "]),
        ("CSIR (India)",
            ["council of scientific and industrial research", "csir"]),

        # Brazil
        ("FAPESP (Brazil)",
            ["fundacao de amparo", "fapesp"]),
        ("CNPq (Brazil)",
            ["conselho nacional de desenvolvimento", "cnpq"]),
        ("CAPES (Brazil)",
            ["coordenacao de aperfeicoamento", "capes"]),



        # China
        ("China Scholarship Council (CSC)",
            ["china scholarship council", " csc "]),

        # Germany
        ("Alexander von Humboldt Foundation",
            ["alexander von humboldt", "humboldt foundation", "avh"]),

        # EU / Europe
        ("European Space Agency (ESA)",
            ["european space agency", " esa "]),
        ("ERDF (EU Regional Development Fund)",
            ["european regional development fund", " erdf "]),

        # Greece
        ("HFRI (Greece)",
            ["hellenic foundation for research and innovation", "hfri"]),

        # Slovenia
        ("ARRS (Slovenia)",
            ["slovenian research agency", "arrs"]),

        # Ireland
        ("Irish Research Council",
            ["irish research council"]),

        # Malaysia
        ("FRGS (Malaysia)",
            ["fundamental research grant scheme", "frgs"]),

        # Iran
        ("NIMAD (Iran)",
            ["national institute for medical research development", "nimad"]),

        # Slovakia
        ("VEGA (Slovakia)",
            ["slovak academy of sciences vega", "vega grant", " vega "]),

        # Spain extra variants
        ("MICINN / MCIN (Spain)",
            ["ministerio de ciencia", "micinn", " mcin ", "mcin/aei",
             "spanish ministry of science and innovation",
             "severo ochoa programme"]),
    ]


    # Pre-compile: list of (canonical_name, [lower_substring, ...])
    COMPILED = [
        (name, [s.lower() for s in aliases])
        for name, aliases in FUNDER_WHITELIST
    ]

    def extract_funders(raw: str) -> list:
        """
        Split a funding_orgs string, clean each segment, and return
        all canonical funder names matched from the whitelist.
        """
        # Step 1: remove URLs
        cleaned = re.sub(r'https?://\S+', ' ', raw)
        # Step 2: remove grant numbers in brackets (keep the text before them)
        cleaned = re.sub(r'\[.*?\]', ' ', cleaned)
        # Step 3: remove parenthetical grant IDs like (Grant No. 12345)
        cleaned = re.sub(r'\(\s*[Gg]rant\s+\w+[\w\s,\.]*\)', ' ', cleaned)
        # Step 4: collapse whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Split by ";" and also by " and " to handle "NSF and NIH" patterns
        segments = re.split(r';', cleaned)

        found = []
        for seg in segments:
            seg_lower = seg.lower()
            for canonical, aliases in COMPILED:
                if canonical in found:
                    continue
                if any(alias in seg_lower for alias in aliases):
                    found.append(canonical)
                    break   # one match per segment

        return found

    # ── Read source data ──────────────────────────────────────────
    cur.execute("""
        SELECT wos_id, funding_orgs
        FROM   papers
        WHERE  funding_orgs IS NOT NULL
          AND  funding_orgs <> ''
    """)
    source_rows = cur.fetchall()
    print(f"  Papers with funding_orgs : {len(source_rows):,}")

    # ── Extract funders ───────────────────────────────────────────
    feature_rows = []
    papers_matched    = 0
    papers_no_match   = 0

    for wos_id, funding_orgs in source_rows:
        funders = extract_funders(funding_orgs)
        if funders:
            papers_matched += 1
            for f in funders:
                feature_rows.append(
                    (wos_id, FEATURE_SET, 'funding_top', f, True)
                )
        else:
            papers_no_match += 1

    print(f"  Papers matched           : {papers_matched:,}  "
          f"({papers_matched/len(source_rows)*100:.1f}%)")
    print(f"  Papers unmatched         : {papers_no_match:,}  "
          f"({papers_no_match/len(source_rows)*100:.1f}%)")
    print(f"  Total feature rows       : {len(feature_rows):,}")
    print(f"  Avg funders per paper    : "
          f"{len(feature_rows)/max(papers_matched,1):.1f}")

    # ── Versioning + Insert ───────────────────────────────────────
    retired = _retire_features(cur, 'funding_top')
    if retired > 0:
        print(f"  Retired old rows         : {retired:,}")
    _insert_features(cur, feature_rows)
    conn.commit()

    elapsed = time.time() - t0
    print(f"\n  ✓ Done in {elapsed:.1f}s")

    # ── Verification: top 25 funders ─────────────────────────────
    print("\n  Top 25 Funding Agencies:")
    cur.execute("""
        SELECT   feature_val,
                 COUNT(DISTINCT wos_id)          AS papers,
                 ROUND(COUNT(DISTINCT wos_id)
                     * 100.0
                     / SUM(COUNT(DISTINCT wos_id)) OVER (), 1) AS pct
        FROM     paper_features
        WHERE    feature_set = %s
          AND    feature_key = 'funding_top'
          AND    is_current  = TRUE
        GROUP BY feature_val
        ORDER BY papers DESC
        LIMIT    25
    """, (FEATURE_SET,))
    print(f"  {'Funder':<55} {'Papers':>7}  {'%':>5}")
    print("  " + "-" * 70)
    for funder, n, pct in cur.fetchall():
        print(f"  {funder:<55} {n:>7,}  {pct:>4.1f}%")

    cur.execute("""
        SELECT COUNT(DISTINCT wos_id)
        FROM   paper_features
        WHERE  feature_set = %s
          AND  feature_key = 'funding_top'
          AND  is_current  = TRUE
    """, (FEATURE_SET,))
    covered = cur.fetchone()[0]
    print(f"\n  Papers covered : {covered:,} / {len(source_rows):,} "
          f"({covered/len(source_rows)*100:.1f}%)")

    cur.close()
    return {
        "papers_matched":  papers_matched,
        "papers_unmatched": papers_no_match,
        "total_rows":      len(feature_rows),
    }


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════
TASK_MAP = {
    "wos_categories":  parse_wos_categories,
    "countries":       extract_countries,
    "institutions":    standardize_institutions,
    "technologies":    cluster_technologies,
    "funding":         standardize_funding,
}

def run_all(conn):
    """Run every task in dependency order."""
    results = {}
    for name, fn in TASK_MAP.items():
        results[name] = fn(conn)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MEco NLP feature engineering")
    parser.add_argument(
        "--task",
        choices=list(TASK_MAP.keys()) + ["all"],
        default="wos_categories",
        help="Which feature extraction task to run (default: wos_categories)",
    )
    args = parser.parse_args()

    print(f"Connecting to database…")
    conn = psycopg2.connect(DB_URI)
    print(f"Connected.  Running task: {args.task}")

    started = datetime.now(timezone.utc)
    if args.task == "all":
        run_all(conn)
    else:
        TASK_MAP[args.task](conn)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()

    conn.close()
    print(f"\nTotal elapsed: {elapsed:.1f}s · Connection closed.")


# In[6]:


conn = psycopg2.connect(DB_URI)
result = parse_wos_categories(conn)
conn.close()


# In[18]:


conn = psycopg2.connect(DB_URI)
result = extract_countries(conn)
conn.close()


# In[19]:


import psycopg2
import pandas as pd

DB_URI = "postgresql://pipeline_user:me_dashboard@127.0.0.1:5432/me_dashboard"
conn = psycopg2.connect(DB_URI)

cur = conn.cursor()
cur.execute("""
    SELECT affiliations 
    FROM papers 
    WHERE affiliations IS NOT NULL 
    LIMIT 20
""")
for row in cur.fetchall():
    print(repr(row[0][:150]))
    print()

print("--- First-author institution samples ---")
cur.execute("""
    SELECT SPLIT_PART(affiliations, ';', 1) AS first_inst
    FROM papers
    WHERE affiliations IS NOT NULL
    LIMIT 20
""")
for row in cur.fetchall():
    print(repr(row[0].strip()))

cur.close()
conn.close()


# In[24]:


conn = psycopg2.connect(DB_URI)
result = standardize_institutions(conn)
conn.close()


# In[22]:


conn = psycopg2.connect(DB_URI)
cur = conn.cursor()

cur.execute("""
    SELECT 
        ia.feature_val,
        COUNT(*) as n
    FROM paper_features ia
    WHERE ia.feature_set = 'nlp_v1'
      AND ia.feature_key = 'institution_all'
      AND ia.is_current = TRUE
      AND ia.feature_val != 'Ministry of Education'
      AND ia.wos_id IN (
          SELECT wos_id FROM paper_features
          WHERE feature_set = 'nlp_v1'
            AND feature_key = 'institution_top'
            AND feature_val = 'Ministry of Education'
            AND is_current = TRUE
      )
    GROUP BY ia.feature_val
    ORDER BY n DESC
    LIMIT 15
""")
print("真实机构（Ministry of Education 论文的其他机构）:")
for inst, n in cur.fetchall():
    print(f"  {inst:<55} {n:>5,}")

cur.close()
conn.close()


# In[25]:


import psycopg2
import pandas as pd

DB_URI = "postgresql://pipeline_user:me_dashboard@127.0.0.1:5432/me_dashboard"
conn = psycopg2.connect(DB_URI)
cur = conn.cursor()

cur.execute("""
    SELECT 
        COUNT(*)                                    AS total,
        COUNT(technology)                           AS has_tech,
        COUNT(DISTINCT technology)                  AS unique_raw
    FROM classifications
    WHERE is_current = TRUE AND decision = 'Y'
""")
row = cur.fetchone()
print(f"Total Y papers     : {row[0]:,}")
print(f"Has technology     : {row[1]:,}")
print(f"Unique raw values  : {row[2]:,}")

print()

cur.execute("""
    SELECT technology
    FROM classifications
    WHERE is_current = TRUE 
      AND decision = 'Y'
      AND technology IS NOT NULL
    ORDER BY RANDOM()
    LIMIT 50
""")
print("50 random technology values:")
for (tech,) in cur.fetchall():
    print(f"  {tech}")

cur.close()
conn.close()


# In[26]:


pip install bertopic sentence-transformers umap-learn hdbscan


# In[27]:


"""
Technology Clustering
Runs BERTopic on all 35,433 GPT-extracted technology phrases.
Outputs two files:
  - technology_clusters.csv   : cluster summary 
  - technology_assignments.csv: every wos_id → cluster_id mapping
"""
import psycopg2
import pandas as pd
import numpy as np
from bertopic import BERTopic
from sentence_transformers import SentenceTransformer

DB_URI = "postgresql://pipeline_user:me_dashboard@127.0.0.1:5432/me_dashboard"

# ── Step 1: Read all technology values ───────────────────────────
print("Reading technology values from database...")
conn = psycopg2.connect(DB_URI)
cur = conn.cursor()
cur.execute("""
    SELECT c.wos_id, c.technology
    FROM   classifications c
    WHERE  c.is_current = TRUE
      AND  c.decision   = 'Y'
      AND  c.technology IS NOT NULL
      AND  c.technology <> ''
""")
rows = cur.fetchall()
cur.close()
conn.close()

df_tech = pd.DataFrame(rows, columns=["wos_id", "technology"])
print(f"  Total rows      : {len(df_tech):,}")
print(f"  Unique values   : {df_tech['technology'].nunique():,}")

# ── Step 2: Embed unique phrases (each phrase embedded only once) ─
unique_phrases = df_tech["technology"].unique().tolist()
print(f"\nEmbedding {len(unique_phrases):,} unique phrases...")
print("  (This takes 3-8 minutes depending on your Mac — please wait)")

model = SentenceTransformer("all-MiniLM-L6-v2")
embeddings = model.encode(
    unique_phrases,
    batch_size=256,
    show_progress_bar=True,
    convert_to_numpy=True,
)
print(f"  Embeddings shape: {embeddings.shape}")

# ── Step 3: Run BERTopic ─────────────────────────────────────────
print("\nRunning BERTopic clustering...")
print("  (nr_topics='auto' — BERTopic will find the optimal number)")

topic_model = BERTopic(
    embedding_model=model,
    nr_topics="auto",       
    min_topic_size=30,      # each cluster must have ≥30 papers
    calculate_probabilities=False,
    verbose=True,
)
topics, _ = topic_model.fit_transform(unique_phrases, embeddings)

# Map topic assignments back to unique phrases
phrase_to_topic = dict(zip(unique_phrases, topics))
df_tech["cluster_id"] = df_tech["technology"].map(phrase_to_topic)

n_topics    = len(set(t for t in topics if t != -1))
n_outliers  = sum(1 for t in topics if t == -1)
print(f"\n  Clusters found  : {n_topics}")
print(f"  Outliers (-1)   : {n_outliers:,} phrases ({n_outliers/len(unique_phrases)*100:.1f}%)")

# ── Step 4: Build cluster summary CSV ────────────────────────────
print("\nBuilding cluster summary...")

topic_info = topic_model.get_topic_info()

summary_rows = []
for _, row in topic_info.iterrows():
    tid = row["Topic"]
    if tid == -1:
        continue
    # Get top 5 representative phrases for this cluster
    member_phrases = [p for p, t in phrase_to_topic.items() if t == tid]
    sample_5 = " || ".join(member_phrases[:5])
    summary_rows.append({
        "cluster_id":     tid,
        "auto_label":     row["Name"],       # BERTopic's auto label
        "count":          row["Count"],
        "sample_phrases": sample_5,
        "canonical_name": "",               # ← YOU FILL THIS IN
    })

# Add outlier row
n_outlier_papers = (df_tech["cluster_id"] == -1).sum()
summary_rows.append({
    "cluster_id":     -1,
    "auto_label":     "outliers",
    "count":          n_outlier_papers,
    "sample_phrases": "",
    "canonical_name": "Other",             # outliers → "Other"
})

df_summary = pd.DataFrame(summary_rows).sort_values("count", ascending=False)

# ── Step 5: Save both files ───────────────────────────────────────
import os
summary_path     = os.path.expanduser("~/Desktop/technology_clusters.csv")
assignments_path = os.path.expanduser("~/Desktop/technology_assignments.csv")

df_summary.to_csv(summary_path, index=False)
df_tech[["wos_id", "cluster_id"]].to_csv(assignments_path, index=False)

print(f"\n✓ Files saved:")
print(f"  {summary_path}")
print(f"  {assignments_path}")
print(f"\n── Cluster overview (top 30 by size) ─────────────────────")
print(f"  {'cluster_id':>10}  {'count':>7}  {'auto_label'}")
print("  " + "-" * 60)
for _, r in df_summary.head(30).iterrows():
    print(f"  {int(r['cluster_id']):>10}  {int(r['count']):>7,}  {r['auto_label']}")


# In[28]:


from sklearn.cluster import KMeans
N_CLUSTERS = 30   

print(f"Re-clustering with KMeans (k={N_CLUSTERS})...")
print("(Reusing existing embeddings — no re-encoding needed)")

kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init=10)

topic_model2 = BERTopic(
    embedding_model=model,
    hdbscan_model=kmeans,    
    calculate_probabilities=False,
    verbose=False,
)
topics2, _ = topic_model2.fit_transform(unique_phrases, embeddings)


phrase_to_topic2 = dict(zip(unique_phrases, topics2))
df_tech["cluster_id"] = df_tech["technology"].map(phrase_to_topic2)

n_outliers2 = sum(1 for t in topics2 if t == -1)
print(f"  Clusters found : {len(set(topics2)):,}")
print(f"  Outliers       : {n_outliers2}")   # 应该是 0

# ── summary CSV ─────────────────────────────────────────
topic_info2 = topic_model2.get_topic_info()

summary_rows2 = []
for _, row in topic_info2.iterrows():
    tid = row["Topic"]
    if tid == -1:
        continue
    member_phrases = [p for p, t in phrase_to_topic2.items() if t == tid]
    sample_8 = " || ".join(member_phrases[:8])
    summary_rows2.append({
        "cluster_id":     tid,
        "count":          row["Count"],
        "auto_label":     row["Name"],
        "sample_phrases": sample_8,
        "canonical_name": "", 
    })

df_summary2 = pd.DataFrame(summary_rows2).sort_values("count", ascending=False)


import os
summary_path     = os.path.expanduser("~/Desktop/technology_clusters.csv")
assignments_path = os.path.expanduser("~/Desktop/technology_assignments.csv")

df_summary2.to_csv(summary_path, index=False)
df_tech[["wos_id", "cluster_id"]].to_csv(assignments_path, index=False)

print(f"\n✓ Files updated:")
print(f"  {summary_path}")
print(f"  {assignments_path}")
print(f"\n── All {N_CLUSTERS} clusters (sorted by size) ──────────────")
print(f"  {'ID':>4}  {'Count':>7}  Auto label")
print("  " + "-" * 65)
for _, r in df_summary2.iterrows():
    print(f"  {int(r['cluster_id']):>4}  {int(r['count']):>7,}  {r['auto_label'][:55]}")


# In[29]:


"""
Write named technology clusters to paper_features
================================================================
Prerequisites:
  - ~/Desktop/technology_clusters.csv   
  - ~/Desktop/technology_assignments.csv 
"""

import os
import time
import psycopg2
import pandas as pd
from psycopg2.extras import execute_values

DB_URI      = "postgresql://pipeline_user:me_dashboard@127.0.0.1:5432/me_dashboard"
FEATURE_SET = "nlp_v1"

CLUSTERS_PATH     = os.path.expanduser("~/Desktop/technology_clusters.csv")
ASSIGNMENTS_PATH  = os.path.expanduser("~/Desktop/technology_assignments.csv")

# ── Step 1: Load and validate the reviewed CSV ────────────────────
print("Loading CSVs...")
df_clusters     = pd.read_csv(CLUSTERS_PATH)
df_assignments  = pd.read_csv(ASSIGNMENTS_PATH)

print(f"  Clusters CSV    : {len(df_clusters)} rows")
print(f"  Assignments CSV : {len(df_assignments):,} rows")

# Check that canonical_name is fully filled
missing = df_clusters["canonical_name"].isna() | (df_clusters["canonical_name"].str.strip() == "")
if missing.any():
    print(f"\n WARNING: {missing.sum()} cluster(s) have empty canonical_name:")
    print(df_clusters[missing][["cluster_id", "auto_label", "count"]])
    print("\nPlease fill in all canonical_name values and re-run.")
    raise ValueError("canonical_name column is not fully filled.")

# Show the final mapping
print("\n  Final canonical_name mapping:")
for _, r in df_clusters.sort_values("cluster_id").iterrows():
    print(f"    cluster {int(r['cluster_id']):>3}  →  {r['canonical_name']}")

# ── Step 2: Build wos_id → canonical_name mapping ────────────────
print("\nBuilding wos_id → canonical_name mapping...")
cluster_to_name = df_clusters.set_index("cluster_id")["canonical_name"].to_dict()
df_assignments["canonical_name"] = df_assignments["cluster_id"].map(cluster_to_name)

# Check for unmapped (outliers with cluster_id = -1 get "Other" if present)
unmapped = df_assignments["canonical_name"].isna()
if unmapped.any():
    n = unmapped.sum()
    print(f"  {n:,} rows with no canonical_name → assigning 'Other'")
    df_assignments.loc[unmapped, "canonical_name"] = "Other"

print(f"  Mapped {len(df_assignments):,} papers to {df_assignments['canonical_name'].nunique()} clusters")

# Show distribution
print("\n  Cluster distribution:")
dist = df_assignments.groupby("canonical_name").size().sort_values(ascending=False)
for name, count in dist.items():
    pct = count / len(df_assignments) * 100
    print(f"    {name:<55} {count:>6,}  ({pct:>4.1f}%)")

# ── Step 3: Write to paper_features ──────────────────────────────
print("\nWriting to paper_features table...")
t0 = time.time()
conn = psycopg2.connect(DB_URI)
cur  = conn.cursor()

# Versioning: retire old technology_cluster rows
cur.execute("""
    UPDATE paper_features
       SET is_current = FALSE
     WHERE feature_set = %s
       AND feature_key = 'technology_cluster'
       AND is_current  = TRUE
""", (FEATURE_SET,))
retired = cur.rowcount
if retired > 0:
    print(f"  Retired old rows : {retired:,}")

# Build and insert new rows
feature_rows = [
    (row["wos_id"], FEATURE_SET, "technology_cluster", row["canonical_name"], True)
    for _, row in df_assignments.iterrows()
]

execute_values(cur, """
    INSERT INTO paper_features
        (wos_id, feature_set, feature_key, feature_val, is_current)
    VALUES %s
""", feature_rows, page_size=2000)

conn.commit()
elapsed = time.time() - t0
print(f"  Inserted : {len(feature_rows):,} rows")
print(f"  ✓ Done in {elapsed:.1f}s")

# ── Step 4: Verification ──────────────────────────────────────────
print("\nVerification:")
cur.execute("""
    SELECT   feature_val,
             COUNT(*)                        AS papers,
             ROUND(COUNT(*) * 100.0
                 / SUM(COUNT(*)) OVER (), 1) AS pct
    FROM     paper_features
    WHERE    feature_set = %s
      AND    feature_key = 'technology_cluster'
      AND    is_current  = TRUE
    GROUP BY feature_val
    ORDER BY papers DESC
""", (FEATURE_SET,))
print(f"  {'Cluster':<55} {'Papers':>7}  {'%':>5}")
print("  " + "-" * 70)
for name, n, pct in cur.fetchall():
    print(f"  {name:<55} {n:>7,}  {pct:>4.1f}%")

cur.execute("""
    SELECT COUNT(DISTINCT wos_id)
    FROM   paper_features
    WHERE  feature_set = %s
      AND  feature_key = 'technology_cluster'
      AND  is_current  = TRUE
""", (FEATURE_SET,))
covered = cur.fetchone()[0]
print(f"\n  Papers covered : {covered:,} / {len(df_assignments):,} "
      f"({covered/len(df_assignments)*100:.1f}%)")

cur.close()
conn.close()
print("\n✓ T5d complete.")


# In[30]:


conn = psycopg2.connect(DB_URI)
cur = conn.cursor()

cur.execute("""
    SELECT 
        COUNT(*)                    AS total,
        COUNT(funding_orgs)         AS has_funding,
        COUNT(DISTINCT funding_orgs) AS unique_raw
    FROM papers
""")
row = cur.fetchone()
print(f"Total papers       : {row[0]:,}")
print(f"Has funding_orgs   : {row[1]:,}  ({row[1]/row[0]*100:.1f}%)")
print(f"Unique raw values  : {row[2]:,}")

print("\n20 random samples:")
cur.execute("""
    SELECT funding_orgs 
    FROM papers 
    WHERE funding_orgs IS NOT NULL
    ORDER BY RANDOM() 
    LIMIT 20
""")
for (f,) in cur.fetchall():
    print(f"  {f[:120]}")

cur.close()
conn.close()


# In[38]:


conn = psycopg2.connect(DB_URI)
result = standardize_funding(conn)
conn.close()


# In[36]:


import re
conn = psycopg2.connect(DB_URI)
cur = conn.cursor()

cur.execute("""
    SELECT p.funding_orgs
    FROM   papers p
    WHERE  p.funding_orgs IS NOT NULL
      AND  p.wos_id NOT IN (
          SELECT DISTINCT wos_id
          FROM   paper_features
          WHERE  feature_set = 'nlp_v1'
            AND  feature_key = 'funding_top'
            AND  is_current  = TRUE
      )
    LIMIT 200
""")
unmatched_rows = [r[0] for r in cur.fetchall()]
cur.close()
conn.close()

CLEAN_RE = re.compile(r'\[.*?\]|https?://\S+|\(\s*[Gg]rant.*?\)')
tokens = []
for raw in unmatched_rows:
    cleaned = CLEAN_RE.sub(' ', raw)
    for seg in cleaned.split(';'):
        seg = seg.strip()
        if len(seg) > 5:
            tokens.append(seg[:80])

print("Sample unmatched funding segments (first 50):")
for t in tokens[:50]:
    print(f"  {t}")
