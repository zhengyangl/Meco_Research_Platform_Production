#!/usr/bin/env python
# coding: utf-8

"""
NLP feature engineering for the MEco corpus.

Derives structured attributes from raw WoS text fields in `papers` (WoS categories,
countries, institutions, technology clusters, funders) and writes them to the
paper_features table, tagged with FEATURE_SET.

Requires DATABASE_URL (postgresql://user:password@host:5432/dbname), read at import.
Usage:
    python text_analysis.py --task {wos_categories,countries,institutions,technologies,funding,all}
"""

import argparse
import time
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values

# Config
def get_db_uri() -> str:
    """Return DATABASE_URL from the environment; raise EnvironmentError if unset."""
    import os
    uri = os.environ.get("DATABASE_URL")
    if not uri:
        raise EnvironmentError(
            "DATABASE_URL is not set.\n"
            "  export DATABASE_URL='postgresql://user:password@host:5432/dbname'"
        )
    return uri

DB_URI      = get_db_uri()
FEATURE_SET = "nlp_v1"   # feature_set value written on every row


# Helpers
def _retire_features(cur, feature_key: str) -> int:
    """Set is_current = FALSE on current rows for FEATURE_SET and feature_key; return count."""
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
    """Bulk-insert (wos_id, feature_set, feature_key, feature_val, is_current) rows."""
    sql = """
        INSERT INTO paper_features
            (wos_id, feature_set, feature_key, feature_val, is_current)
        VALUES %s
    """
    execute_values(cur, sql, rows, page_size=2000)
    return len(rows)


# WoS categories
def parse_wos_categories(conn) -> dict:
    """Split papers.wos_categories on ";" into one 'wos_category' row per category."""
    print("\n" + "═" * 60)
    print("T5e · Parsing WoS Categories")
    print("═" * 60)
    t0 = time.time()
    cur = conn.cursor()

    cur.execute("""
        SELECT wos_id, wos_categories
        FROM   papers
        WHERE  wos_categories IS NOT NULL
          AND  wos_categories <> ''
    """)
    source_rows = cur.fetchall()
    print(f"  Papers with wos_categories : {len(source_rows):,}")

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

    retired = _retire_features(cur, "wos_category")
    if retired > 0:
        print(f"  Retired old rows           : {retired:,}")

    _insert_features(cur, feature_rows)
    conn.commit()
    elapsed = time.time() - t0
    print(f"\n  ✓ Done in {elapsed:.1f}s")

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


# Countries
def extract_countries(conn) -> dict:
    """
    Extract country names from papers.addresses into 'country' and 'country_first' rows.

    'country' has each distinct resolved country per paper; 'country_first' is the first
    of those. Candidate = last comma-separated token of each ";" segment after removing
    [...] author groups; resolved via an alias dict, then pycountry names.
    """
    import re
    import pycountry

    print("\n" + "═" * 60)
    print("T5b · Extracting Countries")
    print("═" * 60)
    t0 = time.time()
    cur = conn.cursor()

    # WoS spellings that pycountry does not recognise; checked before the pycountry lookup.
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
        # Truncated or non-standard WoS spellings
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

    cur.execute("""
        SELECT wos_id, addresses
        FROM   papers
        WHERE  addresses IS NOT NULL
          AND  addresses <> ''
    """)
    source_rows = cur.fetchall()
    print(f"  Papers with addresses : {len(source_rows):,}")

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

    for key, rows in [('country', country_rows), ('country_first', first_rows)]:
        retired = _retire_features(cur, key)
        if retired > 0:
            print(f"  Retired old '{key}' rows : {retired:,}")
        _insert_features(cur, rows)

    conn.commit()
    elapsed = time.time() - t0
    print(f"\n  ✓ Done in {elapsed:.1f}s")

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


# Institutions

