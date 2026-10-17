"""European defence expenditure page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.analysis import defence as D
from src.config import EXPORTABLE_SOURCES
from src.data.schema import MILEX_INDICATORS
from src.ui import common as U
from src.visualization import charts as V
from src.visualization.theme import assign_stable

DEFAULT_COUNTRIES = ["Germany", "France", "United Kingdom", "Italy", "Poland", "Sweden"]
FMT = {"US$ million": ",.0f", "% of GDP": ".2f", "US$ per person": ",.0f",
       "% of general government expenditure": ".2f"}  # fmt: skip


def render() -> None:
    v = U.db_version()
    st.sidebar.markdown("### Defence filters")
    src = U.pick_source("defence", "defence_source", "Expenditure dataset")
    inds = [i for i in MILEX_INDICATORS if i in U.milex_indicators(v, src.name)]
    ind = st.sidebar.selectbox("Indicator", inds, format_func=lambda i: MILEX_INDICATORS[i]["label"],
                               key=f"ind_{src.name}")  # fmt: skip
    meta = MILEX_INDICATORS[ind]
    full = U.milex(v, src.name, ind)
    have = full.dropna(subset=["value"])
    all_countries = sorted(have["country"].unique())
    default = [c for c in DEFAULT_COUNTRIES if c in all_countries] or all_countries[:6]
    sel = st.sidebar.multiselect("Countries (max 8 for trend charts)", all_countries, default=default,
                                 max_selections=8, key=f"mx_ctry_{src.name}")  # fmt: skip
    y0, y1 = int(have["year"].min()), int(have["year"].max())
    years = st.sidebar.slider("Years", y0, y1, (max(y0, 2000), y1), key=f"mx_years_{src.name}")

    U.page_header("Area B · European defence trends", "Military expenditure in Europe",
                  "Levels, burdens and changes in national military spending, with units kept explicit.")  # fmt: skip
    U.status_banner(src)
    unit = full["unit"].iloc[0]
    basis = full["price_basis"].iloc[0]
    st.info(U.md(f"**Indicator:** {meta['label']}  \n**Unit:** {unit} · **Price basis:** {basis}  \n"
                 f"{meta['definition']}"), icon=":material/straighten:")  # fmt: skip
    syn = src["data_status"] == "synthetic"
    fmt = FMT.get(unit, ",.2f")
    span = full[(full["year"] >= years[0]) & (full["year"] <= years[1])]

    last = int(span.dropna(subset=["value"])["year"].max())
    k = st.columns(4)
    k[0].metric(f"Countries with data, {last}", int(span[(span.year == last)]["value"].notna().sum()),
                help="European countries (excluding historical entities and the EU aggregate).")  # fmt: skip
    k[1].metric("Values flagged as estimates", U.fmt_pct(D.estimate_share(span), 1),
                help="Share of non-missing values in the selected years that SIPRI marks as "
                "estimates (blue) or highly uncertain (red).")  # fmt: skip
    k[2].metric("Missing country-years", U.fmt_pct(span["value"].isna().mean(), 1),
                help="'...' (unavailable) and 'xxx' (state did not exist). Never filled with zero.")  # fmt: skip
    if ind in D.RATIOS:
        k[3].metric(f"Median across countries, {last}",
                    f"{span[span.year == last]['value'].astype(float).median():.2f}%",
                    help="Median, not mean: a few very high values (e.g. countries at war) dominate a mean.")  # fmt: skip
    elif ind not in D.NOMINAL:
        bt = D.balanced_total(span, years[0], last)
        if len(bt["totals"]) >= 2 and bt["totals"].iloc[0] > 0:
            chg = bt["totals"].iloc[-1] / bt["totals"].iloc[0] - 1
            k[3].metric(f"Real change in total, {years[0]}–{last}", f"{chg * 100:+.0f}%",
                        help=f"Balanced panel of {len(bt['included'])} countries with data in every "
                        f"year; excluded: {', '.join(bt['excluded']) or 'none'}.")  # fmt: skip

    t_tr, t_cmp, t_chg, t_thr, t_cov = st.tabs(
        ["Trends", "Country comparison", "Change", "% of GDP threshold", "Coverage & flags"]
    )

    with t_tr:
        d = span[span["country"].isin(sel)]
        if "mx_colors" not in st.session_state:
            st.session_state["mx_colors"] = {}
        cmap = assign_stable(st.session_state["mx_colors"], sel)
        mode = "Level"
        if ind not in D.NOMINAL and ind not in D.RATIOS:
            mode = st.segmented_control("Display", ["Level", "Index (base year = 100)"],
                                        default="Level", key="mx_mode") or "Level"  # fmt: skip
        if not sel:
            st.info("Select at least one country in the sidebar.")
        elif mode == "Level":
            st.plotly_chart(V.milex_lines(d, unit, meta["label"], syn, cmap=cmap), width="stretch")
        else:
            base = st.select_slider("Base year", options=list(range(years[0], years[1] + 1)),
                                    value=years[0], key="mx_base")  # fmt: skip
            idx = D.index_to_base(d, base).rename(columns={"index": "value"})
            idx["value_flag"] = "reported"
            st.plotly_chart(V.milex_lines(idx, f"Index ({base} = 100)",
                                          f"Real military expenditure, index {base} = 100", syn,
                                          baseline=100, cmap=cmap), width="stretch")  # fmt: skip
            st.caption("Indexing removes differences in size so growth paths can be compared on one axis.")
        if ind in D.NOMINAL:
            st.warning(U.md("Current-US$ series move with inflation and exchange rates. Use the constant-price "
                            "indicator to assess real growth."), icon=":material/warning:")  # fmt: skip
        st.caption("Open circles mark values flagged by SIPRI as estimates or highly uncertain.")

    with t_cmp:
        yr = st.select_slider("Year", options=sorted(span["year"].dropna().unique().astype(int)),
                              value=last, key="mx_cmp_year")  # fmt: skip
        lv = D.latest_values(span, yr)
        st.plotly_chart(V.milex_ranking(lv, unit, f"{meta['label']}, {yr}", syn, fmt), width="stretch")
        st.caption(
            "Hatched bars are SIPRI estimates. Ordering reflects point values only; small differences "
            "are within measurement uncertainty and should not be read as a ranking of effort. "
            f"Countries without data for {yr} are omitted, not shown as zero."
        )

    with t_chg:
        c1, c2 = st.columns(2)
        ys = sorted(span["year"].dropna().unique().astype(int))
        yf = c1.selectbox("From", ys, index=max(0, len(ys) - 11), key="chg_from")
        yt = c2.selectbox("To", ys, index=len(ys) - 1, key="chg_to")
        if yt <= yf:
            st.warning("'To' must be later than 'From'.")
        elif ind in D.NOMINAL:
            st.warning(U.md("Growth is not computed on current-price series. Select the constant (2024) US$ "
                            "indicator for real change, or a share-of-GDP indicator for change in burden."))  # fmt: skip
        else:
            ch = D.change_between(span, yf, yt)
            col = "change_pp" if ind in D.RATIOS else "pct_change"
            xt = "Change (percentage points)" if ind in D.RATIOS else "Real change (%)"
            st.plotly_chart(V.change_bars(ch, col, xt, f"{meta['label']}: change {yf}–{yt}", syn),
                            width="stretch")  # fmt: skip
            st.caption("Only countries with data in both years are shown. Shares change in "
                       "percentage points; constant-price levels in percent.")  # fmt: skip
            st.dataframe(ch, hide_index=True, width="stretch")

    with t_thr:
        g = U.milex(v, src.name, "share_gdp_pct")
        g = g[(g["year"] >= years[0]) & (g["year"] <= years[1])]
        thr = st.number_input("Threshold (% of GDP)", 0.5, 10.0, 2.0, 0.5, key="thr")
        tc = D.count_at_or_above(g, thr)
        st.plotly_chart(V.threshold_counts(tc, thr, syn), width="stretch")
        st.caption(
            "Grey bars show how many countries have data each year (the denominator). SIPRI's "
            "definition of military expenditure differs from NATO's, so this is **not** a measure "
            "of compliance with NATO's 2% guideline, and it covers non-NATO states."
        )

    with t_cov:
        cov = span.groupby(["country", "value_flag"]).size().unstack(fill_value=0)
        st.dataframe(cov.reset_index(), hide_index=True, width="stretch")
        st.caption("Number of country-years per flag in the selected range.")
        if src.name in EXPORTABLE_SOURCES:
            st.download_button("Download selected series (CSV)", span.to_csv(index=False).encode(),
                               file_name=f"{src.name}_{ind}.csv", mime="text/csv")  # fmt: skip
        else:
            st.info(f"Export disabled: {src['redistribution']} Obtain the workbook directly from "
                    f"{src['url']}.", icon=":material/lock:")  # fmt: skip
        st.caption(U.md(f"Source: {src['citation']}"))
