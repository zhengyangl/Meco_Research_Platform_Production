"""
MEco Research Dashboard — Complete Single-Page Application (LIGHT THEME · v3)
"Nature Is Not Optional."
Based on Jacobs et al. (2025), Biomimetics 2025, 10, 784

Run with:
    streamlit run app.py
"""

# ════════════════════════════════════════════════════════════════
# IMPORTS
# ════════════════════════════════════════════════════════════════
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import pandas as pd
import json

# ════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Nature Is Not Optional · MEco",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ════════════════════════════════════════════════════════════════
# GLOBAL CSS 
# ════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Inter:wght@300;400;500;600&display=swap');
 
/* ── Base ─────────────────────────────────────────────────── */
.stApp { background: #F7F5F1; color: #2A2722; }
#MainMenu, footer, header { visibility: hidden; }
section[data-testid="stSidebar"] { display: none; }
section.main > div { padding-top: 2.5rem; padding-bottom: 6rem; }
div.block-container { max-width: 1080px; padding-left: 2rem; padding-right: 2rem; }
 
/* ── Shared utilities ─────────────────────────────────────── */
.hr     { border: none; border-top: 1px solid #E5E1DA; margin: 1.5rem 0; }
.hr-sm  { border: none; border-top: 1px solid #E5E1DA; margin: 1.2rem 0; }
.section-sep { border: none; border-top: 1px solid #DAD5CC; margin: 5rem 0 4rem; }
.chart-label {
    font: 500 0.68rem/1 'Inter', sans-serif;
    letter-spacing: .18em; text-transform: uppercase;
    color: #8A847B; margin-bottom: .6rem;
}
.chart-sub-label {
    font: 300 .82rem/1.6 'Inter', sans-serif;
    color: #6B665E; max-width: 600px; margin-bottom: .9rem;
}
 
/* ── Section eyebrows ─────────────────────────────────────── */
.hero-eyebrow, .s1-eyebrow, .s2-eyebrow,
.s3-eyebrow, .s4-eyebrow, .s6-eyebrow, .eyebrow {
    font: 500 0.68rem/1 'Inter', sans-serif;
    letter-spacing: .22em; text-transform: uppercase;
    color: #3D7A52; margin-bottom: .85rem;
}
 
/* ── Section 0: Hero ──────────────────────────────────────── */
.hero-eyebrow { font-size: 0.7rem; margin-bottom: .9rem; }
h1.hero-title {
    font: 700 3.8rem/1.05 'Playfair Display', serif !important;
    color: #2A2722 !important;
    margin-bottom: .9rem !important;
}
.hero-sub {
    font: 300 1.08rem/1.8 'Inter', sans-serif;
    color: #6B665E; max-width: 540px; margin-bottom: 1.8rem;
}
.hero-prompt {
    font: 400 1rem/1.7 'Inter', sans-serif;
    color: #4A453E; padding: 1.1rem 1.5rem;
    border-left: 3px solid #3D7A52;
    border-radius: 0 8px 8px 0;
    background: rgba(61,122,82,.07);
}
.hero-prompt strong { color: #2A2722; font-weight: 500; }
 
/* ── Section 0: Category pills ───────────────────────────── */
.cat-pill {
    display: inline-block;
    font: 500 0.67rem/1 'Inter', sans-serif;
    letter-spacing: .16em; text-transform: uppercase;
    padding: 4px 12px; border-radius: 20px;
    margin: 1.4rem 0 .7rem;
}
.cp-provisioning { background: rgba(168,116,14,.12); color: #8A5E0B; }
.cp-cultural      { background: rgba(95,87,189,.12);  color: #5048A8; }
.cp-regulating    { background: rgba(29,140,105,.12); color: #1A7A5C; }
.cp-supporting    { background: rgba(61,122,82,.12);  color: #356B49; }
 
/* ── Section 0: Counter ──────────────────────────────────── */
.ctr {
    text-align: center; background: #FBF9F5;
    border: 1px solid #E5E1DA; border-radius: 10px;
    padding: 1.6rem 2rem; margin: 1.2rem 0 1rem;
}
.ctr-n   { font: 700 3.2rem/1 'Playfair Display', serif; color: #3D7A52; }
.ctr-sub { font: 300 .82rem/1 'Inter', sans-serif; color: #8A847B; margin-top: 6px; }
 
/* ── Section 0: Insight panel ────────────────────────────── */
.insight {
    background: linear-gradient(145deg, #EEF4EE 0%, #F7F5F1 70%);
    border: 1px solid #C5DBCB; border-radius: 12px;
    padding: 2rem 2.4rem; margin-top: 1rem;
}
.insight-title { font: 700 1.55rem/1.25 'Playfair Display', serif; color: #2A2722; margin-bottom: .9rem; }
.insight-body  { font: 400 .96rem/1.85 'Inter', sans-serif; color: #4A453E; margin-bottom: 1.3rem; }
.hl-red   { font: 700 1.7rem/1 'Playfair Display', serif; color: #B05A2E; }
.hl-green { font: 700 1.7rem/1 'Playfair Display', serif; color: #3D7A52; }
.tag-sec-lbl { font: 500 .64rem/1 'Inter', sans-serif; letter-spacing: .14em; text-transform: uppercase; margin-bottom: 5px; }
.lbl-gap { color: #B05A2E; }
.lbl-ok  { color: #3D7A52; }
.tag { display: inline-block; margin: 3px 3px; padding: 3px 9px; border-radius: 20px; font: 400 .7rem/1 'Inter', sans-serif; }
.tag-gap { background: rgba(176,90,46,.10); color: #97491F; border: 1px solid rgba(176,90,46,.25); }
.tag-ok  { background: rgba(61,122,82,.10); color: #356B49; border: 1px solid rgba(61,122,82,.25); }
.insight-cta   { font: 500 .75rem/1 'Inter', sans-serif; letter-spacing: .14em; text-transform: uppercase; color: #3D7A52; }
.insight-empty { text-align: center; padding: 2rem; color: #B8B0A4; font: 300 .88rem/1.6 'Inter', sans-serif; }
 
div:has(> button[data-testid*="stBaseButton-pill"]) {
    justify-content: center !important;
    gap: 14px 12px !important;
    padding: 10px 0 20px 0;
}
 
button[data-testid="stBaseButton-pills"],
button[data-testid="stBaseButton-pillsActive"] {
    background-color: #FDFCFA !important;
    border: 1px solid #D6D2CC !important;
    border-radius: 30px !important;
    padding: 10px 28px !important; 
    font-family: 'Inter', sans-serif !important;
    font-size: 0.95rem !important; 
    font-weight: 500 !important;
    letter-spacing: 0.02em !important; 
    color: #4A453E !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1) !important;
    height: auto !important; 
    min-height: 62px !important; 
}
 
button[data-testid="stBaseButton-pills"]:hover,
button[data-testid="stBaseButton-pillsActive"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 3px 8px rgba(61,122,82,0.08) !important;
    border-color: #3D7A52 !important;
    background-color: rgba(61,122,82,0.04) !important;
    color: #2E5C3E !important;
}
 
button[data-testid="stBaseButton-pills"]:active,
button[data-testid="stBaseButton-pillsActive"]:active {
    transform: translateY(0) !important;
    box-shadow: 0 1px 2px rgba(61,122,82,0.08) !important;
}
 
button[data-testid="stBaseButton-pillsActive"] {
    background-color: rgba(61, 122, 82, 0.08) !important;
    border: 1.5px solid #3D7A52 !important;
    color: #356B49 !important;
    font-weight: 500 !important;
    box-shadow: 0 4px 10px rgba(61, 122, 82, 0.1) !important;
    transform: translateY(0) !important; 
}
 
button[data-testid*="stBaseButton-pill"]:focus-visible {
    box-shadow: none !important;
    outline: none !important;
}

/* ── Section 1: Narrative ────────────────────────────────── */
.s1-title { 
    font: 700 3.6rem/1.15 'Playfair Display', serif !important; 
    color: #2A2722 !important; 
    margin-bottom: 1rem !important; 
    letter-spacing: -0.01em !important; 
}
.s1-sub { 
    font: 300 1.05rem/1.85 'Inter', sans-serif !important; 
    color: #6B665E !important; 
    max-width: 580px !important; 
    margin-bottom: .5rem !important; 
}
.s1-bridge {
    font: 400 1.0rem/1.7 'Inter', sans-serif; color: #4A453E;
    padding: 1rem 1.5rem; border-left: 3px solid #3D7A52;
    border-radius: 0 8px 8px 0; background: rgba(61,122,82,.07);
    margin-bottom: 1.6rem;
}
.s1-bridge em { color: #2A2722; font-style: normal; font-weight: 500; }
 
/* ── Section 1: KPI cards ────────────────────────────────── */
.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 1.4rem; }
.kpi-card { background: #FFFFFF; border: 1px solid #E5E1DA; border-radius: 10px; padding: 1.2rem 1.1rem 1rem; text-align: center; box-shadow: 0 1px 2px rgba(42,39,34,.03); }
.kpi-card.accent-amber { border-color: #E0C589; }
.kpi-card.accent-green { border-color: #B6D2BD; }
.kpi-val       { font: 700 2.1rem/1 'Playfair Display', serif; color: #2A2722; display: block; margin-bottom: .45rem; }
.kpi-val-amber { color: #A8740E !important; }
.kpi-val-green { color: #3D7A52 !important; }
.kpi-label     { font: 500 .75rem/1.3 'Inter', sans-serif; color: #6B665E; display: block; margin-bottom: .3rem; }
.kpi-note      { font: 300 .67rem/1.45 'Inter', sans-serif; color: #9A938A; display: block; }
 
/* ── Section 2 / 3 / 4 / 6 narrative ─────────────────────── */
.s2-title, .s3-title, .s4-title, .s6-title { 
    font: 700 3.4rem/1.15 'Playfair Display', serif !important; 
    color: #2A2722 !important; 
    margin-bottom: .85rem !important; 
    letter-spacing: -0.01em !important; 
}
.s2-sub, .s3-sub, .s4-sub, .s6-sub { 
    font: 300 1.02rem/1.85 'Inter', sans-serif !important; 
    color: #6B665E !important; 
    max-width: 620px !important; 
    margin-bottom: .5rem !important; 
}
div[data-testid="stRadio"] label { font: 400 .82rem/1 'Inter', sans-serif !important; color: #4A453E !important; }
div[data-testid="stRadio"] > div { gap: 1rem; }
.scenario-callout {
    background: rgba(61,122,82,0.07); border: 1px solid rgba(61,122,82,0.22);
    border-left: 3px solid #3D7A52; border-radius: 0 8px 8px 0;
    padding: .85rem 1.2rem; font: 300 .82rem/1.65 'Inter', sans-serif;
    color: #4A453E; margin-bottom: 1rem;
}
/* ── Section 2: Radial chart side panel ──────────────────── */
.radial-info-card {
    background: #FBF9F5; border: 1px solid #E5E1DA; border-radius: 10px;
    padding: 1.1rem 1.3rem; margin-bottom: 1rem;
}
.radial-info-card.insight {
    background: linear-gradient(145deg, #EEF4EE 0%, #FBF9F5 75%);
    border-color: #C5DBCB;
}
.radial-info-title {
    font: 600 .66rem/1 'Inter', sans-serif; letter-spacing: .16em; text-transform: uppercase;
    color: #9A938A; margin-bottom: .7rem;
}
.radial-info-card.insight .radial-info-title { color: #3D7A52; }
.radial-info-body { font: 300 .82rem/1.7 'Inter', sans-serif; color: #6B665E; }
.radial-info-body b { color: #2A2722; font-weight: 500; }
.radial-info-body .ib-su { color: #2E7CB8; font-weight: 500; }
.radial-info-body .ib-en { color: #1D8C69; font-weight: 500; }
.radial-info-body .ib-re { color: #A8740E; font-weight: 500; }
 
.scenario-callout b { color: #356B49; font-weight: 500; }
 
 
 
/* ── Section 2: Gap cards ────────────────────────────────── */
.gap-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 1.4rem 0; }
.gap-card { background: #FFFFFF; border: 1px solid #E5E1DA; border-radius: 10px; padding: 1.3rem 1.2rem 1.1rem; box-shadow: 0 1px 2px rgba(42,39,34,.03); }
.gap-card.critical { border-color: #E0B79E; }
.gap-icon  { font-size: 1.5rem; display: block; margin-bottom: .55rem; }
.gap-svc   { font: 500 .82rem/1.2 'Inter', sans-serif; color: #4A453E; letter-spacing: .06em; margin-bottom: .55rem; }
.gap-n     { font: 700 2.3rem/1 'Playfair Display', serif; color: #B05A2E; display: block; margin-bottom: .4rem; }
.gap-n-ok  { color: #3D7A52 !important; }
.gap-sub   { font: 300 .72rem/1.5 'Inter', sans-serif; color: #8A847B; }
.gap-ratio { font: 300 .68rem/1 'Inter', sans-serif; color: #6B665E; margin-top: .7rem; padding-top: .7rem; border-top: 1px solid #E5E1DA; }
.gap-ratio b { color: #B05A2E; }
 
/* ── Section 5: Quote ────────────────────────────────────── */
.quote-wrap { text-align: center !important; padding: 3.5rem 2rem 2rem !important; max-width: 720px !important; margin: 0 auto !important; }
.quote-mark { font: 400 4rem/1 'Playfair Display', serif !important; color: rgba(61,122,82,0.30) !important; display: block !important; margin-bottom: -.5rem !important; }
.quote-text { font: 400 italic 1.8rem/1.55 'Playfair Display', serif !important; color: #2A2722 !important; margin-bottom: 1.2rem !important; }
.quote-source { font: 300 .75rem/1 'Inter', sans-serif !important; color: #8A847B !important; letter-spacing: .10em !important; text-transform: uppercase !important; }
.turn-text { font: 300 1.05rem/1.85 'Inter', sans-serif !important; color: #4A453E !important; text-align: center !important; max-width: 520px !important; margin: 2rem auto 0 !important; }
.turn-text em { color: #3D7A52 !important; font-style: normal !important; }
 
/* ── Section 5: Echo ─────────────────────────────────────── */
.echo-wrap {
    background: rgba(61,122,82,0.05) !important; border: 1px solid rgba(61,122,82,0.20) !important;
    border-radius: 14px !important; padding: 2.2rem 2.8rem !important;
    text-align: center !important; margin: 0 auto !important; max-width: 680px !important;
}
.echo-n     { font: 700 5rem/1 'Playfair Display', serif !important; color: #3D7A52 !important; display: block !important; margin-bottom: .6rem !important; }
.echo-label { font: 300 1.0rem/1.7 'Inter', sans-serif !important; color: #4A453E !important; max-width: 440px !important; margin: 0 auto .8rem !important; }
.echo-sub   { font: 300 .75rem/1.6 'Inter', sans-serif !important; color: #8A847B !important; max-width: 400px !important; margin: 0 auto !important; }
 
/* ── Section 5: Identity buttons ─────────────────────────── */
div[data-testid="stButton"] button {
    background: #FFFFFF !important; border: 1px solid #E5E1DA !important;
    border-radius: 10px !important; color: #4A453E !important;
    font: 400 .78rem/1.3 'Inter', sans-serif !important;
    height: 72px !important;
    box-shadow: 0 1px 2px rgba(42,39,34,.03) !important;
    transition: border-color .2s, background .2s !important;
}
div[data-testid="stButton"] button:hover {
    border-color: rgba(61,122,82,0.50) !important;
    background: rgba(61,122,82,0.05) !important; color: #2A2722 !important;
}
div[data-testid="stButton"] button:focus,
div[data-testid="stButton"] button:active {
    border-color: rgba(61,122,82,0.80) !important;
    background: rgba(61,122,82,0.09) !important; color: #2A2722 !important;
}
 
/* ── Section 5: Response card ────────────────────────────── */
.response-card {
    background: #FFFFFF !important; border: 1px solid #E5E1DA !important;
    border-left: 3px solid #3D7A52 !important; border-radius: 0 12px 12px 0 !important;
    padding: 2rem 2.4rem !important; margin-top: 1.4rem !important; max-width: 780px !important;
    box-shadow: 0 2px 6px rgba(42,39,34,.05) !important;
}
.response-title { font: 700 1.55rem/1.2 'Playfair Display', serif !important; color: #2A2722 !important; margin-bottom: .7rem !important; }
.response-body  { font: 300 .92rem/1.85 'Inter', sans-serif !important; color: #4A453E !important; margin-bottom: 0 !important; }

/* option 1 */
.response-body em { 
    color: #356B49 !important; 
    font-style: normal !important; 
    font-weight: 500 !important; 
}
.response-body b  { 
    color: #2A2722 !important; 
    font-weight: 500 !important; 
}
/*.response-body em { color: #2A2722 !important; font-style: italic !important;font-weight: 500 !important; }*/
/*.response-body b  { color: #2A2722 !important; font-weight: 500 !important; }*/

/* option 2 green color */
/*.response-body em { color: #3D7A52 !important; font-style: italic !important; font-weight: 500 !important; }
/*.response-body b  { color: #2A2722 !important; font-weight: 500 !important; }

 
/* ── Section 5: Final statement ──────────────────────────── */
.final-wrap { text-align: center !important; padding: 4rem 2rem 2rem !important; }
.final-you     { font: 300 1.1rem/1 'Inter', sans-serif !important; letter-spacing: .28em !important; text-transform: uppercase !important; color: #8A847B !important; margin-bottom: .6rem !important; display: block !important; }
.final-belong  { font: 700 4.2rem/1.1 'Playfair Display', serif !important; color: #3D7A52 !important; display: block !important; margin-bottom: 1.6rem !important; }
.final-link    { font: 400 .72rem/1 'Inter', sans-serif !important; letter-spacing: .18em !important; text-transform: uppercase !important; color: #356B49 !important; text-decoration: none !important; border-bottom: 1px solid rgba(61,122,82,0.35) !important; padding-bottom: 2px !important; display: inline-block !important; }
.land-ack      { font: 300 italic .75rem/1.8 'Inter', sans-serif !important; color: #B8B0A4 !important; max-width: 560px !important; display: block !important; margin: 3rem auto 0 !important; text-align: center !important; line-height: 1.85 !important; }
 
/* ── Credibility badges ───────────────────────────────────── */
.badge-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: .65rem; align-items: center; }
.badge {
    display: inline-flex; align-items: center; gap: 5px;
    font: 400 .62rem/1 'Inter', sans-serif;
    letter-spacing: .10em; text-transform: uppercase;
    padding: 4px 10px; border-radius: 20px;
}
.badge-real { background: rgba(61,122,82,0.10); border: 1px solid rgba(61,122,82,0.30); color: #356B49; }
.badge-sim  { background: rgba(168,116,14,0.10); border: 1px solid rgba(168,116,14,0.28); color: #8A5E0B; }
.badge-dot  { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.badge-real .badge-dot { background: #3D7A52; }
.badge-sim  .badge-dot { background: #A8740E; }
 

div[data-testid="stMultiSelect"] label,
div[data-testid="stSlider"] label,
div[data-testid="stSelectbox"] label {
    font: 500 .72rem/1.3 'Inter', sans-serif !important;
    color: #4A453E !important;
}
div[data-testid="stDownloadButton"] button {
    background: rgba(61,122,82,0.08) !important;
    border: 1px solid rgba(61,122,82,0.40) !important;
    color: #356B49 !important;
    font: 500 .76rem/1 'Inter', sans-serif !important;
    letter-spacing: .04em !important;
    height: auto !important; padding: .6rem 1.4rem !important;
    box-shadow: none !important;
}
div[data-testid="stDownloadButton"] button:hover {
    background: rgba(61,122,82,0.14) !important;
    border-color: rgba(61,122,82,0.65) !important;
    color: #2A2722 !important;
}
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# DATA LOADING — read pre-computed JSON/Parquet from dashboard_data/
# ════════════════════════════════════════════════════════════════
# These files are produced by pipeline/aggregate.py on every pipeline run.
# The narrative page never queries the database directly — it reads only
# these static artifacts. This is what keeps the page loading instantly
# and what lets it survive even if the database is offline.
import json as _json
from pathlib import Path as _Path
_DATA_DIR = _Path(__file__).parent / "dashboard_data"

@st.cache_data
def _load_corpus_meta():
    with open(_DATA_DIR / "corpus_meta.json", encoding="utf-8") as f:
        return _json.load(f)

@st.cache_data
def _load_services_summary():
    with open(_DATA_DIR / "services_summary.json", encoding="utf-8") as f:
        return _json.load(f)

@st.cache_data
def _load_annual_by_category():
    with open(_DATA_DIR / "annual_by_category.json", encoding="utf-8") as f:
        return _json.load(f)

@st.cache_data
def _load_country_oa():
    with open(_DATA_DIR / "country_oa.json", encoding="utf-8") as f:
        return _json.load(f)

@st.cache_data
def _load_wos_cooccurrence():
    with open(_DATA_DIR / "wos_cooccurrence.json", encoding="utf-8") as f:
        return _json.load(f)
        

@st.cache_data
def _load_framing():
    with open(_DATA_DIR / "framing.json", encoding="utf-8") as f:
        return _json.load(f)
        
        
CORPUS = _load_corpus_meta()       # corpus_meta.json contents
SVC_SUMMARY = _load_services_summary()  # services_summary.json contents
ANNUAL = _load_annual_by_category()     # annual_by_category.json contents
COUNTRY_OA = _load_country_oa()         # country_oa.json contents
WOS_NET = _load_wos_cooccurrence()      # wos_cooccurrence.json contents
FRAMING = _load_framing()               # framing.json contents

# ── Service display-name mapping ────────────────────────────────────
# Database / aggregate.py stores the raw GPT classification values
# (e.g. 'Fibre/Hide/Wood', 'Atmospheric Regulation') as the source of truth.
# This dict turns those into the prettier display labels used throughout
# the narrative page. Anything not in this dict falls through to the raw
# value, so it's safe to leave the lookup unconditional.
SERVICE_DISPLAY_NAMES = {
    "Fibre/Hide/Wood":         "Fibre · Hide · Wood",
    "Atmospheric Regulation":  "Atmospheric Reg.",
    "Inspiration/Education":   "Inspiration · Education",
}
def display_name(raw: str) -> str:
    return SERVICE_DISPLAY_NAMES.get(raw, raw)

# Reverse mapping: pretty label → raw DB name (for deep-link URLs).
SERVICE_RAW_NAMES = {v: k for k, v in SERVICE_DISPLAY_NAMES.items()}
def raw_name(pretty: str) -> str:
    return SERVICE_RAW_NAMES.get(pretty, pretty)


# ════════════════════════════════════════════════════════════════
# SHARED CONSTANTS
# ════════════════════════════════════════════════════════════════
RESEARCH_GAP_THRESHOLD = 500  # papers; services below this are flagged

_SERVICE_META = {
    "Biochemicals":            {"icon": "", "desc": "Molecules used in medicine"},
    "Fibre/Hide/Wood":         {"icon": "", "desc": "Materials used for clothing or construction"},
    "Fuel":                    {"icon": "", "desc": "Materials used to generate energy"},
    "Potable Water":           {"icon": "", "desc": "Fresh water that is safe to consume"},
    "Food":                    {"icon": "", "desc": "Nutritious ingredients from wild & domesticated habitats"},
    "Biodiversity":            {"icon": "", "desc": "The variety of living species on Earth"},
    "Disease Regulation":      {"icon": "", "desc": "Natural systems reducing disease and disease vectors"},
    "Waste Treatment":         {"icon": "️", "desc": "Filtering and treating organic and chemical waste"},
    "Climate Regulation":      {"icon": "️", "desc": "Stabilization of climatic conditions"},
    "Atmospheric Regulation":  {"icon": "", "desc": "Production and consumption of essential molecules (O₂)"},
    "Water Regulation":        {"icon": "", "desc": "Timing and volume of water distribution across land"},
    "Pollination":             {"icon": "", "desc": "Distribution of pollen seeds for plant reproduction"},
    "Coastline Regulation":    {"icon": "️", "desc": "Stabilization of coastal lands via mangroves and reefs"},
    "Primary Production":      {"icon": "️", "desc": "Creation of sugars from sunlight — base of all food chains"},
    "Soil Formation":          {"icon": "", "desc": "The ongoing creation of new fertile soil"},
    "Nutrient Cycling":        {"icon": "", "desc": "The movement of nutrients through ecosystems"},
    "Inspiration/Education":   {"icon": "", "desc": "Art, science, music, literature, and design"},
    "Aesthetic":               {"icon": "", "desc": "Mental and physical benefits of natural beauty"},
    "Recreation":              {"icon": "️", "desc": "Physical and mental health from nature experiences"},
    "Cultural Heritage":       {"icon": "️", "desc": "Societal value placed upon landscapes"},
    "Spiritual":               {"icon": "️", "desc": "Support for the spiritual lives of people"},
    "Cultural Identity":       {"icon": "", "desc": "Individual and societal identity from human-nature bonds"},
}

# Build the same nested-dict structure the rest of the code expects, but now
# every paper count comes from services_summary.json — no hardcoded values.
_CAT_CSS_MAP = {"Provisioning": "provisioning", "Cultural": "cultural",
                "Regulating": "regulating", "Supporting": "supporting"}
SERVICES = {cat: {"css": _CAT_CSS_MAP[cat], "items": []} for cat in _CAT_CSS_MAP}
for _s in SVC_SUMMARY["services"]:
    _raw = _s["service"]
    _meta = _SERVICE_META.get(_raw, {"icon": "•", "desc": ""})
    SERVICES[_s["category"]]["items"].append({
        "name":   display_name(_raw),   # pretty label used everywhere downstream
        "icon":   _meta["icon"],
        "desc":   _meta["desc"],
        "papers": _s["total"],
    })

# Build _df2 directly from services_summary.json — single source of truth.
# The display_name() pass keeps the pretty service labels everywhere in the
# narrative; raw GPT names stay in the database and the data files.
_df2 = pd.DataFrame([
    {"service":  display_name(s["service"]),
     "category": s["category"],
     "total":    s["total"],
     "replace":  s["replace"],
     "enhance":  s["enhance"],
     "support":  s["support"]}
    for s in SVC_SUMMARY["services"]
])
_df2["adj"] = _df2["total"].clip(lower=1)

# ════════════════════════════════════════════════════════════════
# SESSION STATE
# ════════════════════════════════════════════════════════════════
_svc_names = [s["name"] for cat in SERVICES.values() for s in cat["items"]]
for _name in _svc_names:
    if _name not in st.session_state:
        st.session_state[_name] = False

if "identity" not in st.session_state:
    st.session_state.identity = None

if "spotlight_idx" not in st.session_state:  
    st.session_state.spotlight_idx = 0


# ════════════════════════════════════════════════════════════════
# ONE-TIME OPENING ANIMATION 
# ════════════════════════════════════════════════════════════════
if not st.session_state.get("intro_played", False):
    st.session_state.intro_played = True
    
    components.html("""
    <script>
    (function() {
      try {
        var doc = window.parent.document;
        if (!doc.getElementById('meco-intro-style')) {
            var style = doc.createElement('style');
            style.id = 'meco-intro-style';
            style.innerHTML = `
              @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Inter:wght@300;400&display=swap');
              
              .meco-intro { position: fixed; inset: 0; z-index: 999999; background: #F7F5F1; overflow: hidden; cursor: pointer; display: flex; align-items: center; justify-content: center; opacity: 1; transition: opacity .85s ease; }
              .meco-intro.fade { opacity: 0; pointer-events: none; }
              .meco-intro canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
              
              .meco-intro .intro-center { position: relative; z-index: 2; text-align: center; padding: 0 1.5rem; opacity: 0; transform: translateY(10px); transition: opacity 1s ease .25s, transform 1s ease .25s; }
              .meco-intro.in .intro-center { opacity: 1; transform: translateY(0); }
              
              .meco-intro .intro-n { 
                  font: 700 4.2rem/1.05 'Playfair Display', serif; color: #2A2722; 
                  animation: meco-pulse-slow 6s infinite ease-in-out;
              }
              .meco-intro .intro-cap { font: 300 1.15rem/1.6 'Inter', sans-serif; color: #6B665E; margin-top: .7rem; }
              
              .meco-intro .intro-legend { margin-top: 1.8rem; display: flex; justify-content: center; gap: 24px; font: 400 .85rem/1 'Inter', sans-serif; color: #6B665E; }
              .meco-intro .leg-item { display: flex; align-items: center; gap: 8px; }
              .meco-intro .leg-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
              
              .meco-intro .intro-skip {
                  position: absolute; bottom: 40px; left: 50%; transform: translateX(-50%); z-index: 2;
                  font: 400 .75rem/1 'Inter', sans-serif; letter-spacing: .2em; text-transform: uppercase; color: #6B665E;
                  animation: meco-pulse 4.5s infinite ease-in-out;
              }
              
              @keyframes meco-pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
              @keyframes meco-pulse-slow { 0%, 100% { opacity: 0.7; } 50% { opacity: 1; } }
              
              @media (max-width: 640px) { .meco-intro .intro-n { font-size: 2.6rem; } .meco-intro .intro-legend { flex-direction: column; gap: 12px; align-items: center; } }
            `;
            doc.head.appendChild(style);
        }

        if (doc.getElementById('meco-intro-singleton')) return;
        var ov = doc.createElement('div');
        ov.id = 'meco-intro-singleton';
        ov.className = 'meco-intro';
        
        ov.innerHTML =
          '<canvas></canvas>' +
          '<div class="intro-center">' +
            '<div class="intro-n">Nature Is Not Optional.</div>' +
            '<div class="intro-cap">Twenty years of bio-inspired research.<br>Each one a choice about nature.</div>' +
            '<div class="intro-legend">' +
              '<span class="leg-item"><span class="leg-dot" style="background:#A8740E;"></span> 58% Replace</span>' +
              '<span class="leg-item"><span class="leg-dot" style="background:#1D8C69;"></span> 39% Enhance</span>' +
              '<span class="leg-item"><span class="leg-dot" style="background:#2E7CB8;"></span> 3% Support</span>' +
            '</div>' +
          '</div>' +
          '<div class="intro-skip">Click anywhere to enter</div>';
          
        doc.body.appendChild(ov);
        requestAnimationFrame(function() { ov.classList.add('in'); });

        var canvas = ov.querySelector('canvas');
        var ctx = canvas.getContext('2d');
        var w, h;
        
        function resize() { 
            w = canvas.width = ov.clientWidth; 
            h = canvas.height = ov.clientHeight; 
        }
        resize();

        var fov = 500;
        var max_depth = 1500;
        var speed = 3.5;
        var num_stars = 1200;

        function mkStar(initZ) {
          var r = Math.random();
          var c = r < 0.58 ? '#D68A18' : (r < 0.97 ? '#20AB7D' : '#3696E3');
          return {
            x: (Math.random() - 0.5) * w * 5,
            y: (Math.random() - 0.5) * h * 5,
            z: initZ ? Math.random() * max_depth : max_depth,
            base_s: Math.random() * 2.5 + 1.5,
            c: c
          };
        }
        
        var stars = [];
        for (var i = 0; i < num_stars; i++) stars.push(mkStar(true));

        var raf = null, running = true;
        function frame() {
          if (!running) return;
          ctx.clearRect(0, 0, w, h);
          
          var cx = w / 2;
          var cy = h / 2;

          for (var i = 0; i < num_stars; i++) {
            var s = stars[i];
            s.z -= speed;
            
            if (s.z <= 0) {
                stars[i] = mkStar(false);
                s = stars[i];
            }
            
            var scale = fov / s.z;
            var px = cx + (s.x * scale);
            var py = cy + (s.y * scale);
            var pSize = s.base_s * scale;

            if (px >= 0 && px <= w && py >= 0 && py <= h) {
                var op = (1 - s.z / max_depth) * 1.5;
                op = Math.min(Math.max(op, 0), 0.95);
                
                ctx.globalAlpha = op;
                ctx.fillStyle = s.c;
                ctx.beginPath();
                ctx.arc(px, py, pSize, 0, Math.PI * 2);
                ctx.fill();
            }
          }
          raf = requestAnimationFrame(frame);
        }
        frame();
        window.addEventListener('resize', resize);

        function dismiss() {
          var el = doc.getElementById('meco-intro-singleton');
          if (!el) return;
          running = false;
          try { cancelAnimationFrame(raf); } catch (e) {}
          el.classList.add('fade');
          setTimeout(function() { if (el && el.parentNode) el.parentNode.removeChild(el); }, 900);
        }
        ov.addEventListener('click', dismiss);

      } catch (e) {}
    })();
    </script>
    """, height=0)


# ════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ════════════════════════════════════════════════════════════════
def section_sep():
    st.markdown('<div class="section-sep"></div>', unsafe_allow_html=True)

def credibility_badge(has_real: bool = True, has_sim: bool = False):
    badges = ""
    if has_real:
        badges += ('<span class="badge badge-real"><span class="badge-dot"></span>'
                   'Real data · Jacobs et al. (2025)</span>')
    if has_sim:
        badges += ('<span class="badge badge-sim"><span class="badge-dot"></span>'
                   'Simulated / illustrative</span>')
    st.markdown(f'<div class="badge-row">{badges}</div>', unsafe_allow_html=True)

def build_sankey(groups, label_r, label_e, label_s):
    """Build a 3 to 6 Sankey from paradigm sources to target-group sinks.

    Args:
        groups: list of dicts with keys {'key', 'label', 'replace', 'enhance',
                'support'}. 'key' is used for coloring ('critical' → green
                highlight, 'other' → muted, everything else → neutral gray).
        label_r/e/s: source-node labels (e.g. "Replace  58%").
    """
    n_groups = len(groups)
    nodes = [label_r, label_e, label_s] + [g["label"] for g in groups]

    # Node colors: sources use paradigm palette; target colors depend on group.
    source_colors = [
        "rgba(168,116,14,0.88)",   # Replace amber
        "rgba(29,140,105,0.85)",   # Enhance green
        "rgba(46,124,184,0.88)",   # Support blue
    ]
    target_colors = []
    for g in groups:
        if g["key"] == "critical":
            target_colors.append("rgba(61,122,82,0.90)")   # highlighted green
        elif g["key"] == "other":
            target_colors.append("rgba(184,176,164,0.75)") # muted
        else:
            target_colors.append("rgba(138,132,123,0.80)") # neutral gray
    node_colors = source_colors + target_colors

# Precompute paradigm totals for percentage math in hover tooltips.
    source_totals = [
        sum(g["replace"] for g in groups),   # 0: Replace total
        sum(g["enhance"] for g in groups),   # 1: Enhance total
        sum(g["support"] for g in groups),   # 2: Support total
    ]

    # Flows: for each group, add one link from each paradigm source.
    # Skip zero-value flows to keep the layout clean. Also record customdata
    # per link — [pct_of_target, pct_of_source] — for hover percentages.
    source, target, value, link_colors, link_customdata = [], [], [], [], []
    for i, g in enumerate(groups):
        target_idx = 3 + i
        target_total = g["replace"] + g["enhance"] + g["support"]
        for src_idx, paradigm_key, paradigm_name, base_rgb in [
            (0, "replace", "Replace", "168,116,14"),
            (1, "enhance", "Enhance", "29,140,105"),
            (2, "support", "Support", "46,124,184"),
        ]:
            v = g[paradigm_key]
            if v <= 0:
                continue
            source.append(src_idx); target.append(target_idx); value.append(v)
            pct_s = v / source_totals[src_idx] * 100 if source_totals[src_idx] else 0
            link_customdata.append([paradigm_name, pct_s])
            # Highlight the Support → Critical link — the narrative's punchline.
            if g["key"] == "critical" and src_idx == 2:
                link_colors.append("rgba(61,122,82,0.55)")
            elif g["key"] == "critical":
                link_colors.append("rgba(61,122,82,0.20)")
            else:
                link_colors.append(f"rgba({base_rgb},0.22)")

    # Node customdata: pre-formatted breakdown strings for hover.
    # Source nodes → simple total. Target nodes → full R/E/S breakdown.
    node_customdata = []
    for src_idx in range(3):
        node_customdata.append(f"{source_totals[src_idx]:,} papers total")
    for g in groups:
        t_total = g["replace"] + g["enhance"] + g["support"]
        if t_total > 0:
            r_pct = g["replace"] / t_total * 100
            e_pct = g["enhance"] / t_total * 100
            s_pct = g["support"] / t_total * 100
            node_customdata.append(
                f"{t_total:,} papers received<br>"
                f"Replace: {g['replace']:,} ({r_pct:.0f}%)<br>"
                f"Enhance: {g['enhance']:,} ({e_pct:.0f}%)<br>"
                f"Support: {g['support']:,} ({s_pct:.0f}%)"
            )
        else:
            node_customdata.append("(empty)")

    # Manual node positioning — force sources to spread evenly on the left
    _node_x = [0.001, 0.001, 0.001] + [0.999] * n_groups
    _node_y = [0.18, 0.7, 0.95] + [
        (i + 0.5) / n_groups for i in range(n_groups)
    ]

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=18, thickness=22, label=nodes, color=node_colors,
            x=_node_x, y=_node_y,
            customdata=node_customdata,
            hovertemplate="<b>%{label}</b><br>%{customdata}<extra></extra>",
            line=dict(color="#FFFFFF", width=0.5),
        ),
        link=dict(
            source=source, target=target, value=value, color=link_colors,
            customdata=link_customdata,
            hovertemplate=(
                "<b>%{customdata[1]:.0f}% of %{customdata[0]}</b> "
                "→ <b>%{target.label}</b>"
                "<br>Flow: <b>%{value:,}</b> papers"
                "<extra></extra>"
            ),
        ),
    ))
    fig.update_layout(paper_bgcolor="#FFFFFF",
                      font=dict(size=11, color="#4A453E", family="Inter, sans-serif"),
                      height=560, margin=dict(l=10, r=10, t=25, b=45))
    return fig


def _s4_target_groups():
    """Build the 6-target groups for Sankey chart.
    Structure:
        - Top 4 services by total paper count (excluding critical food-system services)
        - Critical Services   (Pollination + Soil Formation + Nutrient Cycling)
        - Other Services      (everything else)

    Returns a list of dicts:
        {'key', 'label', 'replace', 'enhance', 'support', 'total'}
    """
    CRITICAL = {"Pollination", "Soil Formation", "Nutrient Cycling"}

    # Rank services by total, excluding critical from the top-4 pool
    ranked = sorted(
        [s for s in SVC_SUMMARY["services"] if s["service"] not in CRITICAL],
        key=lambda s: s["total"],
        reverse=True,
    )
    top4 = ranked[:4]
    top4_names = {s["service"] for s in top4}

    groups = []
    for s in top4:
        groups.append({
            "key": s["service"],
            "label": display_name(s["service"]),
            "replace": int(s["replace"]),
            "enhance": int(s["enhance"]),
            "support": int(s["support"]),
            "total":   int(s["total"]),
        })

    # Critical group — sum of the three food-system services
    crit = {"replace": 0, "enhance": 0, "support": 0, "total": 0}
    for s in SVC_SUMMARY["services"]:
        if s["service"] in CRITICAL:
            for k in ("replace", "enhance", "support", "total"):
                crit[k] += int(s[k])
    groups.append({
        "key": "critical",
        "label": "Critical Services\n(Pollination · Soil · Nutrients)",
        **crit,
    })

    # Other group — everything not in top-4 and not critical
    other = {"replace": 0, "enhance": 0, "support": 0, "total": 0}
    for s in SVC_SUMMARY["services"]:
        if s["service"] not in top4_names and s["service"] not in CRITICAL:
            for k in ("replace", "enhance", "support", "total"):
                other[k] += int(s[k])
    groups.append({
        "key": "other",
        "label": "Other Services",
        **other,
    })

    return groups


def _s4_scenario_groups(real_groups, tgt_r_pct, tgt_e_pct, tgt_s_pct):
    """Recompute each group's R/E/S under a hypothetical global paradigm mix.

    Total corpus stays the same. Each paradigm's global total is set to
    (target_pct × total). Each group keeps its relative share within each
    paradigm — so the target rankings don't change, only the paradigm mix.
    """
    real_r = sum(g["replace"] for g in real_groups)
    real_e = sum(g["enhance"] for g in real_groups)
    real_s = sum(g["support"] for g in real_groups)
    total = real_r + real_e + real_s
    tgt_r = total * tgt_r_pct
    tgt_e = total * tgt_e_pct
    tgt_s = total * tgt_s_pct

    scenario = []
    for g in real_groups:
        share_r = g["replace"] / real_r if real_r else 0
        share_e = g["enhance"] / real_e if real_e else 0
        share_s = g["support"] / real_s if real_s else 0
        new_r = int(round(share_r * tgt_r))
        new_e = int(round(share_e * tgt_e))
        new_s = int(round(share_s * tgt_s))
        scenario.append({
            "key":     g["key"],
            "label":   g["label"],
            "replace": new_r,
            "enhance": new_e,
            "support": new_s,
            "total":   new_r + new_e + new_s,
        })
    return scenario


# ════════════════════════════════════════════════════════════════
# SECTION 0 · Feel 
# ════════════════════════════════════════════════════════════════

# Hero-nav + opening-animation CSS.
st.markdown("""
<style>
/* ── Hero navigation ──────────────────────────────────────── */
.hero-nav { display: flex; gap: 10px; align-items: flex-start; flex-wrap: wrap;
            margin-bottom: 1.7rem; }
.hn-primary {
    font: 500 .74rem/1 'Inter', sans-serif; letter-spacing: .02em;
    padding: 9px 16px; border-radius: 20px; text-decoration: none;
    background: rgba(61,122,82,0.10); color: #356B49;
    border: 1px solid rgba(61,122,82,0.40);
    transition: background .18s, border-color .18s;
}
.hn-primary:hover { background: rgba(61,122,82,0.17); border-color: rgba(61,122,82,0.65); }
/* Secondary pill — the researchers' shortcut straight to the Data Sandbox */
.hn-secondary {
    font: 500 .74rem/1 'Inter', sans-serif; letter-spacing: .02em;
    padding: 9px 16px; border-radius: 20px; text-decoration: none;
    background: #FFFFFF; color: #4A453E; border: 1px solid #E5E1DA;
    transition: background .18s, border-color .18s, color .18s;
}
.hn-secondary:hover {
    border-color: rgba(61,122,82,0.45); background: rgba(61,122,82,0.05); color: #2A2722;
}
/* Stop scrolled-to headings from hiding under the top padding */
.sec-anchor { display: block; height: 0; scroll-margin-top: 2rem; }

/* ── One-time opening animation (full-screen overlay injected by JS) ─────── */
.meco-intro {
    position: fixed; inset: 0; z-index: 999999;
    background: #F7F5F1; overflow: hidden; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    opacity: 1; transition: opacity .85s ease;
}
.meco-intro.fade { opacity: 0; }
.meco-intro canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
.meco-intro .intro-center {
    position: relative; z-index: 2; text-align: center; padding: 0 1.5rem;
    opacity: 0; transform: translateY(10px);
    transition: opacity 1s ease .25s, transform 1s ease .25s;
}
.meco-intro.in .intro-center { opacity: 1; transform: translateY(0); }
.meco-intro .intro-n   { font: 700 4.2rem/1.05 'Playfair Display', serif; color: #2A2722; }
.meco-intro .intro-cap { font: 300 1.15rem/1.6 'Inter', sans-serif; color: #6B665E; margin-top: .7rem; }
.meco-intro .intro-legend {
    margin-top: 1.8rem; display: flex; justify-content: center; gap: 24px;
    font: 400 .85rem/1 'Inter', sans-serif; color: #6B665E;
}
.meco-intro .leg-item { display: flex; align-items: center; gap: 8px; }
.meco-intro .leg-dot  { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.meco-intro .intro-skip {
    position: absolute; bottom: 40px; left: 50%; transform: translateX(-50%); z-index: 2;
    font: 400 .75rem/1 'Inter', sans-serif; letter-spacing: .2em; text-transform: uppercase; color: #8A847B;
    animation: meco-intro-pulse 2.5s infinite ease-in-out;
}
@keyframes meco-intro-pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
@media (max-width: 640px) {
    .meco-intro .intro-n { font-size: 2.6rem; }
    .meco-intro .intro-legend { flex-direction: column; gap: 12px; align-items: center; }
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="hero-eyebrow">Manufactured Ecosystems · Research Dashboard</div>',
            unsafe_allow_html=True)
st.markdown('<h1 class="hero-title">Nature Is Not Optional.</h1>', unsafe_allow_html=True)
st.markdown("""
<p class="hero-sub">
    Over 68,000 scientific papers. Twenty years of research.<br>
    One urgent question: <em>can technology replace what nature provides?</em><br><br>
    Before we show you the data, we want to ask something about your day.
</p>
""", unsafe_allow_html=True)



st.markdown("""
<div class="hero-prompt">
    <strong>Tap everything you've already done since you woke up this morning.</strong>
    Small, ordinary things — each one quietly leans on nature.
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
st.markdown('<div id="sec-feel" class="sec-anchor"></div>', unsafe_allow_html=True)

# ── Everyday actions → the ecosystem services they quietly invoke ──
_EVERYDAY_ACTIONS = {
    "Drank coffee or tea":                 ["Potable Water", "Pollination", "Soil Formation", "Nutrient Cycling"],
    "Ate a meal with fresh produce":       ["Food", "Pollination", "Primary Production", "Biodiversity"],
    "Put on cotton or wool clothing":      ["Fibre/Hide/Wood", "Soil Formation", "Nutrient Cycling"], 
    "Took a deep breath outside":          ["Atmospheric Regulation", "Climate Regulation", "Disease Regulation"], 
    "Washed up or flushed the toilet":     ["Potable Water", "Waste Treatment", "Water Regulation"],
    "Took medication or vitamins":          ["Biochemicals"],
    "Turned on the heating or AC":          ["Fuel", "Climate Regulation"],
    "Walked in a park or noticed nature":  ["Aesthetic", "Recreation", "Inspiration/Education"], 
    "Used paper or wooden products":       ["Fibre/Hide/Wood", "Primary Production"], 
    "Felt tied to your local landscape":   ["Cultural Heritage", "Spiritual", "Cultural Identity"],
    "Saw a bird, insect, or wild animal":  ["Biodiversity", "Pollination", "Coastline Regulation"],
}

# Native pills 
selected_actions = st.pills(
    "Everyday actions",
    options=list(_EVERYDAY_ACTIONS.keys()),
    selection_mode="multi",
    label_visibility="collapsed",
) or []

st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

# 1. Raw Names
triggered_raw_names = set()
for action in selected_actions:
    triggered_raw_names.update(_EVERYDAY_ACTIONS[action])

# 2. Sync triggered services into session_state.
# Keys use display names because downstream UI components reference s["name"].
# Matching remains based on RAW ecosystem service identifiers.
for s_cat in SERVICES.values():
    for s_item in s_cat["items"]:
        raw_val = raw_name(s_item["name"])

        st.session_state[s_item["name"]] = (
            raw_val in triggered_raw_names
        )

all_services_flat = [s for cat in SERVICES.values() for s in cat["items"]]

selected_services = [
    s for s in all_services_flat 
    if raw_name(s["name"]) in triggered_raw_names
]

num_actions = len(selected_actions)
num_services = len(selected_services)

# ── Live counter ──────────────────────────────────────────────
st.markdown(f"""
<div class="ctr">
    <div class="ctr-n">{num_services}</div>
    <div class="ctr-sub">
        hidden ecosystem {"service" if num_services == 1 else "services"} behind your
        {num_actions} routine {"action" if num_actions == 1 else "actions"}
    </div>
</div>
""", unsafe_allow_html=True)

# ── Personalised insight panel ───────────────────────────────
if num_services == 0:
    st.markdown("""
    <div class="insight-empty">
        ↑ Tap at least one everyday action to reveal the unseen natural systems running in the background.
    </div>
    """, unsafe_allow_html=True)

else:
    gap_services = [s for s in selected_services if s["papers"] < RESEARCH_GAP_THRESHOLD]
    well_researched_services = [s for s in selected_services if s["papers"] >= RESEARCH_GAP_THRESHOLD]

    num_gaps = len(gap_services)
    act_word = "action" if num_actions == 1 else "actions"

    if num_gaps == 0:
        body_text = (
            f'Those <span class="hl-green">{num_actions}</span> simple {act_word} quietly rely on '
            f'<span class="hl-green">{num_services}</span> distinct ecosystem services. '
            f'The ones behind your choices happen to be relatively well-studied in bio-inspired research. '
            f"Scroll down to see what happens to the rest."
        )
    elif num_gaps == num_services:
        body_text = (
            f'You thought you were just going about your day — but those '
            f'<span class="hl-green">{num_actions}</span> {act_word} invoked '
            f'<span class="hl-red">{num_services}</span> distinct ecosystem services, and '
            f'<em>every single one</em> has fewer than {RESEARCH_GAP_THRESHOLD:,} bio-inspired research papers. '
            f'Science is building technological backups — just not yet for the things <em>you</em> just relied on.'
        )
    else:
        body_text = (
            f'You thought you were just going about your day. In fact those '
            f'<span class="hl-green">{num_actions}</span> {act_word} quietly invoked '
            f'<span class="hl-green">{num_services}</span> distinct ecosystem services — and '
            f'<span class="hl-red">{num_gaps}</span> of them '
            f'{"has" if num_gaps == 1 else "have"} fewer than {RESEARCH_GAP_THRESHOLD:,} bio-inspired research papers. '
            f'If those hidden systems fail, very few technological backup plans currently exist.'
        )

    gap_html_list = []
    for s in gap_services:
        if isinstance(s, dict):
            icon = s.get("icon", "🌱")
            safe_name = str(s.get("name", "Unknown Service")).replace("<", "&lt;").replace(">", "&gt;")
            gap_html_list.append(f'<span class="tag tag-gap">{icon} {safe_name}</span>')

    gap_tags_html = "".join(gap_html_list)

    ok_html_list = []
    for s in well_researched_services:
        if isinstance(s, dict):
            icon = s.get("icon", "🌱")
            safe_name = str(s.get("name", "Unknown Service")).replace("<", "&lt;").replace(">", "&gt;")
            ok_html_list.append(f'<span class="tag tag-ok">{icon} {safe_name}</span>')

    ok_tags_html = "".join(ok_html_list)

    gap_block_html = (
        f'<div style="margin-bottom:.9rem">'
        f'<div class="tag-sec-lbl lbl-gap">Research gap — fewer than {RESEARCH_GAP_THRESHOLD:,} papers ({num_gaps})</div>'
        f'{gap_tags_html}'
        f'</div>'
    ) if gap_services else ""

    ok_block_html = (
        f'<div style="margin-bottom:1.4rem">'
        f'<div class="tag-sec-lbl lbl-ok">Better researched ({len(well_researched_services)})</div>'
        f'{ok_tags_html}'
        f'</div>'
    ) if well_researched_services else ""

    html_payload = [
        '<div class="insight">',
        '<div class="insight-title">What the research says about your choices.</div>',
        f'<div class="insight-body">{body_text}</div>',
        gap_block_html,
        ok_block_html,
        '<div class="insight-cta">↓ &nbsp; Scroll to see what 20 years of global research actually looks like</div>',
        '</div>'
    ]
    
    final_html = "".join([p for p in html_payload if p != ""])
    st.markdown(final_html, unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# SECTION 1 · Discovery 
# ════════════════════════════════════════════════════════════════
# section_sep()
st.markdown('<div id="sec-discovery" class="sec-anchor"></div>', unsafe_allow_html=True)
st.markdown('<div class="s1-eyebrow">Section 01 · Discovery</div>', unsafe_allow_html=True)
st.markdown(f'<h2 class="s1-title">{CORPUS["total_papers"]:,} Attempts.</h2>', unsafe_allow_html=True)
st.markdown(f"""
<p class="s1-sub">
    For twenty years, the global scientific community has been working on
    something unprecedented: learning from nature in order to engineer it.
    {CORPUS["total_papers"]:,} published papers. Hundreds of research groups. A shared, if often
    unspoken, question —
    <em style="color:#4A453E; font-style:italic">
    what happens when the natural world can no longer do this on its own?</em>
</p>
<p class="s1-sub">Before we show you the gaps, here is the scale of the effort.</p>
""", unsafe_allow_html=True)
st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

# Build percentages live from the real paradigm totals.
_pt = SVC_SUMMARY["paradigm_totals"]
_pt_total = _pt["replace"] + _pt["enhance"] + _pt["support"]
_pct_replace = round(_pt["replace"] / _pt_total * 100) if _pt_total else 0
_pct_support = round(_pt["support"] / _pt_total * 100) if _pt_total else 0
_n_engaged = sum(1 for s in SVC_SUMMARY["services"] if s["total"] > 0)
_n_total_svc = len(SVC_SUMMARY["services"])

st.markdown(f"""
<div class="kpi-grid">
  <div class="kpi-card">
    <span class="kpi-val">{CORPUS["non_review"]:,}</span>
    <span class="kpi-label">Non-review papers</span>
    <span class="kpi-note">Of which {CORPUS["decision_y"]:,} describe<br>a technology linked to an ES</span>
  </div>
  <div class="kpi-card">
    <span class="kpi-val">{_n_engaged} / {_n_total_svc}</span>
    <span class="kpi-label">Services engaged</span>
    <span class="kpi-note">Spiritual &amp; Cultural Identity<br>remain entirely out of reach</span>
  </div>
  <div class="kpi-card accent-amber">
    <span class="kpi-val kpi-val-amber">{_pct_replace}%</span>
    <span class="kpi-label">Aim to replace nature</span>
    <span class="kpi-note">The dominant paradigm —<br>stand-alone substitutes for ES</span>
  </div>
  <div class="kpi-card accent-green">
    <span class="kpi-val kpi-val-green">{_pct_support}%</span>
    <span class="kpi-label">Aim to support nature</span>
    <span class="kpi-note">The most ecologically aligned<br>approach, yet heavily marginalized</span>
  </div>
</div>
""", unsafe_allow_html=True)


st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
st.markdown("""
<div class="s1-bridge">
    This imbalance is not a recent development.
    <em>It has been building for twenty years</em> — and accelerating
    as the climate crisis intensifies the demand for technological solutions.
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="chart-label">Biomimetic design paradigms · 2004 – 2025</div>',
            unsafe_allow_html=True)
credibility_badge(has_real=True, has_sim=False)

# Real annual data from annual_by_category.json
_years        = ANNUAL["years"]
_replace_data = ANNUAL["replace"]
_enhance_data = ANNUAL["enhance"]
_support_data = ANNUAL["support"]

# Compute paradigm percentages for legend labels
_total_all = sum(_replace_data) + sum(_enhance_data) + sum(_support_data)
_pct_r = round(sum(_replace_data) / _total_all * 100) if _total_all else 0
_pct_e = round(sum(_enhance_data) / _total_all * 100) if _total_all else 0
_pct_s = round(sum(_support_data) / _total_all * 100) if _total_all else 0

_area_fig = go.Figure()
_area_fig.add_trace(go.Scatter(x=_years, y=_support_data, name=f"Support  ({_pct_s}%)", mode="lines",
    line=dict(width=0.8, color="#2E7CB8"), fillcolor="rgba(46,124,184,0.55)", stackgroup="one",
    hovertemplate="<b>%{x}</b><br>Support: %{y:,} papers<extra></extra>"))
_area_fig.add_trace(go.Scatter(x=_years, y=_enhance_data, name=f"Enhance  ({_pct_e}%)", mode="lines",
    line=dict(width=0.8, color="#1D8C69"), fillcolor="rgba(29,140,105,0.42)", stackgroup="one",
    hovertemplate="<b>%{x}</b><br>Enhance: %{y:,} papers<extra></extra>"))
_area_fig.add_trace(go.Scatter(x=_years, y=_replace_data, name=f"Replace  ({_pct_r}%)", mode="lines",
    line=dict(width=0.8, color="#A8740E"), fillcolor="rgba(168,116,14,0.45)", stackgroup="one",
    hovertemplate="<b>%{x}</b><br>Replace: %{y:,} papers<extra></extra>"))
_area_fig.add_vline(x=2013, line_dash="dot", line_color="rgba(42,39,34,0.20)", line_width=1.2)
_area_fig.add_annotation(x=2013.25, y=0.97, yref="paper",
    text='Fitter (2013):<br>"Can ES be replaced?"',
    font=dict(size=9, color="#6B665E", family="Inter, sans-serif"),
    showarrow=False, xanchor="left", yanchor="top")
# Support annotation: anchor to the latest year with data
_support_anno_year = _years[-2] if len(_years) >= 2 else _years[-1]
_support_anno_val  = _support_data[_years.index(_support_anno_year)]

_area_fig.add_annotation(
    x=2024, y=100, 
    text=f"<b>Support: {_pct_s}%</b><br>Most needed. Least resourced.",
    font=dict(size=9, color="#2E7CB8", family="Inter, sans-serif"),
    showarrow=True, 
    arrowhead=2, 
    arrowcolor="#2E7CB8", 
    arrowwidth=1.2, 
    ax=-90, ay=-80, 
    bgcolor="rgba(255,255,255,0.92)", 
    bordercolor="rgba(46,124,184,0.35)", 
    borderwidth=1, 
    borderpad=4
)

_area_fig.update_layout(
    paper_bgcolor="#FFFFFF", 
    plot_bgcolor="#FBF9F5",
    height=430, 
    margin=dict(l=50, r=15, t=15, b=45), 
    hovermode="x unified",
    hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#E5E1DA",
                    font=dict(size=11, color="#2A2722", family="Inter, sans-serif")),
    legend=dict(orientation="h", y=1.03, x=0.99, xanchor="right", yanchor="bottom",
                font=dict(size=11, color="#6B665E", family="Inter, sans-serif"),
                bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)", traceorder="reversed"),
    xaxis=dict(
        tickmode="array",
        tickvals=[2004, 2006, 2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024, 2025],
        range=[2004, 2025], 
        tickfont=dict(size=11, color="#8A847B"),
        gridcolor="#ECE8E1", 
        linecolor="#E5E1DA", 
        zeroline=False
    ),
    yaxis=dict(
        title=dict(text="ES-linked publications per year",
                   font=dict(size=11, color="#8A847B")),
        tickfont=dict(size=11, color="#8A847B"), 
        tickformat=",",
        gridcolor="#ECE8E1", 
        linecolor="#E5E1DA", 
        zeroline=False
    )
)
st.plotly_chart(_area_fig, use_container_width=True, config={"displayModeBar": False})
st.markdown("""
<p style="font:300 .68rem/1.7 'Inter',sans-serif;color:#B8B0A4;margin-top:.6rem;padding-left:2px;">
    Annual counts derived from GPT-4.1 classification of the full corpus.
    Each paper is assigned to one of three design paradigms (Replace / Enhance / Support)
    as defined in Jacobs et al. (2025).
    <a href="https://doi.org/10.3390/biomimetics10110784" target="_blank" style="color:#9A938A;">
        Read the full paper →</a>
</p>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# SECTION 2 · The Gap Map  
# ════════════════════════════════════════════════════════════════
# section_sep()
st.markdown('<div id="sec-gap" class="sec-anchor"></div>', unsafe_allow_html=True)
st.markdown('<div class="s2-eyebrow">Section 02 · The Gap Map</div>', unsafe_allow_html=True)
st.markdown('<h2 class="s2-title">The Services Nobody Is Building.</h2>', unsafe_allow_html=True)
st.markdown(f"""
<p class="s2-sub">
    <b>{CORPUS["decision_y"]:,} papers</b> in the corpus describe technologies
    linked to one of 22 ecosystem services. The chart below shows where
    those papers go — and where the foundations of our food system,
    our water cycle, and our cultural identity are left almost entirely
    unaddressed.
</p>
""", unsafe_allow_html=True)
st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

# ── Ecosystem service coverage — horizontal stacked bars ─────────

_CAT_ORDER2 = ["Provisioning", "Regulating", "Supporting", "Cultural"]
_R_COL2 = {
    "support": "rgba(46,124,184,0.90)",   # blue
    "enhance": "rgba(29,140,105,0.85)",   # green
    "replace": "rgba(168,116,14,0.88)",   # amber
}
_CRITICAL_SERVICES = {"Pollination", "Soil Formation", "Nutrient Cycling"}

# Sort: group by category (family), then largest→smallest within each group.
_ord2 = pd.concat(
    [_df2[_df2["category"] == _c].sort_values("total", ascending=False)
     for _c in _CAT_ORDER2]
).reset_index(drop=True)

# Build tick labels + stacked values. 
_labels = []
_replace_vals, _enhance_vals, _support_vals = [], [], []
_totals = []
_prev_cat = None
for _, _r in _ord2.iterrows():
    if _r["category"] != _prev_cat:
        _n_in_cat = int((_ord2["category"] == _r["category"]).sum())
        _labels.append(
            f"<b><span style='color:#8A847B;letter-spacing:0.18em'>"
            f"{_r['category']}</span></b>"
        )
        _replace_vals.append(0); _enhance_vals.append(0); _support_vals.append(0)
        _totals.append(-1)  
    _svc = _r["service"]
    if _svc in _CRITICAL_SERVICES:
        # critical food-system services — warm red highlight
        _label_html = f"<span style='color:#B34C2F'>{_svc}</span>"
    else:
        _label_html = _svc
    _labels.append(_label_html)
    _replace_vals.append(int(_r["replace"]))
    _enhance_vals.append(int(_r["enhance"]))
    _support_vals.append(int(_r["support"]))
    _totals.append(int(_r["total"]))
    _prev_cat = _r["category"]

# ── Build the figure ────────────────────────────────────────────
_row_h = 24
_fig_h = len(_labels) * _row_h + 70

_bar_fig = go.Figure()
_yidx = list(range(len(_labels)))

_bar_fig.add_trace(go.Bar(
    x=_replace_vals, y=_yidx, orientation='h', name='Replace',
    marker=dict(color=_R_COL2["replace"], line=dict(color="#FFFFFF", width=0.5)),
    hovertemplate="Replace: <b>%{x:,}</b><extra></extra>"))
_bar_fig.add_trace(go.Bar(
    x=_enhance_vals, y=_yidx, orientation='h', name='Enhance',
    marker=dict(color=_R_COL2["enhance"], line=dict(color="#FFFFFF", width=0.5)),
    hovertemplate="Enhance: <b>%{x:,}</b><extra></extra>"))
_bar_fig.add_trace(go.Bar(
    x=_support_vals, y=_yidx, orientation='h', name='Support',
    marker=dict(color=_R_COL2["support"], line=dict(color="#FFFFFF", width=0.5)),
    hovertemplate="Support: <b>%{x:,}</b><extra></extra>"))

# Total-count annotation at bar end (skip header + zero rows)
for _i, _t in enumerate(_totals):
    if _t > 0:
        _bar_fig.add_annotation(
            x=_t, y=_i, text=f"{_t:,}",
            xanchor="left", yanchor="middle", xshift=6,
            font=dict(size=10, color="#6B665E", family="Inter, sans-serif"),
            showarrow=False)

_bar_fig.update_layout(
    barmode='stack',
    paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
    height=_fig_h,
    margin=dict(l=200, r=90, t=30, b=55),
    bargap=0.28,
    showlegend=True,
    legend=dict(
        orientation="h", y=1.03, x=1, xanchor="right", yanchor="bottom",
        font=dict(size=11, color="#6B665E", family="Inter, sans-serif"),
        bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)",
        traceorder="normal"),
    xaxis=dict(
        tickfont=dict(size=10, color="#8A847B"), tickformat=",",
        gridcolor="#F1EEE8", linecolor="#E5E1DA",
        showline=True, zeroline=False, ticks="outside", ticklen=4),
    yaxis=dict(
        tickmode='array',
        tickvals=_yidx, ticktext=_labels,
        tickfont=dict(size=11, color="#4A453E", family="Inter, sans-serif"),
        # autorange='reversed', 
        range=[len(_labels) - 0.5, -0.5],
        showline=False, ticks=""),
    hoverlabel=dict(
        bgcolor="#FFFFFF", bordercolor="#E5E1DA",
        font=dict(size=11, color="#2A2722", family="Inter, sans-serif")),
)

# ── Family background bands ─────────────────────────────────────
_family_tints = {
    "Provisioning": "rgba(168,116,14,0.1)",   # amber wash
    "Regulating":   "rgba(46,124,184,0.1)",   # blue wash
    "Supporting":   "rgba(29,140,105,0.1)",   # green wash
    "Cultural":     "rgba(120,120,120,0.1)",  # grey wash
}

# Walk _labels to find each family's start/end row index. 
_family_ranges = []   
_cur_family = None
_cur_start = None
for _i, _lbl in enumerate(_labels):
    if "<b><span" in _lbl:  # this is a family-header row
        if _cur_family is not None:
            _family_ranges.append((_cur_family, _cur_start, _i - 1))
        # pull family name out of the header text
        for _fam in _family_tints:
            if _fam in _lbl:
                _cur_family = _fam
                _cur_start = _i
                break
if _cur_family is not None:
    _family_ranges.append((_cur_family, _cur_start, len(_labels) - 1))

for _fam, _s, _e in _family_ranges:
    _bar_fig.add_shape(
        type="rect",
        xref="paper", yref="y",
        x0=0, x1=1,
        y0=_s - 0.5, y1=_e + 0.5,
        fillcolor=_family_tints[_fam],
        line=dict(width=0),
        layer="below",
    )

# ── Key insight — placed in the empty lower-right of the chart ────
_bar_fig.add_annotation(
    xref="x", yref="y",
    x=10100,                       
    y=len(_labels) - 0.5,        
    xanchor="right", yanchor="bottom",
    align="left",
    text=(
        "<span style='letter-spacing:.14em;color:#8A847B;font-size:10px'>"
        "KEY INSIGHT</span><br>"
        "<span style='color:#2A2722;font-size:10px;line-height:1.55'>"
        "Half the 31,559-paper corpus goes<br>"
        "to just three ecosystem services.<br>"
        "Two — <i>Spiritual</i> and <i>Cultural Identity</i> — <br>"
        "have zero papers."
        "</span>"
    ),
    showarrow=False,
    bordercolor="rgba(0,0,0,0)",
    borderwidth=0,
    borderpad=14,
    bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif"),
)

# Subtle left accent bar for the insight — a single line, warm tone.
_bar_fig.add_shape(
    type="line",
    xref="x", yref="y",
    x0=6700, x1=6700,             
    y0=len(_labels) - 0.5,       
    y1=len(_labels) - 4.8,       
    line=dict(color="#B34C2F", width=2),
)

# ── Display ─────────────────────────────────────────────────────
st.markdown(
    '<div class="chart-label">Half the corpus goes to just three ecosystem services</div>',
    unsafe_allow_html=True)
credibility_badge(has_real=True, has_sim=False)
st.markdown(
    '<p class="chart-sub-label">'
    'Sorted within each family by paper count. Colours split each bar by '
    'paradigm — '
    '<span style="color:#A87614;font-weight:500">Replace</span>, '
    '<span style="color:#1D8C69;font-weight:500">Enhance</span>, '
    '<span style="color:#2E7CB8;font-weight:500">Support</span>. '
    'Three food-system services are highlighted in '
    '<span style="color:#B34C2F;font-weight:500">red</span> — see the '
    'callout below.'
    '</p>',
    unsafe_allow_html=True)
st.plotly_chart(_bar_fig, use_container_width=True,theme=None,height=_fig_h, config={"displayModeBar": False})


st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
st.markdown('<div class="chart-label">The critical gap — food system services</div>',
            unsafe_allow_html=True)
credibility_badge(has_real=True, has_sim=False)
st.markdown("""
<p class="chart-sub-label">
    Pollination, soil formation, and nutrient cycling collectively
    underpin global food security. Together they account for just
    <b>796 papers</b> — about <b>7%</b> of what a single service
    (Biochemicals) has attracted.
</p>
""", unsafe_allow_html=True)
st.markdown("""
<div class="gap-grid">
  <div class="gap-card">
    <div class="gap-svc">Biochemicals</div>
    <span class="gap-n gap-n-ok">11,079</span>
    <div class="gap-sub">Molecules used in medicine. The single most-studied ES in the
        bio-inspired corpus. Strong commercial incentives drive this concentration.</div>
    <div class="gap-ratio">Reference service</div>
    <a href="/explorer?service=Biochemicals" target="_blank"
       style="display:block;margin-top:.6rem;font:500 .68rem/1 'Inter',sans-serif;color:#356B49;text-decoration:none;">View these 11079 papers →</a>
  </div>
  <div class="gap-card critical">
    <div class="gap-svc">Pollination</div>
    <span class="gap-n">355</span>
    <div class="gap-sub">Responsible for 75% of global food crop varieties.
        RoboBee can physically pollinate — but cannot replace a bee's role in the food chain above it.</div>
    <div class="gap-ratio"><b>1 paper</b> for every 31 in Biochemicals</div>
    <a href="/explorer?service=Pollination" target="_blank"
       style="display:block;margin-top:.6rem;font:500 .68rem/1 'Inter',sans-serif;color:#356B49;text-decoration:none;">View these 355 papers →</a>
  </div>
  <div class="gap-card critical">
    <div class="gap-svc">Nutrient Cycling</div>
    <span class="gap-n">58</span>
    <div class="gap-sub">The movement of nitrogen, phosphorus, and carbon through living systems.
        The rarest research topic in the entire 31,559-paper corpus.</div>
    <div class="gap-ratio"><b>1 paper</b> for every 191 in Biochemicals</div>
    <a href="/explorer?service=Nutrient%20Cycling" target="_blank"
       style="display:block;margin-top:.6rem;font:500 .68rem/1 'Inter',sans-serif;color:#356B49;text-decoration:none;">View these 58 papers →</a>
  </div>
</div>
""", unsafe_allow_html=True)

# Bar chart relocated to the Data Explorer.
st.markdown("""
<p style="font:300 .74rem/1.7 'Inter',sans-serif;color:#9A938A;margin-top:.4rem;padding-left:2px;">
    Want the exact numbers for all 22 services, sorted and filterable?
    <a href="/explorer?paradigm=Replace,Enhance,Support" target="_blank" style="color:#356B49;font-weight:500;">Open the Data Explorer ↗</a>
    &nbsp;·&nbsp;
    <a href="https://doi.org/10.3390/biomimetics10110784" target="_blank" style="color:#9A938A;">
        Read the full paper →</a>
</p>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# SECTION 2.5 · Nature's Voice 
# ════════════════════════════════════════════════════════════════

_voice_cutscene_html = """
<script>
(function() {
  try {
    var doc = window.parent.document;
    
    // Idempotency check: Ensure it plays only once per session
    if (doc.mecoVoicePlayed) return;

    if (!doc.getElementById('nv-cutscene-style')) {
        var style = doc.createElement('style');
        style.id = 'nv-cutscene-style';
        style.innerHTML = `
          /* ── 1. Presentation: Fullscreen Canvas ── */
          .nv-overlay {
            position: fixed; inset: 0; z-index: 999999;
            background: #050706; 
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            opacity: 0; pointer-events: none;
            transition: opacity 1.8s ease, background 2.0s ease;
          }
          .nv-overlay.in { opacity: 1; pointer-events: auto; cursor: pointer; }
          .nv-overlay.blooming { background: radial-gradient(circle at center, #1E3A26 0%, #0A140F 100%); }
          
          .nv-theater { text-align: center; max-width: 600px; padding: 0 20px; position: relative; z-index: 2; margin-top: 60px; }
          
          /* ── 2. Presentation: Decoupled Text Animation (no transition-delay) ── */
          .nv-line { 
            opacity: 0; 
            transform: translateY(15px); 
            transition: opacity 1.2s cubic-bezier(0.25, 0.8, 0.25, 1), transform 1.2s cubic-bezier(0.25, 0.8, 0.25, 1); 
          }
          .nv-line.visible { opacity: 1; transform: translateY(0); }
          
          .nv-l1 { font: italic 400 3.2rem/1.2 'Playfair Display', serif; color: #FFFFFF; margin-bottom: 2rem; }
          .nv-l2 { font: 300 1.1rem/1.6 'Inter', sans-serif; color: #8A847B; }
          .nv-l3 { font: 300 1.1rem/1.6 'Inter', sans-serif; color: #8A847B; margin-bottom: 0.6rem; }
          .nv-l3 b { color: #E0C589; font-weight: 500; font-size: 1.3rem; }
          .nv-l3b { font: italic 300 0.95rem/1.6 'Inter', sans-serif; color: #6B665E; margin-bottom: 3rem; }
          .nv-l3b b { color: #E0C589; font-weight: 500; }
          .nv-l4 { font: 400 1.6rem/1.4 'Playfair Display', serif; color: #85C29C; }
          
          .nv-skip { position: absolute; bottom: 40px; font: 400 .75rem/1 'Inter', sans-serif; letter-spacing: .2em; text-transform: uppercase; color: #555; animation: nv-pulse 3s infinite ease-in-out; }
          @keyframes nv-pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }

          /* ── 3. Presentation: Clean Bee Positioning ── */
          .nv-bee-container { 
              position: absolute; top: 15%; left: 50%; 
              transform: translateX(-100vw) translateY(50px) scale(0.6); 
              opacity: 0; 
              transition: transform 2.2s cubic-bezier(0.19, 1, 0.22, 1), opacity 1.5s ease; 
          }
          .nv-bee-container.visible { transform: translateX(-50%) translateY(0) scale(1); opacity: 1; }

          .nv-bee { width: 70px; height: 70px; animation: nv-bobbing 3s ease-in-out infinite; position: relative; }
          @keyframes nv-bobbing { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-12px); } }
          .nv-wing { transform-origin: bottom right; animation: nv-flap 0.08s infinite alternate; fill: rgba(255,255,255,0.7); }
          @keyframes nv-flap { 0% { transform: rotate(10deg); } 100% { transform: rotate(-25deg); } }
          
          /* ── 4. Presentation: Expression Change & Blooming ── */
          .nv-mouth-sad { opacity: 1; transition: opacity 0.4s; }
          .nv-mouth-happy { opacity: 0; transition: opacity 0.4s; }
          .nv-flower { opacity: 0; transform: scale(0) rotate(-45deg); transition: all 1.4s cubic-bezier(0.34, 1.56, 0.64, 1); position: absolute; right: -25px; top: 15px; font-size: 2rem; }
          
          .blooming-active .nv-mouth-sad { opacity: 0; }
          .blooming-active .nv-mouth-happy { opacity: 1; }
          .blooming-active .nv-flower { opacity: 1; transform: scale(1) rotate(0deg); }
        `;
        doc.head.appendChild(style);
    }

    var observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        doc.mecoVoicePlayed = true; 
        observer.disconnect();
        playCinematicCutscene(doc);
      }
    }, { threshold: 0.2 });
    
    if (window.frameElement) { observer.observe(window.frameElement); }

    // ── Core Controller ──
    function playCinematicCutscene(doc) {
      var originalOverflow = doc.body.style.overflow;
      doc.body.style.overflow = 'hidden';

      var ov = doc.createElement('div');
      ov.className = 'nv-overlay';
      ov.innerHTML = `
        <div class="nv-bee-container" id="nv-bee">
          <div class="nv-bee">
            <svg viewBox="0 0 60 60" width="70" height="70">
              <ellipse class="nv-wing" cx="25" cy="15" rx="8" ry="16" />
              <ellipse class="nv-wing" cx="33" cy="18" rx="6" ry="13" style="animation-delay: 0.04s" />
              <rect x="10" y="25" width="40" height="22" rx="11" fill="#E0C589"/>
              <rect x="20" y="25" width="6" height="22" fill="#2A2722"/>
              <rect x="32" y="25" width="6" height="22" fill="#2A2722"/>
              <polygon points="10,32 4,36 10,40" fill="#2A2722"/>
              <circle cx="44" cy="32" r="2.5" fill="#2A2722"/>
              <path class="nv-mouth-sad" d="M 43 39 Q 45 36 47 39" stroke="#2A2722" fill="transparent" stroke-width="1.5" stroke-linecap="round"/>
              <path class="nv-mouth-happy" d="M 43 37 Q 45 41 47 37" stroke="#2A2722" fill="transparent" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            <div class="nv-flower">🌸</div>
          </div>
        </div>
        <div class="nv-theater">
          <div class="nv-line nv-l1">"I am Pollination."</div>
          <div class="nv-line nv-l2">You wrote 11,079 papers about biochemicals.</div>
          <div class="nv-line nv-l3">You wrote <b>355</b> about me.</div>
          <div class="nv-line nv-l3b">For every <b>1</b> paper about me &mdash; <b>31</b> about biochemicals.</div>
          <div class="nv-line nv-l4">With me, one-third of your world blossoms.</div>
        </div>
        <div class="nv-skip">Click anywhere to continue</div>
      `;
      doc.body.appendChild(ov);

      var bee = ov.querySelector('#nv-bee');

      var FADE_OUT_MS = 1800;
      var timers = [];
      var schedule = function(fn, time) {
        var id = setTimeout(fn, time);
        timers.push(id);
      };
      var clearAllTimers = function() {
        for (var i = 0; i < timers.length; i++) {
          clearTimeout(timers[i]);
        }
      };
      var isExiting = false;
      function endCutscene() {
        if (isExiting) return;
        isExiting = true;

        clearAllTimers();

        ov.style.transition = 'opacity 1.8s ease';
        ov.classList.remove('in');

        setTimeout(function() {
          if (ov.parentNode) ov.parentNode.removeChild(ov);
          doc.body.style.overflow = originalOverflow;
        }, FADE_OUT_MS);
      }
      ov.addEventListener('click', endCutscene);

      // ==========================================
      // Director's Script Control Center 
      // ==========================================
      var T = {
        introIn: 200,        // Stage 1: Fade to black
        beeEnter: 1200,      // Stage 2: Bee flies to the center
        
        // Stage 3: Text fades in precisely line by line
        line1: 1400,         
        line2: 2600,         
        line3: 3800,         
        line3b: 5000,        // Aftershock: the 1-for-31 ratio
        line4: 6400,         // "One-third of your world blossoms"

        bloom: 7700,         // Stage 4: Climax (turns green + blooms + smiles)
        // Stage 5: held indefinitely — dismissed only by click (see above).
      };

      // Execute Timeline
      
      // Scene 1: Cut to black overlay
      schedule(function() { ov.classList.add('in'); }, T.introIn);

      // Scene 2: Bee glides in gracefully and lands in the center
      schedule(function() { bee.classList.add('visible'); }, T.beeEnter);

      // Scene 3: Text flows in at strictly declared time points
      schedule(function() { ov.querySelector('.nv-l1').classList.add('visible'); }, T.line1);
      schedule(function() { ov.querySelector('.nv-l2').classList.add('visible'); }, T.line2);
      schedule(function() { ov.querySelector('.nv-l3').classList.add('visible'); }, T.line3);
      schedule(function() { ov.querySelector('.nv-l3b').classList.add('visible'); }, T.line3b);
      schedule(function() { ov.querySelector('.nv-l4').classList.add('visible'); }, T.line4);

      // Scene 4: Nature's awakening (Background colors, flower blooms, smile appears)
      schedule(function() {
        ov.classList.add('blooming');
        bee.classList.add('blooming-active');
      }, T.bloom);
    }

  } catch (e) {}
})();
</script>
"""
components.html(_voice_cutscene_html, height=0)

# ═════════════════════════════════
# SECTION 3 · Islands of Expertise 
# ════════════════════════════════
# section_sep()
st.markdown('<div id="sec-islands" class="sec-anchor"></div>', unsafe_allow_html=True)
st.markdown('<div class="s3-eyebrow">Section 03 · Islands of Expertise</div>', unsafe_allow_html=True)
st.markdown('<h2 class="s3-title">Bio-inspired &ne; Ecosystem-informed.</h2>', unsafe_allow_html=True)
st.markdown(f"""
<p class="s3-sub">
    Biomimetics is a huge, thriving field. But look at where its researchers
    actually publish, and a clear divide emerges. Research splits into two
    tight camps: hard sciences (materials, chemistry, physics) on one side,
    applied bio-engineering (biomaterials, biomedical devices) on the other.
    Ecology, conservation biology, environmental science &mdash; the
    disciplines that study how living systems <em>work</em> &mdash; are
    almost entirely absent from either.
</p>
<p class="s3-sub">
    Of the {CORPUS["decision_y"]:,} papers in the corpus, only
    <b>{WOS_NET["eco_absence"]["env_eng_papers"]:,}</b> are classified as
    <em>Engineering, Environmental</em> &mdash; the sole environmental
    discipline in the top&nbsp;25. Not a single pure Ecology, Conservation
    Biology, or Ecosystem Science category makes the list at all.
</p>
""", unsafe_allow_html=True)
st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

# ── discipline network — real data from wos_cooccurrence.json ────
# The number of visible nodes is adjustable; the network re-lays out
# deterministically for each value. 
# All positions are stable within a given _S3_TOP_N — no random
# seeds, no run-to-run drift.
_S3_TOP_N     = 12
_S3_PAR_COLOR = {"Replace": "rgba(168,116,14,0.90)",
                 "Enhance": "rgba(29,140,105,0.85)",
                 "Support": "rgba(46,124,184,0.88)"}
_S3_PAR_BORDER = {"Replace": "#A8740E", "Enhance": "#1D8C69", "Support": "#2E7CB8"}

# Filter to top-N nodes, then filter edges to those endpoints
_s3_nodes = WOS_NET["nodes"][:_S3_TOP_N]
_s3_node_names = {n["raw_name"] for n in _s3_nodes}
_s3_edges = [e for e in WOS_NET["edges"]
             if e["a"] in _s3_node_names and e["b"] in _s3_node_names]

# Cluster centres (hand-anchored — this is the "written down" part of the
# hybrid layout: clusters are placed by editorial decision; nodes within a
# cluster are placed by a deterministic circular arrangement).
_S3_CLUSTER_CENTRES = {
    "Hard-Sci":    (-0.9,  0.15),
    "Bio-Applied": ( 1.0,  0.15),
    "Applied-Eng": ( 0.00, -1.0),
}

# ── Deterministic circular layout within each cluster ───────────────
# Nodes in each cluster are sorted by paper count (largest first), then
# placed evenly on a circle around the cluster centre. Same _S3_TOP_N →
# same layout, every render, on every host.
import math as _math3
_s3_by_cluster = {}
for _n in _s3_nodes:
    _s3_by_cluster.setdefault(_n["cluster"], []).append(_n)
for _cluster in _s3_by_cluster:
    _s3_by_cluster[_cluster].sort(key=lambda n: n["n_papers"], reverse=True)

_s3_pos = {}
for _cluster, _members in _s3_by_cluster.items():
    _cx, _cy = _S3_CLUSTER_CENTRES[_cluster]
    _n_in = len(_members)
    _r_ring = 0.30 if _n_in <= 3 else 0.42
    _rot0 = -_math3.pi / 2  # first node sits at the top of its ring
    for _i, _m in enumerate(_members):
        if _n_in == 1:
            _s3_pos[_m["raw_name"]] = (_cx, _cy)
        else:
            _angle = 2 * _math3.pi * _i / _n_in + _rot0
            _s3_pos[_m["raw_name"]] = (_cx + _r_ring * _math3.cos(_angle),
                                        _cy + _r_ring * _math3.sin(_angle))

# ── Header + credibility + read-the-chart caption ─────────────────
st.markdown(
    f'<div class="chart-label">Top {len(_s3_nodes)} disciplines by publication volume &middot; biomimetics corpus</div>',
    unsafe_allow_html=True)
credibility_badge(has_real=True, has_sim=False)
# Build the paradigm-legend string from actually-present paradigms in top-N.
_s3_present_paradigms = {n["dominant_paradigm"] for n in _s3_nodes}
_s3_par_legend_bits = []
if "Replace" in _s3_present_paradigms:
    _s3_par_legend_bits.append('<span style="color:#A8740E;">replace</span>')
if "Enhance" in _s3_present_paradigms:
    _s3_par_legend_bits.append('<span style="color:#1D8C69;">enhance</span>')
if "Support" in _s3_present_paradigms:
    _s3_par_legend_bits.append('<span style="color:#2E7CB8;">support</span>')
_s3_par_legend = " / ".join(_s3_par_legend_bits)
st.markdown(f"""
<p class="chart-sub-label">
    Node size = paper count. Colour = dominant paradigm
    ({_s3_par_legend}). <b>Dashed</b> lines mark rare cross-cluster
    collaborations.
</p>
""", unsafe_allow_html=True)

# ── Figure ──────────────────────────────────────────────────────
_net3 = go.Figure()

# Cluster background zones — light tinted circles behind each family
_S3_CLUSTER_STYLE = {
    "Hard-Sci":    {"fill": "rgba(168,116,14,0.05)", "border": "rgba(168,116,14,0.18)",
                    "label": "HARD-SCI · materials, chemistry, physics", "label_color": "rgba(168,116,14,0.70)"},
    "Bio-Applied": {"fill": "rgba(29,140,105,0.05)", "border": "rgba(29,140,105,0.18)",
                    "label": "BIO-APPLIED · biology as engineering resource", "label_color": "rgba(29,140,105,0.70)"},
    "Applied-Eng": {"fill": "rgba(138,132,123,0.06)", "border": "rgba(138,132,123,0.20)",
                    "label": "APPLIED-ENG", "label_color": "rgba(107,102,94,0.75)"},
}
for _cluster, _members in _s3_by_cluster.items():
    _cx, _cy = _S3_CLUSTER_CENTRES[_cluster]
    _r_bg = 0.65 if len(_members) >= 4 else (0.52 if len(_members) >= 2 else 0.25)
    _style = _S3_CLUSTER_STYLE[_cluster]
    _net3.add_shape(type="circle",
                    x0=_cx - _r_bg, y0=_cy - _r_bg,
                    x1=_cx + _r_bg, y1=_cy + _r_bg,
                    fillcolor=_style["fill"],
                    line=dict(color=_style["border"], width=1, dash="dot"),
                    layer="below")
    _net3.add_annotation(x=_cx, y=_cy + _r_bg + 0.08,
                         text=_style["label"],
                         font=dict(size=10, color=_style["label_color"],
                                    family="Inter, sans-serif"),
                         showarrow=False)

# The absent-discipline annotation — this is what §3 is really about
_net3.add_annotation(
    x=0, y=0.75, xref="x", yref="y",
    text="<i>Ecology · Conservation Biology · Environmental Science</i><br>"
         "<span style='color:rgba(179,76,47,0.75)'>— not in the top 25 —</span>",
    font=dict(size=10, color="rgba(107,102,94,0.85)",
              family="Inter, sans-serif"),
    align="center", showarrow=False)

# Edge traces
# Solid for intra-cluster, dashed for cross-cluster. Both weight-scaled.
_max_cooccur = max((e["cooccur"] for e in _s3_edges), default=1)
for _e in _s3_edges:
    _x0, _y0 = _s3_pos[_e["a"]]
    _x1, _y1 = _s3_pos[_e["b"]]
    _w_norm = _e["cooccur"] / _max_cooccur   # 0-1
    if _e["cross"]:
        _dash = "dash"; _op = 0.28; _wd = 1.0
    else:
        _dash = "solid"
        _op = max(0.10, _w_norm * 0.38)
        _wd = max(0.7, _w_norm * 2.8)
    _net3.add_trace(go.Scatter(
        x=[_x0, _x1, None], y=[_y0, _y1, None], mode="lines",
        line=dict(width=_wd, color=f"rgba(42,39,34,{_op:.2f})", dash=_dash),
        hoverinfo="skip", showlegend=False))

# Node size scaling: sqrt of paper count so extremes don't dominate
_max_papers = max((n["n_papers"] for n in _s3_nodes), default=1)
def _s3_node_size(n_papers):
    return 22 + 60 * (n_papers / _max_papers) ** 0.5

# One trace per paradigm so the legend shows R/E/S
for _par3 in ["Replace", "Enhance", "Support"]:
    _nx, _ny, _nsz, _nlbl, _nhtxt, _ntpos = [], [], [], [], [], []
    for _node in _s3_nodes:
        if _node["dominant_paradigm"] != _par3:
            continue
        _x, _y = _s3_pos[_node["raw_name"]]
        _nx.append(_x); _ny.append(_y)
        _nsz.append(_s3_node_size(_node["n_papers"]))
        _nlbl.append(_node["display"])
		# Text position: put label on the outside of the ring, away from cluster centre
        _cx, _cy = _S3_CLUSTER_CENTRES[_node["cluster"]]
        _dx, _dy = _x - _cx, _y - _cy
        if abs(_dx) > abs(_dy):
            _ntpos.append("middle right" if _dx > 0 else "middle left")
        else:
            _ntpos.append("bottom center" if _dy < 0 else "top center")
        _nhtxt.append(
            f"<b>{_node['display']}</b><br>"
            f"{_node['n_papers']:,} papers · cluster: {_node['cluster']}<br>"
            f"Replace {_node['replace_pct']*100:.0f}% · "
            f"Enhance {_node['enhance_pct']*100:.0f}% · "
            f"Support {_node['support_pct']*100:.0f}%"
        )
    _net3.add_trace(go.Scatter(
        x=_nx, y=_ny, mode="markers+text", name=_par3,
        text=_nlbl, textposition=_ntpos,
        textfont=dict(size=10, color="#4A453E", family="Inter, sans-serif"),
        hoverinfo="text", hovertext=_nhtxt,
        marker=dict(size=_nsz, color=_S3_PAR_COLOR[_par3],
                    line=dict(width=1.5, color="#FFFFFF"))))

_net3.update_layout(
    paper_bgcolor="#FFFFFF", plot_bgcolor="#FBF9F5",
    height=600, margin=dict(l=20, r=20, t=20, b=20), showlegend=True,
    legend=dict(orientation="h", y=-0.04, x=0.5, xanchor="center",
                font=dict(size=11, color="#6B665E", family="Inter, sans-serif"),
                bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)"),
    hovermode="closest",
    hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#E5E1DA",
                    font=dict(size=11, color="#2A2722", family="Inter, sans-serif")),
    xaxis=dict(visible=False, range=[-1.85, 1.85]),
    yaxis=dict(visible=False, range=[-1.60, 1.10]))
st.plotly_chart(_net3, use_container_width=True, config={"displayModeBar": False})

st.markdown(f"""
<div style="margin-top:1rem; padding: 1rem 1.2rem 1rem 1.5rem;
            border-left: 3px solid #B34C2F; background: transparent;">
    <div style="font: 500 .62rem/1 'Inter',sans-serif; letter-spacing:.14em;
                color:#8A847B; margin-bottom:.5rem;">KEY INSIGHT</div>
    <div style="font: 300 .82rem/1.65 'Inter',sans-serif; color:#2A2722;">
        The gap in <b>what</b> biomimetics builds mirrors a
        gap in <b>who</b> builds it. This field mines nature for <em>parts</em>
        &mdash; molecules, structures, materials &mdash; but not for
        <em>principles</em>. The disciplines that study how ecosystems
        sustain themselves aren&rsquo;t at the table.
    </div>
</div>
""", unsafe_allow_html=True)


# ── RoboBee case study — a example of §3's finding ──────────
st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
st.markdown('<div class="chart-label">Case study — RoboBee</div>', unsafe_allow_html=True)
# This case is drawn directly from Jacobs et al. (2025) — not from a corpus
# query. The paper uses RoboBees as its central worked example; we surface
# that example here to make the finding concrete.

credibility_badge(has_real=True, has_sim=True)
components.html("""
<!DOCTYPE html><html><head>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=Inter:wght@300;400;500;600&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: transparent; font-family: 'Inter', sans-serif; color: #2A2722; }
  .case-wrapper { background: #FFFFFF; border: 1px solid #E5E1DA; border-radius: 12px;
                  padding: 1.6rem 1.8rem; box-shadow: 0 1px 3px rgba(42,39,34,.04); }
  .case-header { font-family: 'Playfair Display', serif; font-size: 1.35rem; font-weight: 700;
                 color: #2A2722; margin-bottom: .3rem; }
  .case-meta { font-size: .7rem; font-weight: 300; color: #8A847B; margin-bottom: 1.4rem;
               letter-spacing: .08em; text-transform: uppercase; }
  .case-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px; margin-bottom: 1.2rem; }
  .case-col { background: #FBF9F5; border: 1px solid #E5E1DA; border-radius: 8px; padding: 1.2rem 1.1rem; }
  .case-col.col-eng { border-top: 2px solid rgba(168,116,14,0.60); }
  .case-col.col-eco { border-top: 2px solid rgba(179,76,47,0.60); }
  .case-col-title { font-size: .68rem; font-weight: 500; letter-spacing: .14em;
                    text-transform: uppercase; margin-bottom: .8rem; }
  .col-eng .case-col-title { color: #8A5E0B; }
  .col-eco .case-col-title { color: #A34528; }
  ul { padding-left: 1.1rem; list-style: disc; }
  ul li { font-size: .76rem; font-weight: 300; line-height: 1.75; color: #6B665E; margin-bottom: .2rem; }
  ul li b { color: #2A2722; font-weight: 500; }
  ul li em { color: #A34528; font-style: italic; }
  .case-tie { font-size: .8rem; font-weight: 300; line-height: 1.75; color: #4A453E;
              margin-bottom: 1rem; padding: 0 .2rem; }
  .case-tie em { font-style: italic; color: #6B665E; }
  .case-tie b { font-weight: 500; color: #2A2722; }
  .case-footer { font-size: .78rem; font-weight: 300; font-style: italic; line-height: 1.7;
                 color: #8A847B; border-top: 1px solid #E5E1DA; padding-top: 1rem; }
</style></head><body>
<div class="case-wrapper">
  <div class="case-header">The Incomplete Invention</div>
  <div class="case-meta">Harvard Microrobotics Lab &middot; 2013 &ndash; present</div>
  <div class="case-grid">
    <div class="case-col col-eng">
      <div class="case-col-title">What RoboBee achieves</div>
      <ul>
        <li>Insect-scale flapping-wing flight</li>
        <li>Autonomous crop pollination in lab conditions</li>
        <li>Millimetre-scale actuator design</li>
        <li>Swarm coordination protocols</li>
        <li><b>Status:</b> a landmark biomimetic achievement</li>
      </ul>
    </div>
    <div class="case-col col-eco">
      <div class="case-col-title">What a live bee also does</div>
      <ul>
        <li>Feeds insectivores &mdash; birds, bats, spiders, other bees</li>
        <li>Produces wax, propolis, honey &mdash; substrates for other species</li>
        <li>Aerates soil through burrowing behaviour</li>
        <li>Acts as an <em>indicator</em> of ecosystem health</li>
        <li>Carries cultural and spiritual meaning across most human societies</li>
      </ul>
    </div>
  </div>
  <div class="case-tie">
    RoboBees are the perfect illustration of the finding above. The project
    lives in the same clusters that dominate the network chart &mdash;
    materials science, robotics, biomedical engineering. It doesn&rsquo;t
    live in ecology, or in the study of what a bee actually is to the
    ecosystem around it. This isn&rsquo;t a criticism of an extraordinary
    piece of engineering. It&rsquo;s a reminder that when a whole set of
    disciplines isn&rsquo;t at the table, the resulting invention can only
    ever be part of the answer.
  </div>
  <div class="case-footer">
    &ldquo;RoboBees technology meets the engineering requirements to achieve the biological function of
    pollination, but not the complex functionality of a living bee that provides other services,
    such as food production.&rdquo; &mdash;
    <a href="https://doi.org/10.3390/biomimetics10110784" target="_blank"
       style="color:#8A847B; text-decoration:underline;">Jacobs et al. (2025)</a>
  </div>
</div>
</body></html>
""", height=480)

# ── Framing analysis diverging bar — real abstract vocabulary ──────
st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
st.markdown('<div class="chart-label">Framing analysis · abstract vocabulary</div>',
            unsafe_allow_html=True)
credibility_badge(has_real=True, has_sim=False)
st.markdown("""
<p class="chart-sub-label">
    Word frequency in the Replace-oriented subcorpus (left, amber)
    vs. the Support-oriented subcorpus (right, blue), per 1,000 abstracts.
    Terms are drawn from a full scan of 17,242 Replace and 980 Support
    abstracts.
</p>
""", unsafe_allow_html=True)

# Build the dataframe from real framing.json data. Support-leaning terms
# sort first (largest support_per_1k first), Replace-leaning terms follow
# (largest replace_per_1k first) — preserving a top-to-bottom "staircase"
# within each group.
_support_words = sorted(
    [w for w in FRAMING["words"] if w["side"] == "Support"],
    key=lambda w: w["support_per_1k"], reverse=True)
_replace_words = sorted(
    [w for w in FRAMING["words"] if w["side"] == "Replace"],
    key=lambda w: w["replace_per_1k"], reverse=True)
_framing_ordered = _support_words + _replace_words

_FRAMING3 = pd.DataFrame({
    "term": [w["display"].title() for w in _framing_ordered],
    "replace_freq": [-w["replace_per_1k"] for w in _framing_ordered],
    "support_freq": [w["support_per_1k"] for w in _framing_ordered],
})

_frame3 = go.Figure()
_frame3.add_trace(go.Bar(y=_FRAMING3["term"], x=_FRAMING3["replace_freq"], orientation="h",
    name="Replace subcorpus",
    marker=dict(color="rgba(168,116,14,0.75)", line=dict(width=0)),
    hovertemplate="Replace: <b>%{customdata:.1f}</b> / 1,000<extra></extra>",
    customdata=_FRAMING3["replace_freq"].abs()))
_frame3.add_trace(go.Bar(y=_FRAMING3["term"], x=_FRAMING3["support_freq"], orientation="h",
    name="Support subcorpus",
    marker=dict(color="rgba(46,124,184,0.78)", line=dict(width=0)),
    hovertemplate="Support: <b>%{x:.1f}</b> / 1,000<extra></extra>"))
_frame3.add_vline(x=0, line_color="rgba(42,39,34,0.25)", line_width=1)
_frame3.add_annotation(x=-20, y=1.04, yref="paper", text="← Replace-leaning vocabulary",
    font=dict(size=9, color="rgba(168,116,14,0.70)", family="Inter, sans-serif"),
    showarrow=False, xanchor="right")
_frame3.add_annotation(x=20, y=1.04, yref="paper", text="Support-leaning vocabulary →",
    font=dict(size=9, color="rgba(46,124,184,0.70)", family="Inter, sans-serif"),
    showarrow=False, xanchor="left")
_frame3.update_layout(
    barmode="relative", paper_bgcolor="#FFFFFF", plot_bgcolor="#FBF9F5",
    height=520, margin=dict(l=10, r=20, t=30, b=55), hovermode="y unified",
    hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#E5E1DA",
                    font=dict(size=11, color="#2A2722", family="Inter, sans-serif")),
    legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center",
                font=dict(size=11, color="#6B665E", family="Inter, sans-serif"),
                bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)"),
    xaxis=dict(title=dict(text="Occurrences per 1,000 abstracts",
                          font=dict(size=11, color="#8A847B")),
               range=[-45, 82],
               tickfont=dict(size=11, color="#8A847B"),
               tickvals=[-40,-20,0,20,40,60,80], ticktext=["40","20","0","20","40","60","80"],
               gridcolor="#ECE8E1", linecolor="#E5E1DA", zeroline=False),
    yaxis=dict(tickfont=dict(size=11, color="#6B665E", family="Inter, sans-serif"),
               autorange="reversed", linecolor="#E5E1DA", gridcolor="rgba(0,0,0,0)"))
st.plotly_chart(_frame3, use_container_width=True, config={"displayModeBar": False})

# The finding worth flagging: Support-leaning vocabulary isn't ecological
# language. It's biomimetic-surface and fluid-dynamics language. 

st.markdown(f"""
<div style="margin-top:1rem; padding: 1rem 1.2rem 1rem 1.5rem;
            border-left: 3px solid #B34C2F; background: transparent;">
    <div style="font: 500 .62rem/1 'Inter',sans-serif; letter-spacing:.14em;
                color:#8A847B; margin-bottom:.5rem;">KEY INSIGHT</div>
    <div style="font: 300 .82rem/1.65 'Inter',sans-serif; color:#2A2722;">
        Even in the Support subcorpus, the language isn't ecological &mdash; it's <b>drag reduction</b>, <b>shark skin</b>,
        <b>topography</b>: biomimetic surfaces and fluid dynamics, not
        ecosystems. Only two of the eight Support-leaning terms
        (<em>sustainability</em>, <em>ecological</em>) gesture toward ecology
        at all. The vocabulary confirms what the network above shows: the 3%
        that lean Support still speak engineering, not ecology.
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<p style="font:300 .68rem/1.7 'Inter',sans-serif;color:#B8B0A4;margin-top:.4rem;padding-left:2px;">
    Word frequencies computed from 18,222 of 19,269 Replace + Support abstracts
    (95% coverage &mdash; the rest lack an abstract in the corpus).
    <a href="/explorer?paradigm=Replace,Support" target="_blank" style="color:#356B49;font-weight:500;">Explore the Data ↗</a>
</p>
""", unsafe_allow_html=True)


# ═══════════════════════════════
# SECTION 4 · What 3% Teaches Us  
# ═══════════════════════════════
# section_sep()
st.markdown('<div id="sec-3pct" class="sec-anchor"></div>', unsafe_allow_html=True)
st.markdown('<div class="s4-eyebrow">Section 04 · What 3% Teaches Us</div>', unsafe_allow_html=True)
st.markdown('<h2 class="s4-title">Imagining a Different Possibility.</h2>', unsafe_allow_html=True)
st.markdown("""
<p class="s4-sub">
    Three percent is a small number. But it represents something important:
    proof that another way of doing bio-inspired design is possible —
    one that works <em>with</em> natural systems rather than replacing them.
</p>
<p class="s4-sub">
    What would happen if the research community redirected even a fraction
    of its attention? And when these technologies do exist, who can
    actually access them?
</p>
""", unsafe_allow_html=True)
st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

# Build groups from live SVC_SUMMARY data.
_real_groups4     = _s4_target_groups()
_scenario_groups4 = _s4_scenario_groups(_real_groups4, 0.41, 0.39, 0.20)

def _paradigm_totals4(groups):
    return {"replace": sum(g["replace"] for g in groups),
            "enhance": sum(g["enhance"] for g in groups),
            "support": sum(g["support"] for g in groups)}

_real_tot4  = _paradigm_totals4(_real_groups4)
_scen_tot4  = _paradigm_totals4(_scenario_groups4)
_real_all4  = _real_tot4["replace"] + _real_tot4["enhance"] + _real_tot4["support"]
_scen_all4  = _scen_tot4["replace"] + _scen_tot4["enhance"] + _scen_tot4["support"]

def _fmt_pct4(v, total):
    return f"{v/total*100:.0f}%" if total else "—"

# Critical-support flow for the callout narrative
def _crit_support4(groups):
    for g in groups:
        if g["key"] == "critical":
            return g["support"]
    return 0
_real_crit_s4 = _crit_support4(_real_groups4)
_scen_crit_s4 = _crit_support4(_scenario_groups4)
_crit_growth4 = _scen_crit_s4 / _real_crit_s4 if _real_crit_s4 else 0

_SCENARIOS4 = {
    f"Current state  (Support = {_fmt_pct4(_real_tot4['support'], _real_all4)})": {
        "groups":  _real_groups4,
        "label_r": f"Replace  {_fmt_pct4(_real_tot4['replace'], _real_all4)}",
        "label_e": f"Enhance  {_fmt_pct4(_real_tot4['enhance'], _real_all4)}",
        "label_s": f"Support  {_fmt_pct4(_real_tot4['support'], _real_all4)}",
        "callout": (
            f"At <b>{_fmt_pct4(_real_tot4['support'], _real_all4)}</b>, "
            f"Support-oriented research sends only "
            f"<b>{_real_crit_s4:,} papers</b> to Critical Services — "
            f"the rarest, most foundational flows in the entire corpus."
        ),
    },
    f"Scenario  (Support = {_fmt_pct4(_scen_tot4['support'], _scen_all4)})": {
        "groups":  _scenario_groups4,
        "label_r": f"Replace  {_fmt_pct4(_scen_tot4['replace'], _scen_all4)}",
        "label_e": f"Enhance  {_fmt_pct4(_scen_tot4['enhance'], _scen_all4)}",
        "label_s": f"Support  {_fmt_pct4(_scen_tot4['support'], _scen_all4)}",
        "callout": (
            f"At <b>{_fmt_pct4(_scen_tot4['support'], _scen_all4)}</b>, "
            f"the flow to Critical Services would grow to "
            f"<b>{_scen_crit_s4:,} papers</b> — "
            f"a <b>{_crit_growth4:.1f}× increase</b> — while Replace research "
            f"still receives the majority."
        ),
    },
}
st.markdown('<div class="chart-label">A map of choices — where research attention flows</div>',
            unsafe_allow_html=True)
credibility_badge(has_real=True, has_sim=True)
st.markdown("""
<p class="chart-sub-label">
    The same total research effort, distributed differently.
    Toggle between the current state and a hypothetical scenario
    to see how the flow to Critical Services changes.
    The green link is the pathway that matters most.
</p>
""", unsafe_allow_html=True)
_scenario_key = st.radio(label="Select scenario", options=list(_SCENARIOS4.keys()),
                         horizontal=True, label_visibility="collapsed")
_sc4 = _SCENARIOS4[_scenario_key]
st.markdown(f'<div class="scenario-callout">{_sc4["callout"]}</div>', unsafe_allow_html=True)
_sankey4 = build_sankey(_sc4["groups"], _sc4["label_r"], _sc4["label_e"], _sc4["label_s"])
_sankey4.update_traces(
    textfont=dict(
        size=12, 
        color="#333333",   
        family="Inter, sans-serif"
    )
)
_sankey4.update_layout(
    hoverlabel=dict(
        font=dict(size=13, color="#333333")
    )
)
st.plotly_chart(_sankey4, use_container_width=True, config={"displayModeBar": False})

# Global accessibility map 
st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
st.markdown('<div class="chart-label">Global reach — who can access replacement technologies?</div>',
            unsafe_allow_html=True)
credibility_badge(has_real=True, has_sim=False)

st.markdown("""
<div style="margin-bottom: 1rem;">
    <p style="font: 300 0.75rem 'Inter', sans-serif; color: #8A847B; margin: 0 0 0.8rem 0; letter-spacing: 0.02em;">
         <strong>Bubble size</strong> = volume of Replace papers &nbsp;&nbsp;|&nbsp;&nbsp; 
         <strong>Colour</strong> = open-access rate (green = free, red = paywalled)
    </p>
    <div style="background-color: #FAF8F5; border-left: 3px solid #A33216; padding: 0.8rem 1rem; border-radius: 4px;">
        <p style="font: 400 0.8rem/1.5 'Inter', sans-serif; color: #4A453F; margin: 0;">
            <strong style="color: #A33216; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.05em; display: block; margin-bottom: 0.2rem;">Key Observation</strong>
            Despite spanning the Global North/South divide, the world's leading producers of replacement technologies exhibit a shared pattern of low open-access rates, demonstrating that knowledge restriction in high-value paradigms transcends geopolitical categories.
        </p>
    </div>
</div>
""", unsafe_allow_html=True)

# country × open-access data from country_oa.json
_MAP_DATA4 = pd.DataFrame(COUNTRY_OA["countries"]).rename(columns={
    "country":         "Country",
    "region":          "Region",
    "replace_papers":  "Replace_Papers",
    "open_access_pct": "Open_Access_Pct",
})

_map4 = px.scatter_geo(
    _MAP_DATA4, locations="Country", locationmode="country names",
    size="Replace_Papers", color="Open_Access_Pct", hover_name="Country",
    hover_data={"Country": False, "Region": True, "Replace_Papers": True, "Open_Access_Pct": ":.0f"},
    color_continuous_scale=[[0.0,"#A33216"],[0.35,"#C2742F"],[0.65,"#5A9C6E"],[1.0,"#3D7A52"]],
    range_color=[15,100], color_continuous_midpoint=50, size_max=48,
    labels={"Open_Access_Pct": "Open Access %"})
_map4.update_geos(showcountries=True, countrycolor="rgba(218,213,204,0.9)",
    showcoastlines=True, coastlinecolor="rgba(206,200,189,0.8)",
    showland=True, landcolor="#EFEBE4", showocean=True, oceancolor="#F7F5F1",
    showframe=False, projection_type="natural earth")
_map4.update_layout(paper_bgcolor="#FFFFFF", geo_bgcolor="#FFFFFF",
    height=440, margin=dict(r=0, t=10, l=0, b=0),
    coloraxis_colorbar=dict(title=dict(text="Open Access %", font=dict(size=11, color="#8A847B")),
        tickfont=dict(size=10, color="#8A847B"), ticksuffix="%", thickness=12, len=0.6,
        bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)"),
    hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#E5E1DA",
                    font=dict(size=11, color="#2A2722", family="Inter, sans-serif")))
st.plotly_chart(_map4, use_container_width=True, config={"displayModeBar": False})

# ── 3% Spotlight — CAROUSEL ──
st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
st.markdown('<div class="chart-label">The 3% — technologies that chose to support</div>',
            unsafe_allow_html=True)

_SPOTLIGHT4 = [
    {"title":"Living Shoreline Systems","service":"Coastline Regulation · Supporting","n":"~10",
     "link":"/explorer?paradigm=Support&service=Coastline%20Regulation",
     "body":"Bio-inspired breakwater structures modelled on oyster reef geometry to dissipate wave energy "
            "while providing substrate for marine organisms. Unlike concrete seawalls, these structures "
            "<em>support</em> the colonisation and growth of natural reef communities over time — the "
            "technology becomes more effective as nature reclaims it."},
    {"title":"Mycorrhizal Network Inoculants","service":"Primary Production · Supporting","n":"~11",
     "link":"/explorer?paradigm=Support&service=Primary%20Production",
     "body":"Fungal network-inspired soil amendments that enhance plant nutrient uptake by inoculating "
            "degraded soils with mycorrhizal consortia. Rather than replacing soil biology, this approach "
            "<em>reactivates</em> dormant underground networks — using the wood-wide web's own logic to "
            "restore carbon sequestration in post-industrial landscapes."},
    {"title":"Pollinator Corridor Mapping","service":"Pollination · Supporting","n":"~14",
     "link":"/explorer?paradigm=Support&service=Pollination",
     "body":"Landscape connectivity models derived from bee foraging algorithms to design habitat corridors "
            "that <em>support</em> existing pollinator populations across fragmented agricultural land. "
            "Unlike RoboBees, this technology asks not how to replace bees — but how to make the landscape "
            "legible to them again."},
    {"title":"Beaver-Inspired Wetland Restoration","service":"Water Regulation · Supporting","n":"~39",
     "link":"/explorer?paradigm=Support&service=Water%20Regulation",
     "body":"Low-cost structures modelled on beaver dam geometry to slow water flow, raise water tables, and "
            "restore hydrological function in degraded stream systems. Where beaver populations are locally "
            "extinct, these structures <em>hold space</em> for recolonisation — designed to become redundant "
            "once the living engineer returns."},
]

_n_spot = len(_SPOTLIGHT4)
 
# Build slide blocks + dots from the data; 
_slides_html = ""

for _i, _c in enumerate(_SPOTLIGHT4):
    _hidden = "" if _i == 0 else "hidden"

    _slides_html += f"""
      <div class="mc-slide" {_hidden}>
        <div class="mc-head">
          <div>
            <div class="mc-title">{_c['title']}</div>
            <div class="mc-service">{_c['service']}</div>
          </div>
        </div>

        <div class="mc-body">{_c['body']}</div>

        <div class="mc-foot">
          <div class="mc-foot-left">
            <span class="mc-n">{_c['n']}</span>
            <span class="mc-n-label">papers in corpus</span>
          </div>

          <div class="mc-foot-center">
            <a class="mc-explore" href="{_c['link']}" target="_blank">
              Explore papers →
            </a>
          </div>

          <div class="mc-foot-right">
            <span class="mc-badge">Support</span>
          </div>
        </div>
      </div>
    """

_dots_html = "".join(
    f'<span class="mc-dot{" on" if _i == 0 else ""}></span>'
    for _i in range(_n_spot)
)
 
_carousel_html = """
<!DOCTYPE html><html><head>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=Inter:wght@300;400;500;600&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: transparent; font-family: 'Inter', sans-serif; }
  .mc-card {
    position: relative; background: #FFFFFF;
    border: 1px solid #E5E1DA; border-top: 2px solid rgba(61,122,82,0.5);
    border-radius: 12px; padding: 1.5rem 3.6rem 1.25rem;
    box-shadow: 0 1px 3px rgba(42,39,34,.04);
  }
  .mc-nav {
    position: absolute; top: 50%; transform: translateY(-50%);
    width: 36px; height: 36px; border-radius: 50%;
    border: 1px solid #E5E1DA; background: #FFFFFF; color: #8A847B;
    font: 400 1.2rem/1 'Inter', sans-serif; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 1px 2px rgba(42,39,34,.05);
    transition: border-color .18s, color .18s, background .18s;
  }
  .mc-nav:hover { border-color: rgba(61,122,82,0.55); color: #356B49; background: rgba(61,122,82,0.06); }
  .mc-nav:active { transform: translateY(-50%) scale(0.93); }
  .mc-prev { left: 12px; }
  .mc-next { right: 12px; }
  .mc-slides { min-height: 184px; }
  .mc-head { display: flex; align-items: flex-start; gap: 12px; margin-bottom: .85rem; }
  .mc-icon { font-size: 1.9rem; line-height: 1; flex-shrink: 0; }
  .mc-title { font: 700 1.1rem/1.25 'Playfair Display', serif; color: #2A2722; }
  .mc-service { font: 500 .62rem/1.4 'Inter', sans-serif; letter-spacing: .14em;
                text-transform: uppercase; color: #356B49; margin-top: 3px; }
  .mc-body { font: 300 .82rem/1.75 'Inter', sans-serif; color: #6B665E; margin-bottom: 1rem; }
  .mc-body em { color: #356B49; font-style: italic; }
  .mc-foot { display: flex; justify-content: space-between; align-items: center;
             padding-top: .8rem; border-top: 1px solid #E5E1DA; }
  .mc-foot-left, .mc-foot-center, .mc-foot-right {flex: 1; display: flex; align-items: center;}           
  .mc-foot-left { justify-content: flex-start; }
  .mc-foot-center { justify-content: center; }
  .mc-foot-right { justify-content: flex-end; }
  .mc-n { font: 700 1.3rem/1 'Playfair Display', serif; color: #2E7CB8; }
  .mc-n-label { font: 300 .62rem/1 'Inter', sans-serif; color: #8A847B; margin-left: 6px; }
  .mc-badge { font: 500 .62rem/1 'Inter', sans-serif; letter-spacing: .12em; text-transform: uppercase;
              padding: 3px 9px; border-radius: 20px; background: rgba(46,124,184,0.10);
              color: #246592; border: 1px solid rgba(46,124,184,0.22); }
    .mc-explore {
    font: 500 .68rem/1 'Inter', sans-serif; 
    color: #2E7CB8;                        
    text-decoration: none;                 
    transition: color .18s;                
    display: inline-block;
  }
  .mc-explore:hover {
    color: #1b5380;                         
    text-decoration: underline;            
  }
  .mc-dots { text-align: center; margin-top: 1rem; }
  .mc-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
            margin: 0 4px; background: #DAD5CC; transition: background .18s; }
  .mc-dot.on { background: #3D7A52; }
  .mc-counter { text-align: center; font: 300 .66rem/1 'Inter', sans-serif;
                color: #9A938A; margin-top: .6rem; }
</style></head><body>
<div class="mc-card">
  <button class="mc-nav mc-prev" onclick="mcMove(-1)" aria-label="Previous">&lsaquo;</button>
  <button class="mc-nav mc-next" onclick="mcMove(1)" aria-label="Next">&rsaquo;</button>
  <div class="mc-slides">__SLIDES__</div>
  <div class="mc-dots">__DOTS__</div>
  <div class="mc-counter"><span id="mcCur">1</span> of __N__ &nbsp;</div>
</div>
<script>
  var mcI = 0;
  var mcSlides = document.querySelectorAll('.mc-slide');
  var mcDots = document.querySelectorAll('.mc-dot');
  function mcRender() {
    for (var j = 0; j < mcSlides.length; j++) { mcSlides[j].hidden = (j !== mcI); }
    for (var k = 0; k < mcDots.length; k++) { mcDots[k].className = 'mc-dot' + (k === mcI ? ' on' : ''); }
    document.getElementById('mcCur').textContent = (mcI + 1);
  }
  function mcMove(d) { mcI = (mcI + d + mcSlides.length) % mcSlides.length; mcRender(); }
  mcRender();
</script>
</body></html>
"""
_carousel_html = (_carousel_html
                  .replace("__SLIDES__", _slides_html)
                  .replace("__DOTS__", _dots_html)
                  .replace("__N__", str(_n_spot)))
components.html(_carousel_html, height=320)



# ════════════════════════════════════════════════════════════════
# SECTION 5 · You Belong Here  
# ════════════════════════════════════════════════════════════════
# section_sep()
st.markdown('<div id="sec-belong" class="sec-anchor"></div>', unsafe_allow_html=True)
st.markdown('<div class="eyebrow">Section 05 · You Belong Here</div>', unsafe_allow_html=True)

st.markdown("""
<div class="quote-wrap">
    <span class="quote-mark">&ldquo;</span>
    <p class="quote-text">
        Some can be mimicked. Very few can be entirely replaced.
        None should be rendered optional.
    </p>
    <span class="quote-source">Jacobs et al. (2025) · Biomimetics 10, 784</span>
    <p class="turn-text">
        This is not a story about what is missing. It is a story about what is possible — and <em>it starts with you.</em>
    </p>
</div>
""", unsafe_allow_html=True)
st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

_all_svc_flat5 = [s for cat in SERVICES.values() for s in cat["items"]]
_selected5 = [s for s in _all_svc_flat5 if st.session_state.get(s["name"], False)]
_gap5 = [s for s in _selected5 if s["papers"] < RESEARCH_GAP_THRESHOLD]
_n_sel5 = len(_selected5); _n_gap5 = len(_gap5)
if _n_sel5 == 0:
    _echo_n = "10"
    _echo_body = "of the 22 services nature provides have fewer than 500 bio-inspired research papers."
    _echo_sub = ("That is not a gap. That is an open invitation.")
    
elif _n_gap5 == 0:
    _echo_n = str(_n_sel5)
    _echo_body = ("services you said you depend on — all relatively well-studied. "
                  "But most people's selections aren't.")
    _echo_sub = "10 of the 22 services have fewer than 500 papers."
    
else:
    _gap_names5 = ", ".join(f"<em>{s['name']}</em>" for s in _gap5[:3])
    _more5 = f" and {_n_gap5 - 3} more" if _n_gap5 > 3 else ""
    _echo_n = str(_n_gap5)
    _echo_body = (f"of the {_n_sel5} services you said you depend on "
                  f"have fewer than 500 bio-inspired research papers — "
                  f"including {_gap_names5}{_more5}.")
    _echo_sub = ("That gap has your name on it.")
    
st.markdown(f"""
<div class="echo-wrap">
    <span class="echo-n">{_echo_n}</span>
    <p class="echo-label">{_echo_body}</p>
    <p class="echo-sub">{_echo_sub}</p>
</div>
""", unsafe_allow_html=True)
st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

st.markdown('<div class="chart-label">Who are you in this story?</div>', unsafe_allow_html=True)
st.markdown("""
<p style="font:300 .82rem/1.6 'Inter',sans-serif;color:#6B665E;max-width:520px;margin-bottom:1rem;">
    Select the role that feels closest to you.
    We have something to say to each of you.
</p>
""", unsafe_allow_html=True)
_IDENTITIES5 = [
    ("Researcher\n/ Scientist", "researcher"),
    ("Designer\n/ Engineer", "designer"),
    ("Policymaker\n/ Funder", "policymaker"),
    ("Artist\n/ Writer", "artist"),
    ("Educator\n/ Student", "educator"),
    ("Curious\nHuman", "human"),
]
_cols5 = st.columns(6)
for _col5, (_lbl5, _key5) in zip(_cols5, _IDENTITIES5):
    with _col5:
        if st.button(_lbl5, key=f"id_{_key5}", use_container_width=True):
            st.session_state.identity = _key5
_RESPONSES5 = {
    "researcher": {
        "title": "The map has your name on it.",
        "body": ("Pollination: <b>355 papers.</b> Nutrient cycling: <b>58.</b> "
                 "Soil formation: <b>343.</b> These are the foundations of global food security — "
                 "and among the least-published areas in the entire bio-inspired corpus.<br><br>"
                 "<em>Your next paper, your next grant, your next collaboration across "
                 "a disciplinary boundary — that is how the map changes.</em>"),
    },
    "designer": {
        "title": "Nature is the best brief you have never been given.",
        "body": ("The dominant paradigm — Replace — produces things that can be patented and sold. "
                 "The Support paradigm produces things that work best when they disappear.<br><br>"
                 "<em>That is a harder, more interesting design problem. "
                 "And it is almost entirely unoccupied.</em>"),
    },
    "policymaker": {
        "title": "You hold the dial.",
        "body": ("Critical services have so few papers not because scientists don't care — "
                 "but because <b>funding flows toward what can be patented and sold.</b><br><br>"
                 "A single grant program focused on Support-oriented, openly-licensed "
                 "bio-inspired research could shift the entire distribution. "
                 "<em>The lever is small. The effect is large.</em>"),
    },
    "artist": {
        "title": "Imagination shapes what science thinks is possible.",
        "body": ("Your image, your sentence, your character who misses a river "
                 "that no longer runs — that is not separate from the data you have just seen. "
                 "<b>It is the data, felt from the inside.</b><br><br>"
                 "<em>The MEco Anthology is looking for writers. "
                 "The Exhibition is looking for artists.</em>"),
    },
    "educator": {
        "title": "The silos were built in classrooms. They can be taken down there too.",
        "body": ("The disciplinary isolation in Section 3 — "
                 "engineers on one island, ecologists on the other — "
                 "was not inevitable. It was constructed through curricula "
                 "that trained people to stay in their lanes.<br><br>"
                 "<em>A single course that asks an engineering student and an ecology student "
                 "to design something together — that course is already changing the map.</em>"),
    },
    "human": {
        "title": "You have already done the most important thing.",
        "body": ("You came here. You thought about which ecosystem services "
                 "you depend on before you had ever heard the phrase.<br><br>"
                 "That willingness to sit with the complexity, the gaps, the possibilities — "
                 "<em>that is the rarest thing in the world right now.</em> "
                 "Not expertise. Not funding. Not technology. Attention.<br><br>"
                 "<b>You belong in this conversation.</b> You always did."),
    },
}

if st.session_state.identity and st.session_state.identity in _RESPONSES5:
    _resp5 = _RESPONSES5[st.session_state.identity]
    
    st.markdown(f"""
    <div class="response-card">
        <div class="response-title">{_resp5["title"]}</div>
        <div class="response-body">{_resp5["body"]}</div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <p style="font:300 .8rem/1 'Inter',sans-serif;color:#B8B0A4;
              margin-top:.5rem;font-style:italic;">
        Select a role above to receive a personalised message.
    </p>
    """, unsafe_allow_html=True)

st.markdown('<div class="chart-label" style="margin-top: 3rem;">Where to go next</div>',
            unsafe_allow_html=True)
components.html("""
<!DOCTYPE html><html><head>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=Inter:wght@300;400;500&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: transparent; font-family: 'Inter', sans-serif; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
  .card { background: #FFFFFF; border: 1px solid #E5E1DA; border-radius: 10px; padding: 1.3rem 1.2rem; text-decoration: none; display: block; box-shadow: 0 1px 3px rgba(42,39,34,.04); transition: border-color .22s, background .22s, box-shadow .22s; }
  .card:hover { border-color: rgba(61,122,82,0.45); background: rgba(61,122,82,0.04); box-shadow: 0 3px 8px rgba(42,39,34,.07); }
  .card-icon { font-size: 1.4rem; display: block; margin-bottom: .6rem; }
  .card-title { font-family: 'Playfair Display', serif; font-size: .95rem; font-weight: 700; color: #2A2722; margin-bottom: .4rem; line-height: 1.25; }
  .card-desc { font-size: .74rem; font-weight: 300; color: #6B665E; line-height: 1.6; margin-bottom: .9rem; }
  .card-cta { font-size: .62rem; font-weight: 500; letter-spacing: .14em; text-transform: uppercase; color: #3D7A52; }
</style></head><body>
<div class="grid">
  <a class="card" href="https://doi.org/10.3390/biomimetics10110784" target="_blank">
    <div class="card-title">Read the research paper</div>
    <div class="card-desc">The peer-reviewed study behind every number on this page. Jacobs et al. (2025), <em>Biomimetics</em>, vol. 10, art. 784. Open access.</div>
    <div class="card-cta">Read the paper →</div>
  </a>
  <a class="card" href="https://www.manufacturedecosystems.com/home/learning-from-nature" target="_blank">
    <div class="card-title">Learning from Nature</div>
    <div class="card-desc">Go deeper into the four knowledge pillars — Nature, Technology, Imagination, and Each Other. A growing library of resources across disciplines.</div>
    <div class="card-cta">Start exploring →</div>
  </a>
  <a class="card" href="/explorer" target="_blank">
    <div class="card-title">Explore the data yourself</div>
    <div class="card-desc">Explore every paper yourself. Filter by service, paradigm, country, or technology to build your own lens.</div>
    <div class="card-cta">Open Data Explorer →</div>
  </a>  
</div>
</body></html>
""", height=280)

st.markdown("""
<div class="final-wrap">
    <span class="final-you">You</span>
    <span class="final-belong">Belong Here.</span>
    <a class="final-link" href="https://www.manufacturedecosystems.com" target="_blank">
        manufacturedecosystems.com
    </a>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br><br>", unsafe_allow_html=True)