def standardize_institutions(conn) -> dict:
    """
    Clean papers.affiliations into 'institution_top' and 'institution_all' rows.

    Splits on ";", strips " - COUNTRY" suffixes and de-duplicates per paper in order.
    institution_top is the first institution not in SKIP_LIST (else the first one).
    """
    import re

    print("\n" + "═" * 60)
    print("T5a · Institution Standardization")
    print("═" * 60)
    t0 = time.time()
    cur = conn.cursor()

    # Administrative or umbrella bodies skipped when choosing institution_top.
    SKIP_LIST = {
        "ministry of education",
        "ministry of science and technology",
        "ministry of health",
        "chinese academy of engineering",          # umbrella, not a lab
        "chinese academy of social sciences",
        "national natural science foundation of china",
        "state key laboratory",                    # prefix, not institution
    }

    # Trailing country suffix such as " - China".
    SUFFIX_RE = re.compile(r'\s*-\s*[A-Z][A-Za-z\s]{0,20}$')

    def clean_institution(raw: str) -> str:
        """Strip country suffix and extra whitespace from an institution name."""
        cleaned = SUFFIX_RE.sub('', raw.strip()).strip()
        return cleaned if cleaned else raw.strip()

    cur.execute("""
        SELECT wos_id, affiliations
        FROM   papers
        WHERE  affiliations IS NOT NULL
          AND  affiliations <> ''
    """)
    source_rows = cur.fetchall()
    print(f"  Papers with affiliations : {len(source_rows):,}")

    top_rows = []    # feature_key='institution_top'
    all_rows = []    # feature_key='institution_all'
    skipped  = 0

    for wos_id, affiliations in source_rows:
        raw_insts = [s.strip() for s in affiliations.split(';') if s.strip()]
        if not raw_insts:
            skipped += 1
            continue

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

        institution_top = None

        for inst in cleaned_insts:
            if inst.lower() not in SKIP_LIST:
                institution_top = inst
                break
        # Every institution is in SKIP_LIST
        if institution_top is None:
            institution_top = cleaned_insts[0]

        top_rows.append(
            (wos_id, FEATURE_SET, 'institution_top', institution_top, True)
        )

        for inst in cleaned_insts:
            all_rows.append(
                (wos_id, FEATURE_SET, 'institution_all', inst, True)
            )

    total_unique_insts = len({r[3] for r in all_rows})
    print(f"  institution_top rows     : {len(top_rows):,}")
    print(f"  institution_all rows     : {len(all_rows):,}")
    print(f"  Unique institution names : {total_unique_insts:,}")
    print(f"  Papers skipped           : {skipped:,}")

    for key, rows in [('institution_top', top_rows), ('institution_all', all_rows)]:
        retired = _retire_features(cur, key)
        if retired > 0:
            print(f"  Retired old '{key}' rows : {retired:,}")
        _insert_features(cur, rows)

    conn.commit()
    elapsed = time.time() - t0
    print(f"\n  ✓ Done in {elapsed:.1f}s")

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


# Technology clustering

_EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
# Assignments with cosine similarity below this are still made but counted and reported.
_LOW_CONFIDENCE_SIMILARITY = 0.35


