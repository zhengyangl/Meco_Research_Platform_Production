"""BioM Innovation Database."""

import io
import zipfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

DATA_DIR = Path(__file__).parent / "data" / "clean"

st.set_page_config(page_title="BioM Innovation Database", page_icon="🌿", layout="wide")

st.markdown("""
<style>
:root {
    --dark-green: #0A2E1F;
    --mid-green: #0F6E56;
    --teal: #1D9E75;
    --pale-teal: #E1F5EE;
    --off-white: #F7FAF8;
    --charcoal: #1E2D24;
    --slate: #4A6358;
    --muted: #8FA89C;
    --border: #DCE8E2;
    --amber: #D4870A;
}
.stApp { background: var(--off-white); }
#MainMenu, footer, header { visibility: hidden; }

.hero-box {
    background: var(--dark-green);
    padding: 26px 28px;
    border-radius: 14px;
    margin-bottom: 20px;
    position: relative;
}
.hero-box h1 { color: #fff; font-size: 24px; font-weight: 700; margin: 0 0 6px; }
.hero-box p { color: rgba(255,255,255,0.55); font-size: 13.5px; margin: 0; }
.hero-nav-placeholder { position: absolute; top: 26px; right: 28px; color: rgba(255,255,255,0.3); font-size: 12px; }

.section-title { font-size: 16px; font-weight: 700; color: var(--charcoal); margin: 18px 0 10px; }
.pill { display: inline-block; font-size: 11px; padding: 3px 10px; border-radius: 20px;
    background: var(--off-white); color: var(--slate); border: 1px solid var(--border); margin: 2px 4px 2px 0; }
.badge-teal { background: var(--pale-teal); color: var(--mid-green); padding: 2px 9px; border-radius: 20px; font-size: 11px; font-weight: 700; }
.badge-amber { background: #FAEEDA; color: #854F0B; padding: 2px 9px; border-radius: 20px; font-size: 11px; font-weight: 700; }
.badge-gray { background: #F1EFE8; color: #5F5E5A; padding: 2px 9px; border-radius: 20px; font-size: 11px; font-weight: 700; }
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_data():
    cases = pd.read_csv(DATA_DIR / "cases.csv")
    disciplines = pd.read_csv(DATA_DIR / "case_disciplines.csv")
    keywords = pd.read_csv(DATA_DIR / "case_keywords.csv")
    patents = pd.read_csv(DATA_DIR / "case_patents.csv")
    services = pd.read_csv(DATA_DIR / "case_ecosystem_services.csv")
    return cases, disciplines, keywords, patents, services


cases_all, disciplines_all, keywords_all, patents_all, services_all = load_data()

KINGDOM_COLORS = {
    "Animalia": "#B8935F", "Plantae": "#5DAA6E", "Fungi": "#9B6BA8",
    "Protista": "#4A90B8", "Monera": "#C4626E",
}

# ════════════════════════════════════════════════════════════════
# STATE
# ════════════════════════════════════════════════════════════════
for key, default in [
    ("search", ""), ("f_kingdom", []), ("f_phase", []), ("f_continent", []),
    ("f_discipline", []), ("f_service", []), ("f_year_range", None),
    ("_open_case", None), ("year_field_choice", "Concept Year"),
]:
    if key not in st.session_state:
        st.session_state[key] = default

_year_min = int(cases_all["Concept Year_year"].min(skipna=True)) if cases_all["Concept Year_year"].notna().any() else 1970
_year_max = int(cases_all["Concept Year_year"].max(skipna=True)) if cases_all["Concept Year_year"].notna().any() else 2025
if st.session_state.f_year_range is None:
    st.session_state.f_year_range = (_year_min, _year_max)


def clear_filters():
    st.session_state.search = ""
    st.session_state.f_kingdom = []
    st.session_state.f_phase = []
    st.session_state.f_continent = []
    st.session_state.f_discipline = []
    st.session_state.f_service = []
    st.session_state.f_year_range = (_year_min, _year_max)


# ════════════════════════════════════════════════════════════════
# CROSS-TABLE FILTERING
# ════════════════════════════════════════════════════════════════
def case_ids_matching(child_df: pd.DataFrame, value_col: str, selected: list) -> set:
    if not selected:
        return None
    return set(child_df.loc[child_df[value_col].isin(selected), "case_id"])


def intersect(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return a & b


def get_filtered_cases() -> pd.DataFrame:
    df = cases_all

    allowed_ids = None
    allowed_ids = intersect(allowed_ids, case_ids_matching(disciplines_all, "discipline", st.session_state.f_discipline))
    allowed_ids = intersect(allowed_ids, case_ids_matching(services_all, "ecosystem_service", st.session_state.f_service))
    if allowed_ids is not None:
        df = df[df["case_id"].isin(allowed_ids)]

    if st.session_state.f_kingdom:
        df = df[df["Kingdom"].isin(st.session_state.f_kingdom)]
    if st.session_state.f_phase:
        df = df[df["Product Phase"].isin(st.session_state.f_phase)]
    if st.session_state.f_continent:
        df = df[df["Continent"].isin(st.session_state.f_continent)]

    y_lo, y_hi = st.session_state.f_year_range
    df = df[df["Concept Year_year"].isna() | df["Concept Year_year"].between(y_lo, y_hi)]

    s = st.session_state.search.strip().lower()
    if s:
        search_cols = ["display_name", "Mimic", "Product Description", "Company or Institution Name", "Country"]
        haystack = df[search_cols].fillna("").agg(" ".join, axis=1).str.lower()
        df = df[haystack.str.contains(s, regex=False)]

    return df


# ════════════════════════════════════════════════════════════════
# HERO + SEARCH + FILTERS
# ════════════════════════════════════════════════════════════════
st.markdown(
    f'<div class="hero-box"><span class="hero-nav-placeholder">Research Tools ↗ (coming soon)</span>'
    f'<h1>BioM Innovation Database</h1>'
    f'<p>{len(cases_all):,} verified biomimetic innovation cases — explore products and research '
    f'that transfer solutions from biology into engineered systems.</p>'
    f'<p style="margin-top:8px;">Each case links a commercial or research product to the biological '
    f'organism or process it draws from, classified by kingdom, biological organization level, and '
    f'the type of biomimicry involved (form, function, process, or interaction). Filter by discipline, '
    f'ecosystem service, region, or timeframe below, or search directly.</p></div>',
    unsafe_allow_html=True,
)

_search_col, _clear_col = st.columns([5, 1])
with _search_col:
    st.text_input("Search", key="search", placeholder="Search by product, organism, keyword, institution…",
                   label_visibility="collapsed")
with _clear_col:
    st.button("Clear filters", on_click=clear_filters, use_container_width=True)

with st.sidebar:
    st.markdown("### Filters")
    with st.expander("Classification", expanded=True):
        st.multiselect("Kingdom", sorted(cases_all["Kingdom"].dropna().unique()), key="f_kingdom")
        st.multiselect("Product Phase", sorted(cases_all["Product Phase"].dropna().unique()), key="f_phase")
        st.multiselect("Continent", sorted(cases_all["Continent"].dropna().unique()), key="f_continent")
    with st.expander("Discipline & Ecosystem Service", expanded=False):
        st.multiselect("Discipline", sorted(disciplines_all["discipline"].dropna().unique()), key="f_discipline")
        st.multiselect("Ecosystem Service", sorted(services_all["ecosystem_service"].dropna().unique()), key="f_service")
    with st.expander("Concept Year", expanded=False):
        st.slider("Range", min_value=_year_min, max_value=_year_max, key="f_year_range")

filtered = get_filtered_cases()

# ════════════════════════════════════════════════════════════════
# METRICS
# ════════════════════════════════════════════════════════════════
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total cases", f"{len(filtered):,}")
m2.metric("Commercial products", int((filtered["Product Phase"] == "Commercially Available").sum()))
m3.metric("Kingdoms represented", filtered["Kingdom"].nunique())
m4.metric("Countries", filtered["Country"].nunique())

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# TABLE + DOWNLOAD
# ════════════════════════════════════════════════════════════════
_table_header_col, _download_col = st.columns([5, 1])
with _table_header_col:
    st.markdown(f'<div class="section-title">Innovation Cases ({len(filtered):,} results)</div>', unsafe_allow_html=True)


def build_download_zip(filtered_df: pd.DataFrame) -> bytes:
    ids = set(filtered_df["case_id"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("cases.csv", filtered_df.to_csv(index=False))
        zf.writestr("case_disciplines.csv", disciplines_all[disciplines_all["case_id"].isin(ids)].to_csv(index=False))
        zf.writestr("case_keywords.csv", keywords_all[keywords_all["case_id"].isin(ids)].to_csv(index=False))
        zf.writestr("case_patents.csv", patents_all[patents_all["case_id"].isin(ids)].to_csv(index=False))
        zf.writestr("case_ecosystem_services.csv", services_all[services_all["case_id"].isin(ids)].to_csv(index=False))
    return buf.getvalue()


with _download_col:
    st.download_button(
        "⬇ Download (.zip)", data=build_download_zip(filtered),
        file_name="biom_export.zip", mime="application/zip", use_container_width=True,
    )

if filtered.empty:
    st.info("No cases match your filters.")
else:
    _CORE_COLS = ["case_id", "display_name", "Mimic", "Kingdom", "Product Phase",
                  "Company or Institution Name", "Continent", "Concept Year_year", "Commercial Year_year"]
    _HIDEABLE_COLS = {
        "Case Status": "Case Status",
        "Country": "Country",
        "Academia or Industry": "Academia / Industry",
        "Group": "Group",
        "Phylum": "Phylum",
        "biom_type_function": "BioM: Function",
        "biom_type_form": "BioM: Form",
        "biom_type_process": "BioM: Process",
        "biom_type_interaction": "BioM: Interaction",
        "Process Type": "Process Type",
    }
    _visible_extra = st.multiselect(
        "Show additional columns",
        options=list(_HIDEABLE_COLS.keys()),
        default=[],
        format_func=lambda x: _HIDEABLE_COLS[x],
    )

    # Default sort: rows with a real Product Name first, rows relying on
    # the display_name fallback (Mimic-derived or "Untitled case") last.
    # has_real_name must come from "Product Name" itself, not display_name
    # — display_name is never blank (it always holds either the real name
    # or a fallback), so it can't be used to tell the two cases apart.
    sort_df = filtered.copy()
    sort_df["_has_real_name"] = sort_df["Product Name"].notna()
    sort_df = sort_df.sort_values("_has_real_name", ascending=False)

    table_df = sort_df[_CORE_COLS + list(_HIDEABLE_COLS.keys())].rename(columns={
        "display_name": "Case", "Concept Year_year": "Concept Yr", "Commercial Year_year": "Commercial Yr",
    })

    # Matches Explorer's approach exactly: cellStyle returns a JS style
    # object, which ag-grid applies natively — cellRenderer returning an
    # HTML string does NOT get interpreted as HTML by default and shows
    # as literal text instead.
    phase_style = JsCode("""
    function(params) {
        if (params.value === 'Commercially Available') {
            return { 'color': '#0F6E56', 'backgroundColor': 'rgba(29, 158, 117, 0.12)', 'fontWeight': '600' };
        } else if (params.value === 'In Development') {
            return { 'color': '#854F0B', 'backgroundColor': 'rgba(212, 135, 10, 0.12)', 'fontWeight': '600' };
        }
        return { 'color': '#5F5E5A', 'backgroundColor': 'rgba(95, 94, 90, 0.08)', 'fontWeight': '500' };
    }
    """)

    _MIN_WIDTHS = {
        "case_id": 110, "Case": 220, "Mimic": 160, "Kingdom": 110,
        "Product Phase": 170, "Company or Institution Name": 200,
        "Continent": 130, "Concept Yr": 110, "Commercial Yr": 120,
    }
    _HEADER_LABELS = {"case_id": "case_id", "Company or Institution Name": "Institution", **_HIDEABLE_COLS}

    gb = GridOptionsBuilder.from_dataframe(table_df)
    gb.configure_selection("single", use_checkbox=False)
    # Matches Explorer's own pattern exactly: a single tooltipValueGetter
    # on the default column config shows the full cell value on hover for
    # every column, without needing tooltipField set individually on each
    # one. filter=False removes the per-column funnel icon — global search
    # + the sidebar filters are the primary filtering mechanism here, so
    # the per-column filter menu was redundant clutter, not lost capability.
    gb.configure_default_column(
        resizable=True, sortable=True, filter=False,
        tooltipValueGetter=JsCode("function(params) { return params.value; }"),
    )
    for col in table_df.columns:
        header_name = _HEADER_LABELS.get(col, col)
        gb.configure_column(
            col, header_name=header_name, headerTooltip=header_name,
            minWidth=_MIN_WIDTHS.get(col, 140), filter=False,
            hide=(col in _HIDEABLE_COLS and col not in _visible_extra),
        )
    gb.configure_column("Product Phase", cellStyle=phase_style)
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=20)
    grid_response = AgGrid(
        table_df, gridOptions=gb.build(), height=480, allow_unsafe_jscode=True,
        theme="alpine", update_on=["selectionChanged"], fit_columns_on_grid_load=False,
    )

    selected = grid_response.get("selected_rows")
    if selected is not None and len(selected):
        selected_case_id = int(selected.iloc[0]["case_id"]) if hasattr(selected, "iloc") else int(selected[0]["case_id"])
        st.session_state["_open_case"] = selected_case_id

# ════════════════════════════════════════════════════════════════
# VISUALIZATIONS — secondary, collapsed by default
# ════════════════════════════════════════════════════════════════
with st.expander("📊 Charts & trends"):
    viz1, viz2 = st.columns(2)

    with viz1:
        st.markdown('<div class="section-title">Cases by Ecosystem Service</div>', unsafe_allow_html=True)
        svc_filtered = services_all[services_all["case_id"].isin(filtered["case_id"])]
        if len(svc_filtered):
            counts = svc_filtered["ecosystem_service"].value_counts().sort_values()
            fig = px.bar(x=counts.values, y=counts.index, orientation="h",
                          labels={"x": "Cases", "y": ""}, height=420)
            fig.update_traces(marker_color="#1D9E75")
            fig.update_layout(margin=dict(l=0, r=10, t=10, b=10), plot_bgcolor="white")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No ecosystem-service data for the current filter.")

    with viz2:
        st.markdown('<div class="section-title">Kingdom × Product Phase</div>', unsafe_allow_html=True)
        if len(filtered):
            cross = filtered.groupby(["Product Phase", "Kingdom"]).size().reset_index(name="count")
            fig2 = px.bar(cross, x="Product Phase", y="count", color="Kingdom",
                           color_discrete_map=KINGDOM_COLORS, height=420)
            fig2.update_layout(margin=dict(l=0, r=10, t=10, b=10), plot_bgcolor="white", xaxis_title="")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.caption("No data for the current filter.")

    st.markdown('<div class="section-title">Annual Trend by Kingdom</div>', unsafe_allow_html=True)
    _yc1, _yc2 = st.columns([1, 5])
    with _yc1:
        st.radio("Year field", ["Concept Year", "Commercial Year"], key="year_field_choice", label_visibility="collapsed")
    year_col = f"{st.session_state.year_field_choice}_year"
    trend_df = filtered[filtered[year_col].notna()]
    if len(trend_df):
        trend = trend_df.groupby([year_col, "Kingdom"]).size().reset_index(name="count")
        fig3 = px.bar(trend, x=year_col, y="count", color="Kingdom",
                       color_discrete_map=KINGDOM_COLORS, height=360)
        fig3.update_layout(barmode="stack", margin=dict(l=0, r=10, t=10, b=10), plot_bgcolor="white",
                            xaxis_title="Year", yaxis_title="Cases")
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.caption(f"No cases with a known {st.session_state.year_field_choice} for the current filter.")

    st.markdown('<div class="section-title">Cases by Country</div>', unsafe_allow_html=True)
    if "country_iso3" not in filtered.columns:
        st.caption("Run geocode_countries.py on cases.csv to enable this map (adds country_iso3 / country_name_canonical).")
    else:
        geo_df = filtered[filtered["Country"].notna()].copy()
        unmapped = sorted(geo_df.loc[geo_df["country_iso3"].isna(), "Country"].unique().tolist())
        geo_df = geo_df.dropna(subset=["country_iso3"])

        if len(geo_df):
            # Group by country_iso3 ALONE — grouping by (iso3, Country) together
            # was the original bug: different raw spellings of the same country
            # (e.g. "USA" / "U.S.A.") produced separate rows here and silently
            # split that country's count across multiple map entries instead of
            # summing them. country_name_canonical (one fixed name per iso3,
            # from geocode_countries.py) is what the map hovers show instead.
            country_counts = (
                geo_df.groupby("country_iso3")
                .agg(count=("case_id", "size"), country_name_canonical=("country_name_canonical", "first"))
                .reset_index()
            )
            fig4 = px.choropleth(
                country_counts, locations="country_iso3", color="count", hover_name="country_name_canonical",
                color_continuous_scale=["#E1F5EE", "#1D9E75", "#0A2E1F"],
                height=440,
            )
            fig4.update_layout(margin=dict(l=0, r=0, t=10, b=0), geo=dict(bgcolor="rgba(0,0,0,0)"))
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.caption("No mappable country data for the current filter.")

        if unmapped:
            st.caption(f"⚠ {len(unmapped)} country value(s) have no geocode and are excluded above: {unmapped}. "
                       f"Re-run geocode_countries.py after checking these against COUNTRY_ALIASES.")

# ════════════════════════════════════════════════════════════════
# DETAIL DIALOG
# ════════════════════════════════════════════════════════════════
if st.session_state.get("_open_case") is not None:

    @st.dialog(" ", width="large")
    def show_detail(case_id: int):
        row = cases_all[cases_all["case_id"] == case_id].iloc[0]

        st.markdown(f"""
        <div style="background: var(--dark-green); margin: -1rem -1rem 1rem -1rem; padding: 22px 26px 18px; border-radius: 8px 8px 0 0;">
            <div style="color:#fff; font-size:19px; font-weight:700; margin-bottom:6px;">{row['display_name']}</div>
            <div style="color:#5DCAA5; font-size:12.5px;">{row.get('Mimic') or ''} · Case #{case_id}</div>
        </div>
        """, unsafe_allow_html=True)

        if pd.notna(row.get("Product Description")):
            st.markdown("**Description**")
            st.write(row["Product Description"])

        st.markdown("**Biological Classification**")
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Kingdom"); st.write(row.get("Kingdom") or "—")
            st.caption("Group"); st.write(row.get("Group") or "—")
            st.caption("Phylum"); st.write(row.get("Phylum") or "—")
        with c2:
            st.caption("Mimic System"); st.write(row.get("Mimic System") or "—")
            st.caption("Mimic Subsystem"); st.write(row.get("Mimic Subsystem") or "—")
            st.caption("Mimic Suprasystem"); st.write(row.get("Mimic Suprasystem") or "—")

        biom_tags = [t for t, present in [
            ("Function", row.get("biom_type_function")), ("Form", row.get("biom_type_form")),
            ("Process", row.get("biom_type_process")), ("Interaction", row.get("biom_type_interaction")),
        ] if present is True]
        if biom_tags:
            st.markdown("**BioM Type**")
            st.markdown("".join(f'<span class="pill">{t}</span>' for t in biom_tags), unsafe_allow_html=True)

        st.markdown("**Timeline**")
        for label, year_field in [("Concept", "Concept Year"), ("Prototype", "Prototype Year"), ("Commercial", "Commercial Year")]:
            year = row.get(f"{year_field}_year")
            qualifier = row.get(f"{year_field}_year_qualifier")
            raw = row.get(f"{year_field}_year_raw")
            if pd.notna(year):
                suffix = f" ({qualifier})" if pd.notna(qualifier) else ""
                st.caption(f"{label}: {int(year)}{suffix}" + (f" — as recorded: \"{raw}\"" if pd.notna(qualifier) and pd.notna(raw) else ""))

        svc = services_all[services_all["case_id"] == case_id]["ecosystem_service"].tolist()
        if svc:
            st.markdown("**Ecosystem Services**")
            st.markdown("".join(f'<span class="pill">{s}</span>' for s in svc), unsafe_allow_html=True)

        disc = disciplines_all[disciplines_all["case_id"] == case_id]["discipline"].tolist()
        kw = keywords_all[keywords_all["case_id"] == case_id]["keyword"].tolist()
        if disc or kw:
            st.markdown("**Disciplines & Keywords**")
            st.markdown("".join(f'<span class="pill">{d}</span>' for d in disc + kw), unsafe_allow_html=True)

        pat = patents_all[patents_all["case_id"] == case_id]
        if len(pat):
            st.markdown("**Patents**")
            pat_display = pat[["patent_year", "patent_number"]].copy()
            pat_display["patent_year"] = pat_display["patent_year"].astype("Int64")
            st.dataframe(pat_display, hide_index=True, use_container_width=True)

        st.markdown("**Origin**")
        c3, c4 = st.columns(2)
        with c3:
            st.caption("Institution"); st.write(row.get("Company or Institution Name") or "—")
            st.caption("Academia / Industry"); st.write(row.get("Academia or Industry") or "—")
        with c4:
            st.caption("Country"); st.write(row.get("Country") or "—")
            st.caption("Continent"); st.write(row.get("Continent") or "—")

        with st.expander("Linguistic Evidence"):
            st.caption("Word Category"); st.write(row.get("Word Category") or "—")

        if st.button("Close"):
            st.session_state["_open_case"] = None
            st.rerun()

    show_detail(st.session_state["_open_case"])
