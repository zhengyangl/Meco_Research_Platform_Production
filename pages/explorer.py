"""
Data Explorer
"""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from st_aggrid import (AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode,
                       JsCode, ColumnsAutoSizeMode)
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials

# ════════════════════════════════════════════════════════════════
# PAGE CONFIG 
# ════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Data Explorer · MEco",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded", 
)

# ════════════════════════════════════════════════════════════════
# GLOBAL CSS
# ════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap');

/* Base configuration */
.stApp { background: #F8FAFC; color: #0F172A; }
#MainMenu, footer { visibility: hidden; }
header { background: transparent !important; }
section.main > div { padding-top: 1rem; padding-bottom: 2rem; }
div.block-container { max-width: 1440px; padding-left: 2rem; padding-right: 2rem; }

/* Sidebar Polish */
[data-testid="stSidebar"] {
    background-color: #FFFFFF !important;
    border-right: 1px solid #E2E8F0;
}
[data-testid="stSidebar"] .block-container { padding-top: 2rem; }

/* Typography */
.exp-eyebrow {
    font: 600 0.7rem/1 'JetBrains Mono', monospace !important;
    letter-spacing: .05em !important; text-transform: uppercase !important;
    color: #2563EB !important; margin-bottom: .4rem !important;
}
.exp-title {
    font: 600 1.8rem/1.2 'Inter', sans-serif !important;
    letter-spacing: -0.02em !important;
    color: #0F172A !important; margin-bottom: .4rem !important;
}
.exp-sub {
    font: 400 0.9rem/1.5 'Inter', sans-serif !important;
    color: #64748B !important; max-width: 800px !important; margin-bottom: 1rem !important;
}

/* Navigation & Widgets */
.hero-nav { margin-bottom: 1rem; }
.hn-secondary {
    font: 500 .75rem/1 'Inter', sans-serif !important; 
    padding: 6px 12px !important; border-radius: 4px !important; 
    text-decoration: none !important; background: #FFFFFF !important; 
    color: #334155 !important; border: 1px solid #CBD5E1 !important;
    transition: all .15s; box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}
.hn-secondary:hover {
    border-color: #94A3B8 !important; color: #0F172A !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

/* Metric Pills */
.match-count {
    font: 500 .85rem/1 'Inter', sans-serif; color: #334155;
    padding: .5rem .8rem; background: #FFFFFF;
    border: 1px solid #E2E8F0; border-radius: 6px;
    display: inline-block; box-shadow: 0 1px 2px rgba(0,0,0,0.02);
    margin-right: 10px;
}
.match-count b { 
    font-family: 'JetBrains Mono', monospace; 
    color: #2563EB; font-weight: 700; font-size: 0.95rem;
}

/* Charts & Buttons */
.chart-label {
    font: 600 0.75rem/1 'Inter', sans-serif !important;
    color: #475569 !important; border-bottom: 1px solid #E2E8F0;
    padding-bottom: 0.4rem; margin-bottom: 0.8rem !important;
}
div[data-testid="stDownloadButton"] button {
    background: #FFFFFF !important; border: 1px solid #CBD5E1 !important;
    color: #0F172A !important; border-radius: 4px !important;
    font: 500 .8rem/1 'Inter', sans-serif !important;
}
div[data-testid="stDownloadButton"] button:hover {
    border-color: #2563EB !important; color: #2563EB !important;
}

/* Widget Text */
div[data-testid="stMultiSelect"] label,
div[data-testid="stSlider"] label,
div[data-testid="stSelectbox"] label,
div[data-testid="stTextInput"] label,
div[data-testid="stRadio"] label {
    font: 600 .7rem/1.2 'Inter', sans-serif !important;
    color: #475569 !important; text-transform: uppercase !important;
}

/* Sidebar "Clear all" button — subtle, ghost-style */
[data-testid="stSidebar"] div[data-testid="stButton"] > button {
    background: transparent !important;
    border: 1px solid #E2E8F0 !important;
    color: #64748B !important;
    font: 500 .68rem/1 'Inter', sans-serif !important;
    letter-spacing: .03em !important;
    padding: .35rem .6rem !important;
    border-radius: 4px !important;
    height: auto !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover {
    border-color: #DC2626 !important;
    color: #DC2626 !important;
    background: rgba(220, 38, 38, 0.04) !important;
}
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# DATA LOADING & PRE-CACHING
# ════════════════════════════════════════════════════════════════
# Confirmed design (Aug 2026): Explorer reads DIRECTLY from PostgreSQL —
# unlike the narrative page (app.py), which only ever reads pre-computed
# static files under dashboard_data/. Explorer must show ALL current data
# (legacy + everything ingest_incremental.py has added since), so its query
# is intentionally NOT filtered by dataset_id — see aggregate.py's
# LEGACY_DATASET_IDS design note for the narrative-side half of this split.
#
# Filtering logic itself (cascading multiselects, search, AgGrid, URL sync)
# is UNCHANGED — it still all runs in-memory over a single DataFrame. At the
# corpus's current scale (~30k rows, growing in small increments) querying
# the whole table once per cache period is simpler and safer than rewriting
# every filter as dynamic SQL.
import os
import psycopg2

_DATA_DIR = Path(__file__).parent.parent / "dashboard_data"
_CACHE_TTL_SECONDS = 900  # 15 minutes — new incremental data appears without an app restart

# The 22-service whitelist. Defined once here (not derived from the data)
# because two services — Spiritual and Cultural Identity — currently have
# zero papers and would silently disappear from any df.unique()-based list.
# Also used to filter the DB query below, same whitelist aggregate.py uses.
_ALL_SERVICES = [
    "Biochemicals", "Fibre/Hide/Wood", "Fuel", "Potable Water",
    "Food", "Biodiversity", "Disease Regulation", "Waste Treatment",
    "Climate Regulation", "Atmospheric Regulation", "Water Regulation",
    "Pollination", "Coastline Regulation", "Primary Production",
    "Soil Formation", "Nutrient Cycling", "Inspiration/Education",
    "Aesthetic", "Recreation", "Cultural Heritage", "Spiritual",
    "Cultural Identity",
]

_EXPLORER_PAPERS_SQL = """
SELECT
    p.wos_id, p.doi, p.title, p.pub_year, p.source_title, p.times_cited,
    p.open_access, p.authors, p.affiliations, p.wos_categories, p.keywords,
    p.addresses, p.funding_orgs,
    c.category, c.ecosystem_service, c.technology, c.model_version,
    COALESCE(
        (SELECT STRING_AGG(pf.feature_val, ' | ' ORDER BY pf.feature_val)
         FROM paper_features pf
         WHERE pf.wos_id = p.wos_id AND pf.feature_set = 'nlp_v1'
           AND pf.feature_key = 'wos_category' AND pf.is_current = TRUE),
        p.wos_categories
    ) AS wos_categories_parsed,
    (SELECT pf.feature_val FROM paper_features pf
     WHERE pf.wos_id = p.wos_id AND pf.feature_set = 'nlp_v1'
       AND pf.feature_key = 'country_first' AND pf.is_current = TRUE LIMIT 1) AS country_first,
    (SELECT STRING_AGG(pf.feature_val, ' | ' ORDER BY pf.feature_val) FROM paper_features pf
     WHERE pf.wos_id = p.wos_id AND pf.feature_set = 'nlp_v1'
       AND pf.feature_key = 'country' AND pf.is_current = TRUE) AS countries_all,
    (SELECT pf.feature_val FROM paper_features pf
     WHERE pf.wos_id = p.wos_id AND pf.feature_set = 'nlp_v1'
       AND pf.feature_key = 'institution_top' AND pf.is_current = TRUE LIMIT 1) AS institution_top,
    (SELECT STRING_AGG(pf.feature_val, ' | ' ORDER BY pf.feature_val) FROM paper_features pf
     WHERE pf.wos_id = p.wos_id AND pf.feature_set = 'nlp_v1'
       AND pf.feature_key = 'institution_all' AND pf.is_current = TRUE) AS institutions_all,
    (SELECT pf.feature_val FROM paper_features pf
     WHERE pf.wos_id = p.wos_id AND pf.feature_set = 'nlp_v1'
       AND pf.feature_key = 'technology_cluster' AND pf.is_current = TRUE LIMIT 1) AS technology_cluster,
    (SELECT STRING_AGG(pf.feature_val, ' | ' ORDER BY pf.feature_val) FROM paper_features pf
     WHERE pf.wos_id = p.wos_id AND pf.feature_set = 'nlp_v1'
       AND pf.feature_key = 'funding_top' AND pf.is_current = TRUE) AS funding_agencies
FROM papers p
JOIN classifications c ON p.wos_id = c.wos_id
WHERE p.is_review = FALSE
  AND c.is_current = TRUE
  AND c.decision = 'Y'
  AND c.ecosystem_service = ANY(%s)
"""


def _get_db_uri():
    return os.environ.get("DATABASE_URL")


def _query_papers_and_live_meta_from_db():
    """
    Single connection, two queries:
      1. The papers query (unchanged) — feeds df_all.
      2. A live meta-stats query, unfiltered by dataset_id — total_papers /
         non_review / reviews across ALL current data. decision_y is just
         len(df) since the papers query already applies exactly that filter
         (is_review=FALSE, decision='Y', whitelist), so no extra query needed.

    This intentionally does NOT touch corpus_meta.json's generation logic in
    aggregate.py — that file stays legacy-locked (LEGACY_DATASET_IDS) for the
    narrative page. Explorer needs different numbers (live, not locked), so
    it computes its own here rather than overloading one file for two
    incompatible purposes.
    """
    uri = _get_db_uri()
    if not uri:
        raise EnvironmentError("DATABASE_URL is not set")
    conn = psycopg2.connect(uri)
    try:
        df = pd.read_sql(_EXPLORER_PAPERS_SQL, conn, params=(_ALL_SERVICES,))
        _counts = pd.read_sql(
            "SELECT COUNT(*) AS total_papers, "
            "COUNT(*) FILTER (WHERE is_review = FALSE) AS non_review, "
            "COUNT(*) FILTER (WHERE is_review = TRUE) AS reviews "
            "FROM papers",
            conn,
        ).iloc[0]
        live_meta = {
            "total_papers": int(_counts["total_papers"]),
            "non_review":   int(_counts["non_review"]),
            "reviews":      int(_counts["reviews"]),
            "decision_y":   len(df),
        }
        return df, live_meta
    finally:
        conn.close()


def _query_abstracts_from_db() -> dict:
    uri = _get_db_uri()
    if not uri:
        raise EnvironmentError("DATABASE_URL is not set")
    conn = psycopg2.connect(uri)
    try:
        _abs_df = pd.read_sql(
            "SELECT wos_id, abstract FROM papers WHERE abstract IS NOT NULL", conn
        )
        return dict(zip(_abs_df["wos_id"], _abs_df["abstract"]))
    finally:
        conn.close()


@st.cache_data(ttl=_CACHE_TTL_SECONDS)
def load_data() -> tuple:
    # 1. Load DataFrame (+ live meta counts) — DB first, local parquet as
    # fallback if the DB is unreachable (network hiccup, credentials not yet
    # configured, etc). On fallback, live_meta is unavailable — the static
    # (legacy) meta numbers are used instead, which is fine since the
    # fallback banner already tells the user data may be stale.
    data_source = "db"
    live_meta = None
    try:
        df, live_meta = _query_papers_and_live_meta_from_db()
    except Exception as e:
        data_source = "fallback_parquet"
        try:
            df = pd.read_parquet(_DATA_DIR / "papers_classified.parquet")
        except FileNotFoundError:
            st.error(
                f"Could not reach the database ({e}) and no local fallback "
                f"file was found at {_DATA_DIR / 'papers_classified.parquet'}. "
                f"The Explorer has no data to show."
            )
            st.stop()

    df["pub_year"]    = pd.to_numeric(df["pub_year"], errors="coerce").astype("Int64")
    df["times_cited"] = pd.to_numeric(df["times_cited"], errors="coerce").fillna(0).astype(int)
    df["open_access"] = df["open_access"].fillna("Closed")
    

    journal_counts = df["source_title"].value_counts()
    major_journals = journal_counts[journal_counts >= 100].index.tolist()
    
    major_journals = sorted(major_journals) 
    
    df["journal_bucket"] = np.where(
        df["source_title"].isin(major_journals),
        df["source_title"],
        "Other Journals"
    )
    
    # 2. Pre-compute dropdown options to save CPU cycles on reruns
	# Pre-compute top 100 institutions by paper count
    _inst_counts = df["institution_top"].value_counts()
    _top_institutions = _inst_counts.head(100).index.tolist()

    # Explode pipe-separated funding_agencies into individual agency names
    _funding_flat = (
        df["funding_agencies"].dropna()
        .str.split(r" \| ", regex=True).explode().str.strip()
    )
    _funding_list = sorted(_funding_flat[_funding_flat != ""].unique().tolist())

    options = {
        "years":        sorted(df["pub_year"].dropna().unique().tolist()),
        "categories":   ["Replace", "Enhance", "Support"],
        "families":     sorted(df["service_category"].dropna().unique().tolist()) if "service_category" in df.columns else [],
        "services":     sorted(df["ecosystem_service"].dropna().unique().tolist()),
        "oa":           sorted(df["open_access"].dropna().unique().tolist()),
        "journals":     major_journals + ["Other Journals"],
        "countries":    sorted(df["country_first"].dropna().unique().tolist()),
        "tech_clusters": sorted(df["technology_cluster"].dropna().unique().tolist()),
        "top_institutions": _top_institutions,
        "funding_list": _funding_list,
    }
    # 3. Load Meta — starts from the static (legacy-locked) file for
    # provenance fields like dataset_version, then LIVE counts overwrite
    # total_papers/non_review/reviews/decision_y when the DB is reachable,
    # so the methodology panel reflects the current Explorer contents rather
    # than staying frozen at the original published numbers.
    try:
        with open(_DATA_DIR / "corpus_meta.json", encoding="utf-8") as f:
            meta = json.load(f)
    except FileNotFoundError:
        meta = {}
    if live_meta is not None:
        meta.update(live_meta)
    meta["_data_source"] = data_source
    meta["_loaded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    
    # 4. Pre-compute Impact Tier thresholds — relative to the FULL corpus.
    # These never change as the user filters, so "Top 1%" always means
    # "Top 1% of all 31,559 papers", which is an absolute impact signal.
    # The user can then see how many high-impact papers fall within their
    # current filter slice.
    _cits = df["times_cited"].values
    tiers = {
        "top_1_threshold":   int(pd.Series(_cits).quantile(0.99)),
        "top_10_threshold":  int(pd.Series(_cits).quantile(0.90)),
        "median_threshold":  int(pd.Series(_cits).quantile(0.50)),
        # Anything strictly below the median (i.e. bottom half) we treat as "tail".
        # The exact 0.50 quantile becomes the boundary between Median and Tail.
    }

    # service_category isn't returned by the DB query (it's derived, not
    # stored) — compute it the same way aggregate.py does, from the same
    # whitelist mapping, so filtering behaves identically either data source.
    if "service_category" not in df.columns:
        _SERVICE_TO_FAMILY = {
            "Biochemicals": "Provisioning", "Fibre/Hide/Wood": "Provisioning",
            "Fuel": "Provisioning", "Potable Water": "Provisioning",
            "Food": "Provisioning", "Biodiversity": "Provisioning",
            "Disease Regulation": "Regulating", "Waste Treatment": "Regulating",
            "Climate Regulation": "Regulating", "Atmospheric Regulation": "Regulating",
            "Water Regulation": "Regulating", "Pollination": "Regulating",
            "Coastline Regulation": "Regulating",
            "Primary Production": "Supporting", "Soil Formation": "Supporting",
            "Nutrient Cycling": "Supporting",
            "Inspiration/Education": "Cultural", "Aesthetic": "Cultural",
            "Recreation": "Cultural", "Cultural Heritage": "Cultural",
            "Spiritual": "Cultural", "Cultural Identity": "Cultural",
        }
        df["service_category"] = df["ecosystem_service"].map(_SERVICE_TO_FAMILY)
        options["families"] = sorted(df["service_category"].dropna().unique().tolist())

    return df, options, meta, tiers

df_all, OPTIONS, META, TIERS = load_data()

# Compute the OA percentage once — used in the header health bar.
_OA_PCT = round((df_all["open_access"] != "Closed").mean() * 100)
_MEDIAN_CITED = int(df_all["times_cited"].median())

@st.cache_data(ttl=_CACHE_TTL_SECONDS)
def load_abstracts():
    try:
        return _query_abstracts_from_db()
    except Exception:
        try:
            _abs_df = pd.read_parquet(_DATA_DIR / "abstracts.parquet")
            return dict(zip(_abs_df["wos_id"], _abs_df["abstract"]))
        except FileNotFoundError:
            return {}

ABSTRACTS = load_abstracts()

# ── Google Sheets connection for crowd-sourced feedback ─────────
# Kept as a resource cache (not data cache) since gspread client objects
# aren't picklable in the way st.cache_data expects. This connects once
# per session, not once per submission.
@st.cache_resource
def _get_feedback_sheet():
    """Returns the worksheet object, or None if secrets aren't configured
    (e.g. running locally without secrets.toml set up yet)."""
    try:
        _scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        _creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=_scopes
        )
        _client = gspread.authorize(_creds)
        _sheet = _client.open_by_key(st.secrets["feedback_sheet"]["spreadsheet_id"])
        return _sheet.sheet1
    except Exception:
        return None


def _submit_feedback(wos_id, doi, title, current_category, current_service,
                     suggested_category, suggested_service, reason, reporter_email):
    """Appends one row to the feedback sheet. Returns True on success."""
    _ws = _get_feedback_sheet()
    if _ws is None:
        return False
    try:
        # US Eastern time, with automatic EST/EDT handling via zoneinfo 
        _ts = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S %Z")
        _ws.append_row([
            _ts,
            wos_id, doi or "", title or "",
            current_category or "", current_service or "",
            suggested_category, suggested_service or "",
            reason, reporter_email or "",
        ])
        return True
    except Exception:
        return False


# (── _ALL_SERVICES moved up to before load_data(), see DATA LOADING section ──)

# ════════════════════════════════════════════════════════════════
# URL STATE SYNC 
# ════════════════════════════════════════════════════════════════
# Lets a researcher share a precise view by URL. 
_qp = st.query_params
def _read_qp_list(key, valid_set):
    """Read a comma-separated multiselect default from URL, keeping only
    values that exist in the current dataset (defends against stale URLs)."""
    raw = _qp.get(key, "")
    if not raw:
        return []
    return [v for v in raw.split(",") if v in valid_set]

# Defaults driven by URL (fall back to empty / full range when absent).
#
# Confirmed bug (Aug 2026): a single umbrella "state_initialized" flag meant
# that if Streamlit ever failed to re-render one of the filter widgets on a
# given rerun (observed specifically after clicking the manual refresh
# button, which triggers two reruns in quick succession — see
# handover.md), that widget's session_state key could be dropped, and
# because the umbrella flag was already True, it would never be restored —
# causing a hard AttributeError on the next read. Each key below is now
# checked and restored individually, every run. This costs nothing
# (a handful of dict lookups) and makes a dropped key self-heal on the very
# next rerun instead of crashing.
if "f_category" not in st.session_state:
    st.session_state.f_category = _read_qp_list("paradigm", set(OPTIONS["categories"]))
if "f_family" not in st.session_state:
    st.session_state.f_family = _read_qp_list("family", set(OPTIONS["families"]))
if "f_service" not in st.session_state:
    st.session_state.f_service = _read_qp_list("service", set(OPTIONS["services"]))
if "f_journal" not in st.session_state:
    st.session_state.f_journal = _read_qp_list("journal", set(OPTIONS["journals"]))

if "f_oa" not in st.session_state:
    st.session_state.f_oa = []
if "f_country" not in st.session_state:
    st.session_state.f_country = []
if "f_institution" not in st.session_state:
    st.session_state.f_institution = []
if "f_tech_cluster" not in st.session_state:
    st.session_state.f_tech_cluster = []
if "f_funding" not in st.session_state:
    st.session_state.f_funding = []

if "f_year" not in st.session_state:
    _dflt_year_min = int(_qp.get("year_min", OPTIONS["years"][0]))
    _dflt_year_max = int(_qp.get("year_max", OPTIONS["years"][-1]))
    st.session_state.f_year = (
        max(int(OPTIONS["years"][0]), min(int(OPTIONS["years"][-1]), _dflt_year_min)),
        max(int(OPTIONS["years"][0]), min(int(OPTIONS["years"][-1]), _dflt_year_max))
    )
if "f_min_cit" not in st.session_state:
    try:
        st.session_state.f_min_cit = max(0, int(_qp.get("min_cited", 0)))
    except (TypeError, ValueError):
        st.session_state.f_min_cit = 0

# ════════════════════════════════
# SIDEBAR: CASCADING FILTERS
# ════════════════════════════════
with st.sidebar:
    _eb, _refresh, _reset = st.columns([2, 1, 1])
    with _eb:
        st.markdown('<div class="exp-eyebrow">Data Controls</div>', unsafe_allow_html=True)
    with _refresh:
        if st.button("🔄", key="refresh_data_btn", use_container_width=True,
                      help="Force a fresh query — otherwise data auto-refreshes every 15 min"):
            load_data.clear()
            load_abstracts.clear()
            st.rerun()
    with _reset:
        if st.button("Clear all", key="clear_filters_btn", use_container_width=True):
            st.query_params.clear()
            for _k in list(st.session_state.keys()):
                if _k != "clear_filters_btn":
                    del st.session_state[_k]
            st.rerun()
    
    f_search = st.text_input("🔍 Quick Search", placeholder="Search title, authors, keywords, technology...",
                              help="Matches this exact phrase as a substring across title, "
                                   "authors, keywords, and technology. Not fuzzy — check your "
                                   "spelling. For country, institution, or journal, use the "
                                   "filters below instead.")

    # Show the match breakdown immediately under the search box
    if f_search:
        _q_preview = f_search.lower()
        _preview_fields = {"title": "Title", "authors": "Authors",
                            "keywords": "Keywords", "technology": "Technology"}
        _preview_counts = {}
        for _field, _label in _preview_fields.items():
            _n = int(df_all[_field].fillna("").str.lower()
                     .str.contains(_q_preview, na=False, regex=False).sum())
            if _n > 0:
                _preview_counts[_label] = _n
        if _preview_counts:
            _breakdown = " · ".join(f"{k} ({v})" for k, v in _preview_counts.items())
            st.caption(f"Matched in: {_breakdown}")
        else:
            st.caption(f"No matches for \"{f_search}\". Not fuzzy — check spelling.")

    st.markdown("<div style='margin-bottom: 1rem;'></div>", unsafe_allow_html=True)
    
    with st.expander("🌿 Ecological Focus", expanded=True):
        st.multiselect("Paradigm (R/E/S)", options=OPTIONS["categories"], key="f_category")
        st.multiselect("Service Family", options=OPTIONS["families"], key="f_family")
        
        if st.session_state.f_family:
            _valid_services = df_all[df_all["service_category"].isin(st.session_state.f_family)]["ecosystem_service"].unique().tolist()
            _valid_services = sorted(_valid_services)
        else:
            _valid_services = OPTIONS["services"]
            
        _current_f_service = st.session_state.f_service
        _filtered_service = [s for s in _current_f_service if s in _valid_services]
        
        if _filtered_service != _current_f_service:
            st.session_state.f_service = _filtered_service
            
        st.multiselect("Ecosystem Service", options=_valid_services, key="f_service")

    with st.expander("Time & Impact", expanded=True):
        _min_y, _max_y = int(OPTIONS["years"][0]), int(OPTIONS["years"][-1])
        st.slider("Publication Year", min_value=_min_y, max_value=_max_y, key="f_year")
        st.number_input("Minimum Citations", min_value=0, step=10, key="f_min_cit")

    with st.expander("Publication Details", expanded=False):
        st.multiselect("Source Journal", options=OPTIONS["journals"], key="f_journal")
        if "Other Journals" in st.session_state.f_journal:
            st.caption("'Other Journals' includes any journal with fewer than 100 papers in the corpus.")
        st.multiselect("Open Access Status", options=OPTIONS["oa"], key="f_oa")

    with st.expander("Geography & Institutions", expanded=False):
        st.multiselect("Country (first author)",
                       options=OPTIONS["countries"], key="f_country")
        st.multiselect(
            "Institution (first author)",
            options=OPTIONS["top_institutions"],
            key="f_institution",
            help="Top 100 institutions by paper count. Type to search.",
            placeholder="e.g. Harvard, MIT, Tsinghua..."
        )
        if not st.session_state.f_institution:
            st.caption(
                "Top 5: " + " · ".join(OPTIONS["top_institutions"][:5])
            )

    with st.expander("Technology & Funding", expanded=False):
        st.multiselect("Technology Cluster",
                       options=OPTIONS["tech_clusters"], key="f_tech_cluster",
                       help="25 semantic clusters derived from GPT-extracted technology labels.")
        st.multiselect("Funding Agency",
                       options=OPTIONS["funding_list"], key="f_funding",
                       help="Matched against a whitelist of ~60 global funders. "
                            "73.9% of funded papers are covered.")
        st.caption("Covers 60% of papers (73.9% of those with funding data). " 
        				"Papers with no funding info or niche local grants are not included.")


# ══════════════════════════
# APPLY FILTERS
# ══════════════════════════
df = df_all
df = df[(df["pub_year"] >= st.session_state.f_year[0]) & (df["pub_year"] <= st.session_state.f_year[1])]
if st.session_state.f_category: df = df[df["category"].isin(st.session_state.f_category)]
if st.session_state.f_family:   df = df[df["service_category"].isin(st.session_state.f_family)]
if st.session_state.f_service:  df = df[df["ecosystem_service"].isin(st.session_state.f_service)]
if st.session_state.f_journal:  df = df[df["journal_bucket"].isin(st.session_state.f_journal)]
if st.session_state.f_oa:       df = df[df["open_access"].isin(st.session_state.f_oa)]
if st.session_state.f_min_cit > 0: df = df[df["times_cited"] >= st.session_state.f_min_cit]

if f_search:
    q = f_search.lower()
    _search_fields = ["title", "authors", "keywords", "technology"]
    mask = pd.Series(False, index=df.index)
    for field in _search_fields:
        mask |= df[field].fillna("").str.lower().str.contains(q, na=False, regex=False)
    df = df[mask]

# New NLP-derived filters
if st.session_state.f_country:
    df = df[df["country_first"].isin(st.session_state.f_country)]

if st.session_state.f_institution:
    df = df[df["institution_top"].isin(st.session_state.f_institution)]

if st.session_state.f_tech_cluster:
    df = df[df["technology_cluster"].isin(st.session_state.f_tech_cluster)]

if st.session_state.f_funding:
    # funding_agencies is pipe-separated (e.g. "NSF | NIH").
    # Check if any selected agency appears as an exact element in the list.
    _selected = set(st.session_state.f_funding)
    _funding_mask = df["funding_agencies"].fillna("").apply(
        lambda x: bool(_selected.intersection(
            {s.strip() for s in x.split("|")}
        ))
    )
    df = df[_funding_mask]

# ═══════════════════════════════════════
# MAIN AREA: HEADER + HEALTH BAR
# ═══════════════════════════════════════
st.markdown("""
<div class="hero-nav">
  <a class="hn-secondary" href="/">← Back to the story</a>
</div>
""", unsafe_allow_html=True)

st.markdown(f'<h1 class="exp-title">{len(df_all):,} Bio-inspired Papers.</h1>',
            unsafe_allow_html=True)

# One-line corpus summary — dynamic, based on actual data
_n_countries_all = df_all["country_first"].dropna().nunique()
st.markdown(
    f'<p style="font:400 1.0rem/1.5 \'Inter\',sans-serif; color:#475569; '
    f'margin: 0.1rem 0 1.0rem; max-width:720px;">'
    f'A searchable corpus of bio-inspired innovation spanning '
    f'<b style="color:#0F172A;">{_n_countries_all}</b> countries, '
    f'<b style="color:#0F172A;">22</b> ecosystem services, and '
    f'<b style="color:#0F172A;">25</b> technology clusters — '
    f'derived from Jacobs et al. (2025).'
    f'</p>',
    unsafe_allow_html=True
)

# Fallback banner — only shows when the DB was unreachable and we're
# serving the last local parquet snapshot instead.
if META.get("_data_source") == "fallback_parquet":
    st.warning(
        "⚠ Could not reach the database — showing a locally cached snapshot "
        "instead of live data. New papers added since the last successful "
        "sync won't appear here. Try the 🔄 refresh button in the sidebar, "
        "or check the DATABASE_URL / network configuration.",
        icon="⚠️",
    )

# Health bar
_source_label = "database (live)" if META.get("_data_source") == "db" else "local snapshot (fallback)"
st.markdown(
    f"""<div style="
        font: 500 .72rem/1.4 'JetBrains Mono', monospace;
        color: #64748B; margin: 0.2rem 0 1.2rem;
        padding-bottom: 0.7rem; border-bottom: 1px solid #E2E8F0;
    ">
      corpus baseline: {META.get("dataset_version", "—")}
      &nbsp;·&nbsp; source: {_source_label}
      &nbsp;·&nbsp; loaded {META.get("_loaded_at", "—")}
      &nbsp;·&nbsp; open access: {_OA_PCT}%
      &nbsp;·&nbsp; corpus median citations: {_MEDIAN_CITED}
    </div>""",
    unsafe_allow_html=True
)

# Current-filter summary pill (kept from prior version but trimmed).
if len(df) > 0:
    st.markdown(
        f'<div class="match-count"><b>{len(df):,}</b> of {len(df_all):,} matched · '
        f'<b>{df["times_cited"].sum():,}</b> citations · '
        f'<b>{df["ecosystem_service"].nunique()}</b> services represented</div>',
        unsafe_allow_html=True
    )
else:
    st.markdown(
        '<div class="match-count" style="color:#94A3B8;"><b>0</b> matched · '
        'try widening your filters</div>',
        unsafe_allow_html=True
    )

# ════════════════════════════════════════════════════════════════
# IMPACT TIERS 
# ════════════════════════════════════════════════════════════════
# Thresholds are computed once against the FULL corpus, so "Top 1%" always
# means "Top 1% of all 31,559 papers" regardless of how the user filters.
# What changes under filtering is HOW MANY of the user's current selection
# fall into each tier — an absolute impact signal, not a relative one.
st.markdown('<div style="margin-top:1.0rem;"></div>', unsafe_allow_html=True)

_t1, _t2, _t3, _t4 = st.columns(4)
def _tier_card(col, label, count, description, threshold_text, accent):
    col.markdown(f"""
    <div style="
        background:#FFFFFF;
        border:1px solid #E2E8F0;
        border-left:3px solid {accent};
        border-radius:6px;
        padding:.9rem 1rem;
        box-shadow:0 1px 2px rgba(0,0,0,0.03);
    "
    title="Thresholds are fixed against the full {len(df_all):,}-paper corpus. This count shows how many papers in your CURRENT filter fall into that tier.">

      <div style="
          font:500 .65rem/1 'Inter',sans-serif;
          color:#64748B;
          text-transform:uppercase;
          letter-spacing:.08em;
          margin-bottom:.15rem;
      ">
        {label}
      </div>
      <div style="
          font:400 .60rem/1.3 'Inter',sans-serif;
          color:#B0B8C4;
          margin-bottom:.4rem;
      ">
        of full corpus
      </div>

      <div style="
          font:700 1.55rem/1 'JetBrains Mono',monospace;
          color:#0F172A;
          margin-bottom:.45rem;
      ">
        {count:,}
      </div>

      <div style="
          font:500 .73rem/1.3 'Inter',sans-serif;
          color:#334155;
          margin-bottom:.25rem;
      ">
        {description}
      </div>

      <div style="
          font:400 .68rem/1.3 'Inter',sans-serif;
          color:#94A3B8;
      ">
        {threshold_text}
      </div>

    </div>
    """, unsafe_allow_html=True)

if len(df) > 0:
    _n_top1   = int((df["times_cited"] >= TIERS["top_1_threshold"]).sum())
    _n_top10  = int((df["times_cited"] >= TIERS["top_10_threshold"]).sum())
    _n_median = int(((df["times_cited"] >= TIERS["median_threshold"]) &
                     (df["times_cited"] < TIERS["top_10_threshold"])).sum())
    _n_tail   = int((df["times_cited"] < TIERS["median_threshold"]).sum())
else:
    _n_top1 = _n_top10 = _n_median = _n_tail = 0

_tier_card(
    _t1,
    "Top 1%",
    _n_top1,
    "Exceptional impact",
    f"≥ {TIERS['top_1_threshold']:,} citations",
    "#DC2626",
)

_tier_card(
    _t2,
    "Top 10%",
    _n_top10,
    "Highly cited",
    f"≥ {TIERS['top_10_threshold']:,} citations",
    "#F59E0B",
)

_tier_card(
    _t3,
    "Core Literature",
    _n_median,
    "Main body of the field",
    f"{TIERS['median_threshold']:,}–{TIERS['top_10_threshold']-1:,} citations",
    "#2563EB",
)

_tier_card(
    _t4,
    "Long Tail",
    _n_tail,
    "Emerging / niche research",
    f"< {TIERS['median_threshold']:,} citations",
    "#94A3B8",
)

# ════════════════════════════════════════════════════════════════
# VISUALIZATIONS 
# ════════════════════════════════════════════════════════════════
st.markdown('<div style="margin-top:1.2rem;"></div>', unsafe_allow_html=True)

# Custom CSS for tabs and cards
st.markdown("""
<style>

/* ============================
   Tabs
   ============================ */

/* Tab container */
.stTabs [role="tablist"] {
    gap: 12px;
    border-bottom: none !important;
    padding-bottom: 0.5rem;
}

/* Hide default indicator (older Streamlit versions) */
.stTabs [data-baseweb="tab-highlight"] {
    display: none !important;
}

/* Hide selection indicator (newer Streamlit versions) */
.stTabs .react-aria-SelectionIndicator {
    display: none !important;
}

/* Base tab */
.stTabs [role="tab"] {
    background: #F8FAFC !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    padding: 8px 16px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02);
    transition: all 0.2s ease;
}

/* Tab text */
.stTabs [role="tab"] p {
    color: #64748B !important;
    font-weight: 500 !important;
    font-family: "Inter", sans-serif;
    margin: 0;
}

/* Hover */
.stTabs [role="tab"]:hover {
    background: #F1F5F9 !important;
    border-color: #CBD5E1 !important;
}

.stTabs [role="tab"]:hover p {
    color: #2563EB !important;
}

/* Active tab (support both old and new Streamlit) */
.stTabs [role="tab"][aria-selected="true"],
.stTabs [role="tab"][data-selected="true"] {
    background: #FFFFFF !important;
    border: 1px solid #2563EB !important;
    border-radius: 8px !important;
    box-shadow: 0 4px 8px rgba(37,99,235,0.12);
}

/* Active text */
.stTabs [role="tab"][aria-selected="true"] p,
.stTabs [role="tab"][data-selected="true"] p {
    color: #2563EB !important;
    font-weight: 600 !important;
}


/* ============================
   Chart cards
   ============================ */

.chart-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 1.2rem 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    margin-top: 0.8rem;
}

.chart-card-title {
    font: 600 0.82rem/1 "Inter", sans-serif;
    color: #0F172A;
    margin-bottom: 0.15rem;
}

.chart-card-sub {
    font: 400 0.7rem/1.4 "Inter", sans-serif;
    color: #94A3B8;
    margin-bottom: 0.8rem;
}

</style>
""", unsafe_allow_html=True)

_PLOTLY_COUNTRY_MAP = {
    "South Korea":             "South Korea",
    "Czechia":                 "Czech Republic",
    "Palestine, State of":     "Palestine",
    "Brunei Darussalam":       "Brunei",
    "Côte d'Ivoire":           "Ivory Coast",
    "North Macedonia":         "Macedonia",
    "Russia":                  "Russia",
    "Taiwan":                  "Taiwan",
    "Curaçao":                 "Curacao",
}

if len(df) > 0:
    with st.expander("📊 3 Visualizations — Map · Gap Analysis · Tech Treemap", expanded=False):
        tab_map, tab_trend, tab_tech = st.tabs([
            "Global Landscape",
            "Gap Analysis",
            "Tech Ecosystem"
        ])

        # ── Choropleth ────────────────────────────────────────
        with tab_map:
            st.markdown("""
            <div class="chart-card" style="margin-bottom: 0.5rem; padding-bottom: 0.8rem;">
                <div class="chart-card-title">Global Innovation Landscape</div>
                <div class="chart-card-sub" style="margin-bottom: 0;">
                    Where is bio-inspired research happening? Color intensity shows
                    first-author paper count by country.
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            _country_counts = df["country_first"].dropna().value_counts()
            
            if len(_country_counts) > 0:
                _country_df = pd.DataFrame({
                    "country": [_PLOTLY_COUNTRY_MAP.get(c, c) for c in _country_counts.index],
                    "n": _country_counts.values,
                    "label": _country_counts.index,
                })
                _country_df["log_n"] = np.log1p(_country_df["n"])
                
                col_map, col_stats = st.columns([7.5, 2.5], gap="large")
                
                with col_map:
                    fig_map = go.Figure(go.Choropleth(
                        locations = _country_df["country"],
                        locationmode = "country names",
                        z = _country_df["log_n"],
                        customdata = _country_df["n"],
                        text = _country_df["label"],
                        colorscale = [
    						[0.00, "#F1F5F9"], 
    						[0.25, "#C8D9C3"],
    						[0.55, "#7A9E6F"],
    						[0.85, "#4F7942"],
    						[1.00, "#2D4A24"], 
						],
                        autocolorscale = False,
                        showscale = False,
                        hovertemplate = "<b>%{text}</b><br>%{customdata:,} papers<extra></extra>",
                        marker_line_color = "#E2E8F0",
                        marker_line_width = 0.4,
                    ))
                    
                    fig_map.update_layout(
                        paper_bgcolor = "rgba(0,0,0,0)",
                        plot_bgcolor = "rgba(0,0,0,0)",
                        height = 360,  
                        margin = dict(l=0, r=0, t=10, b=0),
                        geo = dict(
                            showframe = False,
                            showcoastlines = True,
                            coastlinecolor = "#CBD5E1",
                            showland = True,
                            landcolor = "#FAFAF7",
                            showocean = True,
                            oceancolor = "#FAFCFA",
                            showlakes = False,
                            showcountries = True,
                            countrycolor = "#E2E8F0",
                            bgcolor = "rgba(0,0,0,0)",
                            projection_type = "natural earth",
                        ),
                        hoverlabel = dict(
                            bgcolor = "#FFFFFF",
                            bordercolor = "#E2E8F0",
                            font = dict(size=11, color="#0F172A", family="Inter, sans-serif"),
                        ),
                    )
                    st.plotly_chart(fig_map, use_container_width=True, config={"displayModeBar": False})
                    
                with col_stats:
                    _top5 = _country_counts.head(5)
                    _n_countries = _country_counts.shape[0]
                    _total_counts = _country_counts.sum()
                    _top5_pct = round(_top5.sum() / _total_counts * 100) if _total_counts > 0 else 0
                    
                    _rank_items = []
                    for i, (c, n) in enumerate(zip(_top5.index, _top5.values)):
                        display_name = c
                        if display_name == "United States":
                            display_name = "USA"
                        elif display_name == "United Kingdom":
                            display_name = "UK"

                        _rank_items.append(
                            f'<div style="display:flex; justify-content:space-between; align-items:center; '
                            f'padding:.35rem 0; border-bottom:1px solid #E2E8F0;">'
                            f'<div style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding-right:0.8rem;">'
                            f'<span style="color:#94A3B8; margin-right:4px;">{i+1}.</span>'
                            f'<span style="color:#334155;">{display_name}</span>'
                            f'</div>'
                            f'<div style="color:#0F172A; font-weight:600; flex-shrink:0;">{n:,}</div>'
                            f'</div>'
                        )
                    _rank_html = "".join(_rank_items)
                    
                    st.markdown(
                        f'<div style="background:#FFFFFF; border-radius:8px; padding:1.2rem; margin-top:0rem; border:1px solid #E2E8F0; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">'
                        f'<div style="font:600 .68rem/1.4 Inter,sans-serif; letter-spacing:.05em; color:#475569; text-transform:uppercase; margin-bottom:.1rem;">'
                        f'Top 5 Countries</div>'
                        f'<div style="font:400 .65rem/1.4 Inter,sans-serif; color:#94A3B8; margin-bottom:1rem;">'
                        f'Contribute {_top5_pct}% of total papers</div>'
                        f'<div style="font:400 .8rem/1.8 \'JetBrains Mono\',monospace;">'
                        f'{_rank_html}'
                        f'</div>'
                        f'<div style="font:400 .65rem/1.5 Inter,sans-serif; color:#94A3B8; margin-top:.8rem; text-align:center;">'
                        f'{_n_countries} countries in total'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
            else:
                st.info("No geographic data available for the selected filters.")

        # ── Ecosystem Service Gap Analysis ────────────────────
        with tab_trend:
            st.markdown("""
            <div class="chart-card">
                <div class="chart-card-title">Where Are the Gaps?</div>
                <div class="chart-card-sub">
                    All 22 ecosystem services ranked by research volume in your
                    current selection. The red line marks 500 papers (~5% of the
                    top service) — the threshold used in the narrative page to
                    flag under-researched services.
                </div>
            """, unsafe_allow_html=True)
            
            # Count papers per ecosystem service in the filtered data.
            _svc_counts = df["ecosystem_service"].value_counts()
            _gap_df = pd.DataFrame({
                "service": _ALL_SERVICES,
                "n": [int(_svc_counts.get(s, 0)) for s in _ALL_SERVICES],
            }).sort_values("n", ascending=True)
            
            # Color: green if >= 500, muted amber if < 500 (research gap)
            _gap_df["color"] = _gap_df["n"].apply(
                lambda x: "#4F7942" if x >= 500 else "#B7791F"
            )
            
            fig_gap = go.Figure()
            
            # Bars
            fig_gap.add_trace(go.Bar(
                y = _gap_df["service"],
                x = _gap_df["n"],
                orientation = "h",
                marker_color = _gap_df["color"],
                hovertemplate= "<b>%{y}</b><br>%{x:,} papers<extra></extra>",
            ))
            
            # Threshold line at 500
            fig_gap.add_vline(
                x=500, line_dash="dot", line_color="#2563EB", line_width=2,
            )
            
            fig_gap.add_annotation(
                x=500, 
                y=0.1, 
                xref="x", 
                yref="paper", 
                text="Gap threshold: 500", 
                showarrow=False,
                xanchor="left",
                xshift=8,
    			font=dict(size=12, color="rgba(37,99,235,0.8)"),
			)
            
            
            fig_gap.update_layout(
                paper_bgcolor = "rgba(0,0,0,0)",
                plot_bgcolor = "#FFFFFF",
                height = 520,
                margin = dict(l=10, r=20, t=10, b=10),
                xaxis = dict(
                    tickfont = dict(size=10, color="#94A3B8", family="Inter, sans-serif"),
                    gridcolor = "#F1F5F9",
                    linecolor = "#E2E8F0",
                    tickformat = ",",
                ),
                yaxis = dict(
                    tickfont = dict(size=11, color="#334155", family="Inter, sans-serif"),
                    linecolor = "#E2E8F0",
                ),
                hoverlabel = dict(
                    bgcolor = "#FFFFFF",
                    bordercolor = "#E2E8F0",
                    font = dict(size=11, color="#0F172A", family="Inter, sans-serif"),
                ),
                showlegend = False,
                bargap = 0.25,
            )
            st.plotly_chart(fig_gap, use_container_width=True, config={"displayModeBar": False})
            
            # Quick stats
            _n_above = (_gap_df["n"] >= 500).sum()
            _n_zero = (_gap_df["n"] == 0).sum()
            _lowest = _gap_df.iloc[0]
            
            st.markdown(
                f'<div style="border-top:1px solid #F1F5F9;margin-top:0.8rem;'
                f'padding-top:0.8rem;font:400 .72rem/1.5 Inter,sans-serif;color:#64748B;">'
                f'<b style="color:#0F172A;">{_n_above}</b> of 22 services above the '
                f'500-paper threshold · '
                f'<b style="color:#0F172A;">{_n_zero}</b> with zero papers · '
                f'Smallest: <b style="color:#0F172A;">{_lowest["service"]}</b> '
                f'({int(_lowest["n"]):,})'
                f'</div>',
                unsafe_allow_html=True
            )
            
            if _gap_df["n"].max() < 500 and len(df) < len(df_all):
                st.markdown(
                    '<div style="font:400 .68rem/1.4 Inter,sans-serif;color:#D97706;'
                    'padding:0.3rem 0 0;">'
                    '⚠ Your current filter returns fewer than 500 papers per service. '
                    'The threshold is based on the full corpus for cross-filter comparison.'
                    '</div>',
                    unsafe_allow_html=True
                )
            st.markdown('</div>', unsafe_allow_html=True)

        # ── Technology Treemap ────────────────────────────────
        with tab_tech:
            st.markdown("""
            <div class="chart-card">
                <div class="chart-card-title">Technology Ecosystem</div>
                <div class="chart-card-sub">
                    What are researchers building? Size = publication volume,
                    color = citation impact (darker = more influential).
                </div>
            """, unsafe_allow_html=True)
            
            _cluster_counts = (
                df.groupby("technology_cluster")
                  .agg(n=("wos_id", "size"),
                       median_cited=("times_cited", "median"))
                  .reset_index()
                  .rename(columns={"technology_cluster": "cluster"})
            )
            _cluster_counts["median_cited"] = (
                _cluster_counts["median_cited"].fillna(0).astype(int)
            )
            
            if len(_cluster_counts) > 0:
                _cluster_counts["short"] = _cluster_counts["cluster"].apply(
                    lambda x: x if len(x) <= 30 else x[:28] + "…"
                )
                
                fig_tree = go.Figure(go.Treemap(
                    labels = _cluster_counts["short"],
                    values = _cluster_counts["n"],
                    parents = [""] * len(_cluster_counts),
                    customdata = _cluster_counts[["cluster", "median_cited"]].values,
                    textinfo = "label+value",
                    textfont = dict(
                        size = 12,
                        family = "Inter, sans-serif",
                    ),
                    texttemplate = "<b>%{label}</b><br>%{value:,}",
                    hovertemplate = (
                        "<b>%{customdata[0]}</b><br>"
                        "%{value:,} papers · median citations: %{customdata[1]}"
                        "<extra></extra>"
                    ),
                    marker = dict(
                        colors = _cluster_counts["median_cited"],
                        colorscale = [
                            [0.00, "#F8FAFC"],
                            [0.30, "#E8DDD2"],
                            [0.60, "#D6A77A"],
                            [1.00, "#A85D16"],
                        ],
                        line = dict(width=2, color="#F0FAF0"),
                        colorbar = dict(
                            title = dict(
                                text = "Median<br>Citation",
                                font = dict(size=10, color="#64748B", family="Inter, sans-serif"),
                            ),
                            thickness = 10,
                            len = 0.55,
                            tickfont = dict(size=9, color="#64748B", family="JetBrains Mono, monospace"),
                            bgcolor = "rgba(0,0,0,0)",
                            borderwidth= 0,
                        ),
                    ),
                    tiling = dict(packing="squarify"),
                ))
                
                fig_tree.update_layout(
                    paper_bgcolor = "rgba(0,0,0,0)",
                    height = 420,
                    margin = dict(l=0, r=0, t=0, b=0),
                    hoverlabel = dict(
                        bgcolor = "#FFFFFF",
                        bordercolor= "#E2E8F0",
                        font = dict(size=11, color="#0F172A", family="Inter, sans-serif"),
                    ),
                )
                st.plotly_chart(fig_tree, use_container_width=True, config={"displayModeBar": False})
                
                _top_impact = _cluster_counts.nlargest(3, "median_cited")
            
                _impact_items = []
                for _, r in _top_impact.iterrows():
                    item = (
                        f'<div style="display:flex; justify-content:space-between; align-items:center; '
                        f'padding:.22rem 0; border-bottom:1px solid #F8FAFC;">'
                        f'<span style="color:#334155; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding-right:1rem;">'
                        f'{r["cluster"]}</span>'
                        f'<span style="color:#0F172A; font-weight:600; white-space:nowrap;">'
                        f'med.&nbsp;{int(r["median_cited"])}</span></div>'
                    )
                    _impact_items.append(item)
                _impact_html = "".join(_impact_items)
                
                st.markdown(
                    f'<div style="border-top:1px solid #F1F5F9; margin-top:.85rem; padding-top:.85rem;">'
                    f'<div style="font:600 .68rem/1.4 Inter,sans-serif; letter-spacing:.05em; color:#94A3B8; text-transform:uppercase; margin-bottom:.55rem;">'
                    f'Highest Citation Impact</div>'
                    f'<div style="font:400 .8rem/1.8 \'JetBrains Mono\',monospace; max-width:420px;">'
                    f'{_impact_html}</div>'
                    f'<div style="font:400 .68rem/1.5 Inter,sans-serif; color:#94A3B8; margin-top:.75rem;">'
                    f'Treemap color encodes the median citation count within each technology cluster.</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    '<div style="color:#94A3B8; font:300 .82rem/1.6 Inter,sans-serif; padding-top:1rem;">'
                    'No technology cluster data.</div>',
                    unsafe_allow_html=True
                )
            st.markdown('</div>', unsafe_allow_html=True)

else:
    st.info("No data matches the selected filters.")


# ══════════════════════
# MAIN TABLE 
# ══════════════════════
st.markdown('<div style="margin-top:1.4rem;"></div>', unsafe_allow_html=True)
st.markdown('<div class="chart-label">Detailed Records</div>', unsafe_allow_html=True)

# AgGrid Community edition has no built-in column-visibility panel (that's
# an Enterprise feature in recent ag-Grid versions), so we expose it here
# in Streamlit instead and pass the resulting hide/show state into
# configure_column() below.
_HIDEABLE_COLS = {
    "keywords":              "Keywords",
    "open_access":           "Access",
    "service_category":      "Family",
    "affiliations":          "All Affiliations",
    "wos_categories_parsed": "WoS Subject Categories",
    "addresses":             "Raw Addresses",
    "funding_orgs":          "Funding (raw text)",
    "countries_all":         "All Countries",
    "institutions_all":      "All Institutions",
    "funding_agencies":      "Funding Agencies (matched)",
    "model_version":         "Classification Model",
}
_visible_extra = st.multiselect(
    "Show additional columns",
    options=list(_HIDEABLE_COLS.keys()),
    default=[],
    format_func=lambda x: _HIDEABLE_COLS[x],
)

_doi_renderer = JsCode("""
class CustomDoiRenderer {
    init(params) {
        this.eGui = document.createElement('a');
        if (params.value) {
            const doi = params.value.replace(/^https?:\\/\\/(dx\\.)?doi\\.org\\//, '');
            this.eGui.innerText = doi;
            this.eGui.href = 'https://doi.org/' + doi;
            this.eGui.target = '_blank';
            this.eGui.style.color = '#2563EB';
            this.eGui.style.textDecoration = 'none';
            this.eGui.style.fontWeight = '400';
        }
    }
    getGui() { return this.eGui; }
}
""")

_category_style = JsCode("""
function(params) {
    if (params.value === 'Replace') {
        return { 'color': '#92400E', 'backgroundColor': 'rgba(245, 158, 11, 0.12)', 'fontWeight': '500' };
    } else if (params.value === 'Enhance') {
        return { 'color': '#065F46', 'backgroundColor': 'rgba(16, 185, 129, 0.12)', 'fontWeight': '500' };
    } else if (params.value === 'Support') {
        return { 'color': '#1E40AF', 'backgroundColor': 'rgba(59, 130, 246, 0.12)', 'fontWeight': '500' };
    }
    return null;
}
""")

_grid_cols = [
    "title", "authors", "pub_year", "source_title", "times_cited",
    "open_access", "ecosystem_service", "service_category", "category",
    "technology", "keywords", "doi",
    # NLP-derived columns
    "country_first", "institution_top", "technology_cluster",
    # available via "Show additional columns" below.
    "affiliations", "wos_categories_parsed", "addresses",
    "funding_orgs", "countries_all", "institutions_all", "funding_agencies", 
    "model_version",
    # always visible, pinned last
    "wos_id",
]

if len(df) == 0:
    st.info("No papers match the current filters. Try clearing some constraints in the sidebar.")
    st.stop()

df_grid = df[_grid_cols].copy()

gb = GridOptionsBuilder.from_dataframe(df_grid)

gb.configure_default_column(
    filter=True, sortable=True, resizable=True, 
    wrapText=False, autoHeight=False, 
    tooltipValueGetter=JsCode("function(params) { return params.value; }") 
)

gb.configure_column("title", header_name="Title", width=340, minWidth=340, pinned="left", tooltipField="title")
gb.configure_column("authors", header_name="Authors", width=180, minWidth=180, tooltipField="authors")

gb.configure_column("pub_year", header_name="Year", width=80, minWidth=80, type=["numericColumn"])
gb.configure_column("source_title", header_name="Journal", width=180, minWidth=180, tooltipField="source_title")
gb.configure_column("times_cited", header_name="Citations", width=150, minWidth=150, type=["numericColumn"], sort="desc")
gb.configure_column("open_access", header_name="Access", width=110, minWidth=110,
                    hide="open_access" not in _visible_extra)

gb.configure_column("ecosystem_service", header_name="Ecosystem Service", width=200, minWidth=200, tooltipField="ecosystem_service")
gb.configure_column("service_category", header_name="Family", width=120, minWidth=120,
                    hide="service_category" not in _visible_extra)
gb.configure_column("category", header_name="Paradigm", width=110, minWidth=110, cellStyle=_category_style)
gb.configure_column("technology", header_name="Technology", width=160, minWidth=160, tooltipField="technology")
gb.configure_column("keywords", header_name="Keywords", width=260, minWidth=260,
                    tooltipField="keywords", hide="keywords" not in _visible_extra)

gb.configure_column("doi", header_name="DOI", width=220, minWidth=220, cellRenderer=_doi_renderer)

gb.configure_column("country_first", header_name="Country", width=120, minWidth=120, maxWidth=150)
gb.configure_column("institution_top", header_name="Institution", width=220, minWidth=220, tooltipField="institution_top")
gb.configure_column("technology_cluster", header_name="Tech Cluster", width=200, minWidth=200, tooltipField="technology_cluster")

gb.configure_column("wos_id", header_name="WoS ID", width=200, minWidth=200)
gb.configure_column("affiliations", header_name="All Affiliations", width=280, minWidth=280,
                    tooltipField="affiliations", hide="affiliations" not in _visible_extra)
gb.configure_column("wos_categories_parsed", header_name="WoS Subject Categories", width=260, minWidth=260,
                    tooltipField="wos_categories_parsed", hide="wos_categories_parsed" not in _visible_extra)
gb.configure_column("addresses", header_name="Raw Addresses", width=280, minWidth=280,
                    tooltipField="addresses", hide="addresses" not in _visible_extra)
gb.configure_column("funding_orgs", header_name="Funding (raw text)", width=240, minWidth=240,
                    tooltipField="funding_orgs", hide="funding_orgs" not in _visible_extra)
gb.configure_column("countries_all", header_name="All Countries", width=180, minWidth=180,
                    tooltipField="countries_all", hide="countries_all" not in _visible_extra)
gb.configure_column("institutions_all", header_name="All Institutions", width=260, minWidth=260,
                    tooltipField="institutions_all", hide="institutions_all" not in _visible_extra)
gb.configure_column("funding_agencies", header_name="Funding Agencies (matched)", width=240, minWidth=240,
                    tooltipField="funding_agencies", hide="funding_agencies" not in _visible_extra)
gb.configure_column("model_version", header_name="Model", width=140, minWidth=140,
                    hide="model_version" not in _visible_extra)

gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=30)
gb.configure_grid_options(
    domLayout="normal", 
    suppressMenuHide=True, 
    rowHeight=38,          
    enableBrowserTooltips=True,
    enableCellTextSelection=True,
    suppressSizeToFit=True  
)

_custom_css = {
    ".ag-header-cell-text": {
        "font-family": "'Inter', sans-serif !important",
        "font-size": "12px !important",
        "font-weight": "600 !important",
        "color": "#64748B !important", 
        "letter-spacing": "0.02em !important"
    },
    ".ag-cell": {
        "font-family": "'Inter', sans-serif !important",
        "font-size": "13px !important",
        "color": "#334155 !important",
    },
    ".ag-row-hover": {
        "background-color": "#F8FAFC !important"
    }
}

AgGrid(
    df_grid,
    gridOptions=gb.build(),
    height=600,
    theme="balham",
    allow_unsafe_jscode=True,
    update_mode=GridUpdateMode.NO_UPDATE,
    columns_auto_size_mode=ColumnsAutoSizeMode.NO_AUTOSIZE,
    enable_enterprise_modules=False,
    custom_css=_custom_css,
)
     
# ════════════════════════════════════════════════════════════════
# REPORT A MISCLASSIFICATION
# ════════════════════════════════════════════════════════════════
# The user pastes a WoS ID
# or DOI, we look it up with a fast dict/index lookup, and the report
# form only appears once a match is confirmed. Submissions go to a
# Google Sheet for manual review — nothing here writes to the production
# database directly.
st.markdown('<div style="margin-top:1.4rem;"></div>', unsafe_allow_html=True)
with st.expander("🚩 Report a Misclassification"):
    st.caption(
        "See a paper that's misclassified? Paste its WoS ID or DOI below "
        "to flag it for review. Reports go to the research team — nothing "
        "is changed automatically."
    )

    _lookup_col, _btn_col = st.columns([4, 1])
    with _lookup_col:
        _lookup_input = st.text_input(
            "WoS ID or DOI", placeholder="e.g. WOS:000123456789 or 10.1038/s41586-...",
            label_visibility="collapsed", key="feedback_lookup_input",
        )
    with _btn_col:
        _lookup_clicked = st.button("Look up", use_container_width=True)

    if _lookup_clicked and _lookup_input.strip():
        _q = _lookup_input.strip()
        _match = df_all[(df_all["wos_id"] == _q) | (df_all["doi"] == _q)]
        if len(_match) == 0:
            st.warning("No paper found with that WoS ID or DOI. Double-check and try again.")
            st.session_state.pop("feedback_match", None)
        else:
            st.session_state.feedback_match = _match.iloc[0].to_dict()

    if "feedback_match" in st.session_state:
        _m = st.session_state.feedback_match
        st.markdown(
            f'<div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:6px; '
            f'padding:.8rem 1rem; margin:.6rem 0;">'
            f'<div style="font:600 .82rem/1.4 Inter,sans-serif; color:#0F172A;">{_m["title"]}</div>'
            f'<div style="font:400 .75rem/1.6 Inter,sans-serif; color:#64748B; margin-top:.3rem;">'
            f'Currently classified as <b>{_m["category"]}</b> · <b>{_m["ecosystem_service"]}</b>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        with st.form("feedback_form", clear_on_submit=True):
            _sug_category = st.selectbox(
                "Suggested paradigm",
                options=["Replace", "Enhance", "Support", "Not sure — just flagging"],
            )
            _sug_service = st.selectbox(
                "Suggested ecosystem service (optional)",
                options=["(no change / not sure)"] + _ALL_SERVICES,
            )
            _reason = st.text_area("Why do you think this is misclassified?", height=100)
            _email = st.text_input(
                "Your email (optional)",
                placeholder="you@institution.edu",
            )
            _submitted = st.form_submit_button("Submit report")

            if _submitted:
                if not _reason.strip():
                    st.error("Please explain why you think this is misclassified.")
                else:
                    _ok = _submit_feedback(
                        wos_id=_m["wos_id"], doi=_m.get("doi"), title=_m["title"],
                        current_category=_m["category"], current_service=_m["ecosystem_service"],
                        suggested_category=_sug_category,
                        suggested_service=None if _sug_service == "(no change / not sure)" else _sug_service,
                        reason=_reason.strip(), reporter_email=_email.strip(),
                    )
                    if _ok:
                        st.success("Thank you — your report has been submitted for review.")
                        del st.session_state["feedback_match"]
                    else:
                        st.error(
                            "Something went wrong submitting your report. "
                            "Please try again later, or contact the research team directly."
                        )
                                    
# ════════════════════════════════════════════════════════════════
# METHODOLOGY PANEL 
# ════════════════════════════════════════════════════════════════
st.markdown('<div style="margin-top:1.4rem;"></div>', unsafe_allow_html=True)
with st.expander("📊 How were these papers classified? (Methodology & data lineage)"):
	st.markdown(f"""
**Source corpus.** Papers are retrieved from Web of Science using
`biomim*` / `bioinspir*` queries, 2004–present. Review and survey
articles are excluded from classification. The current corpus size is
shown above — this panel explains *how* papers are classified, not a
snapshot of *how many*.

**Classification.** The original corpus was classified with **GPT-4.1**,
using a structured prompt developed for Jacobs et al. (2025). Papers added
since then are classified with **Qwen-2.5-72B-instruct**, selected after
benchmarking against GPT-4.1 and DeepSeek on a human-labeled validation
set. For each paper, the model decides:

- **Decision (Y/N):** Does this paper describe a technology contributing
  to at least one ecosystem service?
- **Category (R/E/S):** Does the technology *Replace*, *Enhance*, or *Support*
  the natural process? Boundaries defined in the published prompt.
- **Ecosystem service:** Which of the 22 services does it target?
- **Technology:** Free-text label for the bio-inspired technology described.

**Confidence and human review.** The model also reports its own confidence
(high / medium / low) in each classification. High-confidence results are
written to the database automatically; medium- and low-confidence results
are instead sent to a review queue for a person to check before they enter
the database — so not every row in this dataset is a raw, unverified model
output.

**Defensive filtering.** Two LLM hallucination values (`"Cultural"`,
`"Ecosystem monitoring"`) appeared in initial outputs and were filtered
out by a 22-service whitelist in `aggregate.py`. Neither is a valid
ecosystem service under this framework.

**Versioning.** Every classification result is stored in PostgreSQL with
its `model_version`, `prompt_version`, and `run_id`. When a paper is
reclassified, historical results are preserved — the dashboard always
reads `is_current = TRUE` rows. Raw LLM JSON responses are kept in the
`classification_audit` table for replication.

**Reproduce these numbers.** The full pipeline (ingestion → LLM classify
→ aggregate → static JSON/Parquet) is fully open-source. See the 
[**GitHub Repository ↗**](https://github.com/zhengyangl/Meco_Research_Platform_Production) 
for the codebase and `docs/handover.md` for how the pipeline is operated
day to day.
    """)
# ════════════════════════════════════════════════════════════════
# EXPORT
# ════════════════════════════════════════════════════════════════
st.markdown('<div style="margin-top:1.0rem;"></div>', unsafe_allow_html=True)
st.markdown(
    '<div style="font: 600 .65rem/1.2 Inter, sans-serif; '
    'letter-spacing: .05em; color: #8A847B; margin-bottom: 0.4rem; '
    'text-transform: uppercase;">Export Data</div>',
    unsafe_allow_html=True
)
_ALL_EXPORT_COLS = {
    "wos_id":               "WoS ID",
    "doi":                  "DOI",
    "title":                "Title",
    "authors":              "Authors",
    "pub_year":             "Year",
    "source_title":         "Journal",
    "times_cited":          "Citations",
    "open_access":          "Open Access",
    "ecosystem_service":    "Ecosystem Service",
    "service_category":     "Service Family",
    "category":             "Paradigm (R/E/S)",
    "technology":           "Technology",
    "technology_cluster":   "Tech Cluster",
    "country_first":        "Country",
    "institution_top":      "Institution",
    "countries_all":        "All Countries",
    "institutions_all":     "All Institutions",
    "funding_agencies":     "Funding Agencies",
    "wos_categories_parsed":"WoS Categories",
    "keywords":             "Keywords",
    "addresses":            "Addresses",
    "funding_orgs":         "Funding Orgs (raw)",
    "abstract":             "Abstract (full text)",
}
_DEFAULT_EXPORT = [
    "wos_id", "doi", "title", "authors", "pub_year", "source_title",
    "times_cited", "ecosystem_service", "category", "technology",
    "technology_cluster", "country_first", "institution_top",
]
_selected_cols = st.multiselect(
    "Columns to export",
    options=list(_ALL_EXPORT_COLS.keys()),
    default=_DEFAULT_EXPORT,
    format_func=lambda x: _ALL_EXPORT_COLS[x],
    label_visibility="collapsed",
)
if not _selected_cols:
    _selected_cols = _DEFAULT_EXPORT.copy()

# "abstract" is intentionally NOT a column on `df` — it lives in the
# separate ABSTRACTS dict and is joined in only at export time below.
_valid_cols = [c for c in _selected_cols if c in df.columns or c == "abstract"]

if _valid_cols:
    selected_text = ", ".join(_ALL_EXPORT_COLS[c] for c in _valid_cols[:8])
    if len(_valid_cols) > 8:
        selected_text += " ..."
    st.caption(f"Selected: {selected_text}")

    _export_df = df[[c for c in _valid_cols if c != "abstract"]].copy()
    if "abstract" in _valid_cols:
        _export_df["abstract"] = df["wos_id"].map(ABSTRACTS)
        _export_df = _export_df[_valid_cols]  # restore user's column order

    _csv = _export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=f"⬇ Download {len(df):,} records · {len(_valid_cols)} fields",
        data=_csv,
        file_name=f"meco_export_{len(df)}rows.csv",
        mime="text/csv",
    )
else:
    st.warning("No valid columns available for export.")
