"""BioM Innovation Database — dashboard over the cleaned 5-table dataset."""

import html
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
#MainMenu, footer { visibility: hidden; }

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

/* Tabs as bordered pills. Selectors verified against Streamlit 1.64's frontend
   bundle: the container is data-testid="stTabs" and each tab is a React Aria
   tab carrying the standard ARIA attributes role="tab" / aria-selected. */
[data-testid="stTabs"] [role="tab"] {
    border: 1px solid var(--border); border-radius: 8px; background: #FFFFFF;
    padding: 6px 20px; margin-right: 8px;
}
[data-testid="stTabs"] [role="tab"] p { font-size: 15px; font-weight: 600; color: var(--slate); }
[data-testid="stTabs"] [role="tab"]:hover { border-color: var(--teal); }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { background: var(--mid-green); border-color: var(--mid-green); }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] p { color: #FFFFFF; }
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

COMPARE_MIN, COMPARE_MAX = 2, 4
VERIFIED_STATUS = "Complete, with interview"

# ════════════════════════════════════════════════════════════════
# STATE
# ════════════════════════════════════════════════════════════════
for key, default in [
    ("search", ""), ("f_kingdom", []), ("f_phase", []), ("f_continent", []),
    ("f_discipline", []), ("f_service", []), ("f_year_range", None),
    ("year_field_choice", "Concept Year"),
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
# HERO
# ════════════════════════════════════════════════════════════════
st.markdown(
    f"""
    <div class="hero-box">
        <span class="hero-nav-placeholder">Research Tools ↗ (coming soon)</span>
        <h1>BioM Innovation Database</h1>
        <p>{len(cases_all):,} cases of biology inspiring innovation, from lab research to commercial products.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

def count_active_filters() -> int:
    n = sum(bool(st.session_state[k]) for k in ["f_kingdom", "f_phase", "f_continent", "f_discipline", "f_service"])
    n += bool(st.session_state.search.strip())
    n += tuple(st.session_state.f_year_range) != (_year_min, _year_max)
    return int(n)

filtered = get_filtered_cases()

# ════════════════════════════════════════════════════════════════
# METRICS
# ════════════════════════════════════════════════════════════════
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total cases", f"{len(filtered):,}")
m2.metric("Commercial products", int((filtered["Product Phase"] == "Commercially Available").sum()))
m3.metric("Kingdoms represented", filtered["Kingdom"].nunique())
m4.metric("Countries", filtered["Country"].nunique())

# ════════════════════════════════════════════════════════════════
# FILTER BAR — directly above the table it controls
# ════════════════════════════════════════════════════════════════
# Active filters are visible without opening anything: each popover button's
# label shows its selection count, and hovering it lists the chosen values.
_n_active = count_active_filters()
with st.container(border=True):
    _s_col, _n_col, _c_col = st.columns([6, 1.4, 1.2], vertical_alignment="center")
    with _s_col:
        st.text_input("Search", key="search", placeholder="Search by product, organism, keyword, institution…",
                      label_visibility="collapsed")
    with _n_col:
        st.caption(f"{_n_active} filter{'s' if _n_active != 1 else ''} active" if _n_active else "No filters applied")
    with _c_col:
        st.button("Clear all", on_click=clear_filters, disabled=(_n_active == 0), use_container_width=True)

    # Each filter lives in a fixed-height popover button instead of an inline
    # multiselect: an inline multiselect grows taller with every selected tag,
    # which made the whole bar uneven. The button label carries the selection
    # count and the hover tooltip lists the chosen values.
    _popover_filters = [
        ("Kingdom", "f_kingdom", sorted(cases_all["Kingdom"].dropna().unique())),
        ("Product Phase", "f_phase", sorted(cases_all["Product Phase"].dropna().unique())),
        ("Continent", "f_continent", sorted(cases_all["Continent"].dropna().unique())),
        ("Discipline", "f_discipline", sorted(disciplines_all["discipline"].dropna().unique())),
        ("Ecosystem Service", "f_service", sorted(services_all["ecosystem_service"].dropna().unique())),
    ]
    _fcols = st.columns(6)
    for _col, (_name, _key, _options) in zip(_fcols[:5], _popover_filters):
        _sel = st.session_state[_key]
        with _col:
            with st.popover(f"{_name} · {len(_sel)}" if _sel else _name, use_container_width=True,
                            help=", ".join(_sel) if _sel else None):
                st.multiselect(_name, _options, key=_key, placeholder="All", label_visibility="collapsed")
    with _fcols[5]:
        _lo, _hi = st.session_state.f_year_range
        _yr_changed = (_lo, _hi) != (_year_min, _year_max)
        with st.popover(f"Concept Year · {_lo}–{_hi}" if _yr_changed else "Concept Year", use_container_width=True):
            st.slider("Concept Year", min_value=_year_min, max_value=_year_max, key="f_year_range")

# ════════════════════════════════════════════════════════════════
# TABS — Cases | Explore 
# ════════════════════════════════════════════════════════════════
tab_cases, tab_explore = st.tabs(["Cases", "Explore"])

with tab_cases:
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

        sort_df = filtered.copy()
        sort_df["_has_real_name"] = sort_df["Product Name"].notna()
        sort_df = sort_df.sort_values("_has_real_name", ascending=False)

        table_df = sort_df[_CORE_COLS + list(_HIDEABLE_COLS.keys())].rename(columns={
            "display_name": "Case", "Concept Year_year": "Concept Yr", "Commercial Year_year": "Commercial Yr",
        })

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
            "case_id": 90, "Case": 220, "Mimic": 160, "Kingdom": 110,
            "Product Phase": 170, "Company or Institution Name": 200,
            "Continent": 130, "Concept Yr": 110, "Commercial Yr": 120,
        }
        _HEADER_LABELS = {"case_id": "case_id", "Company or Institution Name": "Institution", **_HIDEABLE_COLS}

        gb = GridOptionsBuilder.from_dataframe(table_df)
        gb.configure_selection("multiple", use_checkbox=True, header_checkbox=True,
                               suppressRowClickSelection=True)
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
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=10)
        grid_response = AgGrid(
            table_df, gridOptions=gb.build(), height=480, allow_unsafe_jscode=True,
            theme="alpine", update_on=["selectionChanged"], fit_columns_on_grid_load=False,
            custom_css={
                ".ag-header-cell-label": {"justify-content": "center"},
                # Excludes ag-grid's own right-aligned numeric-cell class, so
                # case_id / Concept Yr / Commercial Yr keep their natural
                # right alignment while every other (text) column goes left.
                ".ag-cell:not(.ag-right-aligned-cell)": {"text-align": "left", "justify-content": "flex-start"},
            },
        )

        selected = grid_response.get("selected_rows")
        n_selected = 0 if selected is None else len(selected)
        selected_ids = []
        if n_selected:
            selected_ids = (
                selected["case_id"].astype(int).tolist() if hasattr(selected, "iloc")
                else [int(r["case_id"]) for r in selected]
            )

        _can_compare = COMPARE_MIN <= n_selected <= COMPARE_MAX
        _act1, _act2, _act3, _act4 = st.columns([1.3, 1.4, 1.8, 3.5])
        with _act1:
            if st.button("View Details", disabled=(n_selected != 1), use_container_width=True,
                         help="Select exactly one row to view its details."):
                st.session_state["_pending_view"] = ("detail", selected_ids[0])
        with _act2:
            _cmp_label = f"Compare ({n_selected})" if _can_compare else "Compare"
            if st.button(_cmp_label, disabled=not _can_compare, use_container_width=True,
                         help=f"Select {COMPARE_MIN}–{COMPARE_MAX} rows to compare them side by side."):
                st.session_state["_pending_view"] = ("compare", selected_ids)
        with _act3:
            if n_selected:
                selected_export_df = filtered[filtered["case_id"].isin(selected_ids)]
                st.download_button(
                    f"⬇ Download selected ({n_selected})", data=build_download_zip(selected_export_df),
                    file_name="biom_export_selected.zip", mime="application/zip", use_container_width=True,
                )
            else:
                st.button("⬇ Download selected", disabled=True, use_container_width=True)
        if n_selected > COMPARE_MAX:
            st.caption(f"Compare supports up to {COMPARE_MAX} cases — {n_selected} are currently selected.")

# ════════════════════════════════════════════════════════════════
# EXPLORE TAB — taxonomy explorer + charts
# ════════════════════════════════════════════════════════════════
_TAXON_LEVELS = ["Kingdom", "Group", "Phylum"]
_UNRECORDED = "(not recorded)"

# Map colour classes. Binned rather than a continuous scale: with one country
# far ahead of the rest, a linear scale paints every other country almost the
# same pale shade. Each class is a readable range in the legend.
_MAP_BINS = [(1, 1, "1"), (2, 4, "2–4"), (5, 14, "5–14"), (15, 49, "15–49"), (50, float("inf"), "50+")]
_MAP_BIN_LABELS = [b[2] for b in _MAP_BINS]
_MAP_BIN_COLORS = ["#CDEADD", "#8FD0B3", "#45A983", "#177A57", "#0A4430"]


def _map_bin(n: int) -> str:
    return next(label for lo, hi, label in _MAP_BINS if lo <= n <= hi)


def build_country_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Cases per country, largest first, with share and colour class.
    Groups by country_iso3 ALONE — grouping by (iso3, raw Country) was an
    earlier bug: different spellings of one country ("USA" / "U.S.A.") became
    separate rows and split that country's count. country_name_canonical (one
    fixed name per iso3, from geocode_countries.py) is the display name."""
    geo = df[df["Country"].notna() & df["country_iso3"].notna()]
    counts = (
        geo.groupby("country_iso3")
        .agg(count=("case_id", "size"), country_name_canonical=("country_name_canonical", "first"))
        .reset_index()
    )
    if counts.empty:
        return counts.assign(share=[], bin=[])
    counts["share"] = counts["count"] / counts["count"].sum() * 100
    counts["bin"] = counts["count"].map(_map_bin)
    return counts.sort_values(["count", "country_name_canonical"], ascending=[False, True]).reset_index(drop=True)


def build_taxonomy_frame(df: pd.DataFrame) -> pd.DataFrame:
    """One row per case with Kingdom/Group/Phylum. Blank levels become
    '(not recorded)' rather than being dropped: the sunburst cannot take a gap
    mid-path, and dropping those cases would make the counts silently not add up."""
    t = df[["case_id"] + _TAXON_LEVELS].copy()
    for c in _TAXON_LEVELS:
        t[c] = t[c].where(t[c].notna() & t[c].astype(str).str.strip().ne(""), _UNRECORDED)
    return t


def _level_select(label: str, key: str, frame: pd.DataFrame, col: str) -> pd.DataFrame:
    counts = frame[col].value_counts()
    options = ["All"] + counts.index.tolist()
    # A global-filter change can remove the current choice; reset before the
    # widget is drawn (setting a keyed widget's state is allowed at that point).
    if st.session_state.get(key) not in options:
        st.session_state[key] = "All"
    choice = st.selectbox(label, options, key=key,
                          format_func=lambda o: f"All ({len(frame)})" if o == "All" else f"{o} ({counts[o]})")
    return frame if choice == "All" else frame[frame[col] == choice]


with tab_explore:
    st.markdown('<div class="section-title">Explore by Taxonomy</div>', unsafe_allow_html=True)
    tax = build_taxonomy_frame(filtered)
    if tax.empty:
        st.caption("No cases match the current filters.")
    else:
        _tx_chart, _tx_browse = st.columns([1.1, 1])
        with _tx_chart:
            fig_tax = px.sunburst(
                tax, path=_TAXON_LEVELS, color="Kingdom",
                color_discrete_map={**KINGDOM_COLORS, _UNRECORDED: "#C9CFCB"}, height=460,
            )
            fig_tax.update_traces(hovertemplate="<b>%{label}</b><br>%{value} cases<extra></extra>")
            fig_tax.update_layout(margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig_tax, use_container_width=True)
            st.caption("Click a ring to zoom into that branch; click the centre to zoom back out.")
        with _tx_browse:
            _k = _level_select("Kingdom", "ex_kingdom", tax, "Kingdom")
            _g = _level_select("Group", "ex_group", _k, "Group")
            _p = _level_select("Phylum", "ex_phylum", _g, "Phylum")
            _branch = cases_all[cases_all["case_id"].isin(_p["case_id"])]
            st.caption(f"{len(_branch):,} case{'s' if len(_branch) != 1 else ''} in this branch")
            st.dataframe(
                _branch[["case_id", "display_name", "Mimic", "Product Phase"]].rename(columns={"display_name": "Case"}),
                hide_index=True, use_container_width=True, height=300,
            )

    st.markdown('<div class="section-title">Charts</div>', unsafe_allow_html=True)
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
    st.radio("Year field", ["Concept Year", "Commercial Year"], key="year_field_choice",
             label_visibility="collapsed", horizontal=True)
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
        country_counts = build_country_counts(filtered)

        if len(country_counts):
            _map_col, _top_col = st.columns([2.3, 1])
            with _map_col:
                fig4 = px.choropleth(
                    country_counts, locations="country_iso3", color="bin",
                    category_orders={"bin": _MAP_BIN_LABELS},
                    color_discrete_map=dict(zip(_MAP_BIN_LABELS, _MAP_BIN_COLORS)),
                    custom_data=["country_name_canonical", "count", "share"], height=460,
                )
                fig4.update_traces(
                    hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} cases"
                                  " · %{customdata[2]:.1f}% of mapped cases<extra></extra>",
                    marker_line_color="#FFFFFF", marker_line_width=0.6,
                )
                fig4.update_geos(
                    projection_type="natural earth", lataxis_range=[-58, 85],
                    showframe=False, showcoastlines=False,
                    showcountries=True, countrycolor="#FFFFFF", countrywidth=0.6,
                    showland=True, landcolor="#E4EAE6", showocean=True, oceancolor="#F7FAF8",
                    bgcolor="rgba(0,0,0,0)",
                )
                fig4.update_layout(
                    margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                    legend=dict(title_text="Cases", orientation="h", yanchor="top", y=0.02, xanchor="left", x=0.01),
                )
                st.plotly_chart(fig4, use_container_width=True, config={"scrollZoom": True, "displaylogo": False})
                st.caption("Scroll to zoom, drag to pan, double-click to reset.")
            with _top_col:
                top = country_counts.head(10).iloc[::-1]
                fig5 = px.bar(
                    top, x="count", y="country_name_canonical", orientation="h", text="count",
                    color="bin", color_discrete_map=dict(zip(_MAP_BIN_LABELS, _MAP_BIN_COLORS)), height=460,
                )
                fig5.update_traces(textposition="outside", cliponaxis=False,
                                   hovertemplate="<b>%{y}</b><br>%{x} cases<extra></extra>")
                fig5.update_layout(
                    title=dict(text="Top countries", font=dict(size=13)), showlegend=False,
                    margin=dict(l=0, r=24, t=36, b=0), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(visible=False), yaxis=dict(title="", categoryorder="array", categoryarray=top["country_name_canonical"].tolist()),
                )
                st.plotly_chart(fig5, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("No mappable country data for the current filter.")

        if unmapped:
            st.caption(f"⚠ {len(unmapped)} country value(s) have no geocode and are excluded above: {unmapped}. "
                       f"Re-run geocode_countries.py after checking these against COUNTRY_ALIASES.")

# ════════════════════════════════════════════════════════════════
# CASE PROFILE — content builders
# ════════════════════════════════════════════════════════════════
_STAGES = [("Concept", "Concept Year"), ("Prototype", "Prototype Year"), ("Commercial", "Commercial Year")]
_STAGE_RANK = {"Concept": 0, "Prototype": 1, "Patent": 2, "Commercial": 3}


def build_timeline_events(row, pat: pd.DataFrame) -> list:
    """Concept / Prototype / Commercial years plus patent years, sorted
    chronologically. Ties keep the natural stage order. Patents sharing a
    year are grouped into one event. Patents with no parsed year are left
    off the timeline (they are reported in the data notes instead)."""
    events = []
    for stage, field in _STAGES:
        year = row.get(f"{field}_year")
        if pd.notna(year):
            q = row.get(f"{field}_year_qualifier")
            events.append({"year": int(year), "stage": stage, "detail": "",
                           "qualifier": q if pd.notna(q) else None})
    if len(pat):
        dated = pat[pat["patent_year"].notna()]
        for year, grp in dated.groupby(dated["patent_year"].astype(int)):
            nums = grp["patent_number"].dropna().astype(str).tolist()
            shown = ", ".join(nums[:3]) + (f" +{len(nums) - 3} more" if len(nums) > 3 else "")
            events.append({"year": int(year), "stage": "Patent",
                           "detail": f"{len(grp)} patents" + (f" · {shown}" if shown else "") if len(grp) > 1 else shown,
                           "qualifier": None})
    return sorted(events, key=lambda e: (e["year"], _STAGE_RANK[e["stage"]]))


def build_data_notes(row, pat: pd.DataFrame) -> list:
    """Plain-language notes on data quality for one case, derived only from
    fields that actually exist — nothing inferred."""
    notes = []
    if pd.isna(row.get("Product Name")):
        notes.append("No product name was recorded for this case; the title shown is a placeholder.")

    for stage, field in _STAGES:
        q = row.get(f"{field}_year_qualifier")
        if pd.notna(q):
            raw = row.get(f"{field}_year_raw")
            recorded = f" (recorded as \u201c{raw}\u201d)" if pd.notna(raw) else ""
            notes.append(f"{stage} year is {'an expected date' if q == 'expected' else 'approximate'}{recorded}.")

    years = [int(row.get(f"{f}_year")) for _, f in _STAGES if pd.notna(row.get(f"{f}_year"))]
    if years != sorted(years):
        notes.append("Recorded years are not in the usual concept \u2192 prototype \u2192 commercial order; they are shown as recorded.")

    if len(pat):
        undated = pat[pat["patent_year"].isna()]
        if len(undated):
            raws = sorted({str(v) for v in undated.get("patent_year_raw", pd.Series(dtype=str)).dropna()})
            recorded = f" (recorded as {', '.join(chr(8220) + r + chr(8221) for r in raws)})" if raws else ""
            notes.append(f"{len(undated)} patent record(s) have no usable year{recorded} and are not placed on the timeline.")
        n_no_number = int(pat["patent_number"].isna().sum())
        if n_no_number:
            notes.append(f"{n_no_number} patent record(s) have a year but no patent number.")

    canonical = row.get("country_name_canonical")
    country = row.get("Country")
    if pd.notna(canonical) and pd.notna(country) and str(country).strip().lower() != str(canonical).strip().lower():
        notes.append(f"Country recorded as \u201c{country}\u201d; mapped as \u201c{canonical}\u201d.")
    return notes


# ════════════════════════════════════════════════════════════════
# DETAIL DIALOG
# ════════════════════════════════════════════════════════════════
_open_view = st.session_state.pop("_pending_view", None)

if _open_view is not None and _open_view[0] == "detail":

    @st.dialog(" ", width="medium")
    def show_detail(case_id: int):
        row = cases_all[cases_all["case_id"] == case_id].iloc[0]
        pat = patents_all[patents_all["case_id"] == case_id]
        esc = lambda v: html.escape(str(v))

        def _present(v):
            return pd.notna(v) and str(v).strip() != ""

        def _section(title):
            st.markdown(
                f'<div style="font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;'
                f'color:var(--mid-green);margin:14px 0 6px;">{title}</div>',
                unsafe_allow_html=True,
            )

        def _pills(values):
            return "".join(f'<span class="pill">{esc(v)}</span>' for v in values)

        def _kv_grid(pairs, columns=2):
            """Blank fields are skipped entirely (pd.notna, not truthiness —
            NaN is truthy in Python), so no 'nan' or '—' placeholders."""
            items = [(l, v) for l, v in pairs if _present(v)]
            if not items:
                return
            cells = "".join(
                f'<div><div style="color:var(--muted);font-size:10.5px;text-transform:uppercase;'
                f'letter-spacing:0.03em;margin-bottom:1px;">{label}</div>'
                f'<div style="font-size:14px;color:var(--charcoal);margin-bottom:10px;">{esc(value)}</div></div>'
                for label, value in items
            )
            st.markdown(
                f'<div style="display:grid;grid-template-columns:repeat({columns},1fr);gap:0 18px;">{cells}</div>',
                unsafe_allow_html=True,
            )

        # ── Header ─────────────────────────────────────────────
        subtitle = " · ".join(p for p in [esc(row["Mimic"]) if _present(row.get("Mimic")) else "", f"case_id {case_id}"] if p)
        phase = row.get("Product Phase")
        phase_cls = {"Commercially Available": "badge-teal", "In Development": "badge-amber"}.get(phase, "badge-gray")
        badges = f'<span class="{phase_cls}">{esc(phase)}</span>' if _present(phase) else ""
        if row.get("Case Status") == VERIFIED_STATUS:
            badges += ('<span style="margin-left:6px;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700;'
                       'color:var(--mid-green);border:1px solid var(--mid-green);">Interview-verified</span>')
        st.markdown(f"""
        <div style="background: var(--dark-green); margin: 0 0 0.6rem 0; padding: 18px 26px 14px; border-radius: 8px;">
            <div style="color:#fff; font-size:19px; font-weight:700; margin-bottom:4px;">{esc(row['display_name'])}</div>
            <div style="color:#5DCAA5; font-size:12.5px;">{subtitle}</div>
        </div>
        {f'<div style="margin-bottom:4px;">{badges}</div>' if badges else ''}
        """, unsafe_allow_html=True)

        if _present(row.get("Product Description")):
            st.caption(row["Product Description"])

        # ── Biological Inspiration ─────────────────────────────
        chain = [row.get(c) for c in ["Kingdom", "Group", "Phylum"] if _present(row.get(c))]
        levels = [(c.replace("Mimic ", ""), row.get(c)) for c in ["Mimic Subsystem", "Mimic System", "Mimic Suprasystem"]]
        if chain or any(_present(v) for _, v in levels):
            _section("Biological Inspiration")
            if chain:
                st.markdown(
                    '<div style="font-size:14px;color:var(--charcoal);margin-bottom:8px;">'
                    + ' <span style="color:var(--muted);">\u203a</span> '.join(esc(c) for c in chain) + "</div>",
                    unsafe_allow_html=True,
                )
            _kv_grid(levels, columns=3)

        # ── Innovation ─────────────────────────────────────────
        biom_tags = [c for c in ["Function", "Form", "Process", "Interaction"] if row.get(f"biom_type_{c.lower()}") is True]
        if biom_tags or _present(row.get("Process Type")):
            _section("Innovation")
            if biom_tags:
                st.markdown('<span style="font-size:12px;color:var(--muted);margin-right:6px;">BioM Type</span>'
                            + _pills(biom_tags), unsafe_allow_html=True)
            _kv_grid([("Process Type", row.get("Process Type"))], columns=1)

        # ── Innovation Journey ─────────────────────────────────
        events = build_timeline_events(row, pat)
        if events:
            _section("Innovation Journey")
            dot = {"Concept": "#8FA89C", "Prototype": "#D4870A", "Patent": "#4A6358", "Commercial": "#0A2E1F"}
            items = ""
            for e in events:
                tag = ""
                if e["qualifier"]:
                    tag = (f' <span style="font-size:10.5px;font-weight:600;padding:1px 7px;border-radius:10px;'
                           f'background:#FAEEDA;color:#854F0B;">{esc(e["qualifier"])}</span>')
                detail = f' <span style="color:var(--muted);">\u00b7 {esc(e["detail"])}</span>' if e["detail"] else ""
                items += (
                    f'<div style="position:relative;padding:0 0 12px 22px;">'
                    f'<span style="position:absolute;left:0;top:4px;width:11px;height:11px;border-radius:50%;'
                    f'background:{dot[e["stage"]]};border:2px solid #fff;box-shadow:0 0 0 1px {dot[e["stage"]]};"></span>'
                    f'<div style="font-size:13.5px;font-weight:700;color:var(--charcoal);">{e["year"]}{tag}</div>'
                    f'<div style="font-size:12.5px;color:var(--slate);">{e["stage"]}{detail}</div></div>'
                )
            st.markdown(
                f'<div style="position:relative;margin-left:4px;">'
                f'<div style="position:absolute;left:6px;top:8px;bottom:14px;width:2px;background:var(--border);"></div>'
                f'{items}</div>',
                unsafe_allow_html=True,
            )

        # ── Services, disciplines, keywords ────────────────────
        svc = services_all.loc[services_all["case_id"] == case_id, "ecosystem_service"].dropna().tolist()
        if svc:
            _section("Ecosystem Services")
            st.markdown(_pills(svc), unsafe_allow_html=True)

        disc = disciplines_all.loc[disciplines_all["case_id"] == case_id, "discipline"].dropna().tolist()
        if disc:
            _section("Disciplines")
            st.markdown(_pills(disc), unsafe_allow_html=True)

        kw = keywords_all[keywords_all["case_id"] == case_id]
        prod_kw = kw.loc[kw["keyword_type"] == "product", "keyword"].dropna().tolist()
        pat_kw = kw.loc[kw["keyword_type"] == "patent", "keyword"].dropna().tolist()
        if prod_kw or pat_kw:
            _section("Keywords")
            if prod_kw:
                st.markdown(_pills(prod_kw), unsafe_allow_html=True)
            if pat_kw:
                st.markdown('<span style="font-size:12px;color:var(--muted);margin-right:6px;">Patent</span>'
                            + _pills(pat_kw), unsafe_allow_html=True)

        # ── Patents (numbers live here; years are on the timeline) ─
        if len(pat):
            _section("Patents")
            pat_display = pat[["patent_year", "patent_number"]].copy()
            pat_display["patent_year"] = pat_display["patent_year"].astype("Int64")
            st.dataframe(pat_display.rename(columns={"patent_year": "Year", "patent_number": "Number"}),
                         hide_index=True, use_container_width=True)

        # ── Origin ─────────────────────────────────────────────
        origin = [
            ("Institution", row.get("Company or Institution Name")), ("Country", row.get("Country")),
            ("Academia / Industry", row.get("Academia or Industry")), ("Continent", row.get("Continent")),
        ]
        if any(_present(v) for _, v in origin):
            _section("Origin")
            _kv_grid(origin)

        # ── Data notes ─────────────────────────────────────────
        notes = build_data_notes(row, pat)
        if notes:
            _section("Data notes")
            st.markdown(
                '<ul style="margin:0;padding-left:18px;font-size:12.5px;color:var(--slate);line-height:1.5;">'
                + "".join(f"<li>{esc(n)}</li>" for n in notes) + "</ul>",
                unsafe_allow_html=True,
            )

        if _present(row.get("Word Category")):
            with st.expander("Linguistic Evidence"):
                st.caption(f"Word Category: {row['Word Category']}")

        if st.button("Close"):
            st.rerun()

    show_detail(_open_view[1])

# ════════════════════════════════════════════════════════════════
# COMPARE DIALOG
# ════════════════════════════════════════════════════════════════
_MISSING = "—"


def _fmt_year(row, field: str) -> str:
    year = row.get(f"{field}_year")
    if pd.isna(year):
        return _MISSING
    qualifier = row.get(f"{field}_year_qualifier")
    return f"{int(year)} ({qualifier})" if pd.notna(qualifier) else str(int(year))


def _fmt_text(value) -> str:
    return _MISSING if pd.isna(value) or str(value).strip() == "" else str(value)


def _fmt_biom_type(row) -> str:
    parts = [c for c in ["Function", "Form", "Process", "Interaction"] if row.get(f"biom_type_{c.lower()}") is True]
    if parts:
        return ", ".join(parts)
    return "N/A" if row.get("biom_type_na") is True else _MISSING


def _fmt_verified(row) -> str:
    status = row.get("Case Status")
    if pd.isna(status):
        return _MISSING
    return "Yes" if status == VERIFIED_STATUS else "No"


def build_compare_rows(case_ids: list) -> tuple:
    """Returns (column headers, [(label, [value per case])]). Every row keeps
    one cell per case — missing values render as '—' rather than being
    dropped, so the columns stay aligned (the opposite of the detail view,
    where blank fields are skipped entirely)."""
    rows = [cases_all[cases_all["case_id"] == cid].iloc[0] for cid in case_ids]
    headers = [(str(r["display_name"]), int(r["case_id"])) for r in rows]

    def joined(child_df, col, cid):
        vals = child_df.loc[child_df["case_id"] == cid, col].dropna().astype(str).tolist()
        return ", ".join(vals) if vals else _MISSING

    def n_patents(cid):
        n = int((patents_all["case_id"] == cid).sum())
        return str(n) if n else _MISSING

    spec = [
        ("Product Phase", lambda r: _fmt_text(r.get("Product Phase"))),
        ("Interview-verified", _fmt_verified),
        ("Mimic", lambda r: _fmt_text(r.get("Mimic"))),
        ("Kingdom", lambda r: _fmt_text(r.get("Kingdom"))),
        ("Group", lambda r: _fmt_text(r.get("Group"))),
        ("Phylum", lambda r: _fmt_text(r.get("Phylum"))),
        ("Mimic System", lambda r: _fmt_text(r.get("Mimic System"))),
        ("Mimic Subsystem", lambda r: _fmt_text(r.get("Mimic Subsystem"))),
        ("Mimic Suprasystem", lambda r: _fmt_text(r.get("Mimic Suprasystem"))),
        ("BioM Type", _fmt_biom_type),
        ("Process Type", lambda r: _fmt_text(r.get("Process Type"))),
        ("Concept Year", lambda r: _fmt_year(r, "Concept Year")),
        ("Prototype Year", lambda r: _fmt_year(r, "Prototype Year")),
        ("Commercial Year", lambda r: _fmt_year(r, "Commercial Year")),
        ("Patents", lambda r: n_patents(r["case_id"])),
        ("Ecosystem Services", lambda r: joined(services_all, "ecosystem_service", r["case_id"])),
        ("Disciplines", lambda r: joined(disciplines_all, "discipline", r["case_id"])),
        ("Institution", lambda r: _fmt_text(r.get("Company or Institution Name"))),
        ("Academia / Industry", lambda r: _fmt_text(r.get("Academia or Industry"))),
        ("Country", lambda r: _fmt_text(r.get("Country"))),
        ("Continent", lambda r: _fmt_text(r.get("Continent"))),
    ]
    return headers, [(label, [fn(r) for r in rows]) for label, fn in spec]


def row_differs(values: list) -> bool:
    return len(set(values)) > 1


if _open_view is not None and _open_view[0] == "compare":

    @st.dialog(" ", width="large")
    def show_compare(case_ids: list):
        headers, rows = build_compare_rows(case_ids)

        st.markdown(f"""
        <div style="background: var(--dark-green); margin: 0 0 0.9rem 0; padding: 18px 26px 14px; border-radius: 8px;">
            <div style="color:#fff; font-size:19px; font-weight:700;">Comparing {len(case_ids)} cases</div>
        </div>
        """, unsafe_allow_html=True)

        diff_only = st.toggle("Only show rows that differ", key="_compare_diff_only")
        visible = [(label, vals) for label, vals in rows if not diff_only or row_differs(vals)]

        head_cells = "".join(
            f'<th style="text-align:left;padding:8px 10px;border-bottom:2px solid var(--border);vertical-align:bottom;">'
            f'<div style="font-size:13.5px;font-weight:700;color:var(--charcoal);">{html.escape(name)}</div>'
            f'<div style="font-size:11px;color:var(--muted);font-weight:500;">case_id {cid}</div></th>'
            for name, cid in headers
        )
        body_rows = []
        for label, vals in visible:
            bg = "background:var(--pale-teal);" if row_differs(vals) else ""
            cells = "".join(
                f'<td style="padding:7px 10px;font-size:13px;color:var(--charcoal);vertical-align:top;">{html.escape(v)}</td>'
                for v in vals
            )
            body_rows.append(
                f'<tr style="border-bottom:1px solid var(--border);{bg}">'
                f'<td style="padding:7px 10px;font-size:11px;font-weight:600;color:var(--slate);'
                f'text-transform:uppercase;letter-spacing:0.03em;white-space:nowrap;vertical-align:top;">{label}</td>'
                f'{cells}</tr>'
            )

        if not visible:
            st.caption("These cases have identical values in every compared field.")
        else:
            col_w = f"{82 // len(headers)}%"
            colgroup = '<col style="width:18%">' + "".join(f'<col style="width:{col_w}">' for _ in headers)
            st.markdown(
                f'<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;table-layout:fixed;">'
                f'<colgroup>{colgroup}</colgroup><thead><tr><th></th>{head_cells}</tr></thead>'
                f'<tbody>{"".join(body_rows)}</tbody></table></div>',
                unsafe_allow_html=True,
            )
            if not diff_only:
                st.caption("Highlighted rows differ between the selected cases.")

        if st.button("Close", key="_compare_close"):
            st.rerun()

    show_compare(_open_view[1])