def _get_embedder():
    """Load the embedding model; sentence-transformers is imported lazily (this task only)."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise ImportError(
            "sentence-transformers is required for cluster_technologies(). "
            "pip install sentence-transformers --break-system-packages "
            "(see requirements_pipeline.txt)."
        ) from e
    return SentenceTransformer(_EMBEDDING_MODEL_NAME)


def _cosine_sim_matrix(a, b):
    import numpy as np
    a_norm = a / np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = b / np.linalg.norm(b, axis=1, keepdims=True)
    return a_norm @ b_norm.T


def cluster_technologies(conn) -> dict:
    """
    Assign technology_cluster to papers lacking one, by nearest centroid (cosine).

    Centroids are recomputed each run from the embeddings of classifications.technology
    for papers that already have a current technology_cluster label. Only decision = 'Y'
    papers without a current label are assigned; existing labels are never retired or
    changed, so a paper whose technology changes later is not re-assigned.
    """
    print("\n" + "═" * 60)
    print("T5d · Technology Clustering (nearest-centroid)")
    print("═" * 60)
    t0 = time.time()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT c.technology, pf.feature_val
        FROM classifications c
        JOIN paper_features pf ON c.wos_id = pf.wos_id
        WHERE c.is_current = TRUE
          AND pf.feature_set = %s AND pf.feature_key = 'technology_cluster'
          AND pf.is_current = TRUE
          AND c.technology IS NOT NULL AND c.technology <> ''
        """,
        (FEATURE_SET,),
    )
    ground_truth = cur.fetchall()
    if not ground_truth:
        print("  No existing technology_cluster ground truth found in paper_features — "
              "cannot compute centroids. (Has the original 25-cluster labeling been "
              "loaded into the database?)")
        cur.close()
        return {"assigned": 0, "clusters": 0}

    import numpy as np
    from collections import defaultdict

    embedder = _get_embedder()
    texts = [row[0] for row in ground_truth]
    labels = [row[1] for row in ground_truth]
    ground_truth_embeddings = embedder.encode(texts, show_progress_bar=False)

    vectors_by_cluster = defaultdict(list)
    for vec, cluster_name in zip(ground_truth_embeddings, labels):
        vectors_by_cluster[cluster_name].append(vec)
    centroid_names = sorted(vectors_by_cluster.keys())
    centroids = np.array([np.mean(vectors_by_cluster[c], axis=0) for c in centroid_names])
    print(f"  Recomputed {len(centroid_names)} cluster centroid(s) from "
          f"{len(texts):,} currently-labeled paper(s)")

    cur.execute(
        """
        SELECT c.wos_id, c.technology
        FROM classifications c
        WHERE c.is_current = TRUE
          AND c.decision = 'Y'
          AND c.technology IS NOT NULL AND c.technology <> ''
          AND NOT EXISTS (
              SELECT 1 FROM paper_features pf
              WHERE pf.wos_id = c.wos_id AND pf.feature_set = %s
                AND pf.feature_key = 'technology_cluster' AND pf.is_current = TRUE
          )
        """,
        (FEATURE_SET,),
    )
    new_papers = cur.fetchall()
    print(f"  Papers needing technology_cluster assignment: {len(new_papers):,}")

    if not new_papers:
        print("  Nothing new to assign.")
        cur.close()
        return {"assigned": 0, "clusters": len(centroid_names)}

    new_wos_ids = [r[0] for r in new_papers]
    new_texts = [r[1] for r in new_papers]
    new_embeddings = np.array(embedder.encode(new_texts, show_progress_bar=False))

    sims = _cosine_sim_matrix(new_embeddings, centroids)
    best_idx = sims.argmax(axis=1)
    best_sim = sims.max(axis=1)

    feature_rows = []
    n_low_confidence = 0
    for wos_id, idx, sim in zip(new_wos_ids, best_idx, best_sim):
        cluster_name = centroid_names[int(idx)]
        feature_rows.append((wos_id, FEATURE_SET, "technology_cluster", cluster_name, True))
        if sim < _LOW_CONFIDENCE_SIMILARITY:
            n_low_confidence += 1

    # Insert only: existing labels are deliberately not retired.
    _insert_features(cur, feature_rows)
    conn.commit()

    elapsed = time.time() - t0
    print(f"\n  ✓ Assigned {len(feature_rows):,} paper(s) to nearest cluster in {elapsed:.1f}s")
    if n_low_confidence:
        print(f"  ⚠ {n_low_confidence:,} assignment(s) below similarity threshold "
              f"{_LOW_CONFIDENCE_SIMILARITY} — still assigned per the confirmed "
              f"no-human-step design, flagged here for visibility only.")

    cur.close()
    return {
        "assigned": len(feature_rows),
        "clusters": len(centroid_names),
        "low_confidence": n_low_confidence,
    }


# Funding organisations
def standardize_funding(conn) -> dict:
    """
    Match papers.funding_orgs against FUNDER_WHITELIST to write 'funding_top' rows.

    Text is cleaned (URLs, [...] and "(Grant ...)" removed) and split on ";". Each
    segment yields at most one funder (first case-insensitive substring match); each
    funder is recorded once per paper.
    """
    import re

    print("\n" + "═" * 60)
    print("T5c · Funding Organisation Standardization")
    print("═" * 60)
    t0 = time.time()
    cur = conn.cursor()

    # First entry matching a segment wins, so order matters.
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


    # (canonical_name, [lower-cased substrings])
    COMPILED = [
        (name, [s.lower() for s in aliases])
        for name, aliases in FUNDER_WHITELIST
    ]

    def extract_funders(raw: str) -> list:
        """Return the canonical funder names matched in a funding_orgs string."""
        cleaned = re.sub(r'https?://\S+', ' ', raw)
        cleaned = re.sub(r'\[.*?\]', ' ', cleaned)
        cleaned = re.sub(r'\(\s*[Gg]rant\s+\w+[\w\s,\.]*\)', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

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

    cur.execute("""
        SELECT wos_id, funding_orgs
        FROM   papers
        WHERE  funding_orgs IS NOT NULL
          AND  funding_orgs <> ''
    """)
    source_rows = cur.fetchall()
    print(f"  Papers with funding_orgs : {len(source_rows):,}")

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

    retired = _retire_features(cur, 'funding_top')
    if retired > 0:
        print(f"  Retired old rows         : {retired:,}")
    _insert_features(cur, feature_rows)
    conn.commit()

    elapsed = time.time() - t0
    print(f"\n  ✓ Done in {elapsed:.1f}s")

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


# Entry point
TASK_MAP = {
    "wos_categories":  parse_wos_categories,
    "countries":       extract_countries,
    "institutions":    standardize_institutions,
    "technologies":    cluster_technologies,
    "funding":         standardize_funding,
}

def run_all(conn):
    """Run every task in TASK_MAP, in order; return results keyed by task name."""
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
