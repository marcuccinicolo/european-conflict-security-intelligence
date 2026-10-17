"""Conflict patterns page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.analysis import conflict as C
from src.analysis import spatial as S
from src.config import EXPORTABLE_SOURCES
from src.ui import common as U
from src.visualization import charts as V

NOT_ALL = (
    "Counts are **recorded events** in the selected dataset - not a census of all incidents. "
    "Coverage depends on media and partner reporting, access, language and the source's "
    "inclusion rules, all of which change over time."
)


def _defaults(source: str, opts: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    lo, hi = pd.Timestamp(opts["date_min"]), pd.Timestamp(opts["date_max"])
    if source == "ucdp_ged":  # focus on the post-2014 period by default
        lo = max(lo, pd.Timestamp("2014-01-01"))
    return lo, hi


def render() -> None:
    v = U.db_version()
    st.sidebar.markdown("### Conflict filters")
    src = U.pick_source("conflict", "conflict_source", "Conflict dataset")
    opts = U.event_options(v, src.name)
    lo, hi = _defaults(src.name, opts)
    dmin, dmax = pd.Timestamp(opts["date_min"]).date(), pd.Timestamp(opts["date_max"]).date()
    dates = st.sidebar.date_input("Date range", (lo.date(), hi.date()), min_value=dmin,
                                  max_value=dmax, key=f"dates_{src.name}")  # fmt: skip
    start, end = (dates if isinstance(dates, tuple) and len(dates) == 2 else (lo.date(), hi.date()))
    countries = st.sidebar.multiselect("Countries", opts["countries"], key=f"ctry_{src.name}",
                                       placeholder="All countries")  # fmt: skip
    types = st.sidebar.multiselect("Event types", opts["event_types"], key=f"types_{src.name}",
                                   placeholder="All event types")  # fmt: skip
    freq = st.sidebar.radio("Time aggregation", ["Month", "Quarter", "Year"], horizontal=True,
                            key="conflict_freq")  # fmt: skip

    U.page_header("Area A · Conflict patterns", "Conflict events in Europe",
                  "Where and when organised violence is recorded, and how complete the records are.")  # fmt: skip
    U.status_banner(src)

    df = U.events(v, src.name, start, end, tuple(countries), tuple(types))
    if df.empty:
        st.warning("No events match the current filters.")
        return
    syn = src["data_status"] == "synthetic"
    kind = df["fatalities_kind"].iloc[0]
    m = C.headline_metrics(df)

    k = st.columns(5)
    k[0].metric("Recorded events", U.fmt_int(m["events"]),
                help="Distinct source records in the selection after de-duplication.")  # fmt: skip
    k[1].metric("Countries with events", m["countries"])
    fat_label = "Estimated fatalities (best)" if kind == "estimate" else "Reported fatalities"
    fat_help = (
        f"Sum of UCDP 'best' estimates. Sum of low/high estimates: "
        f"{U.fmt_int(m.get('fatalities_low'))} - {U.fmt_int(m.get('fatalities_high'))}."
        if kind == "estimate"
        else "Sum of reported fatalities; events without a figure are excluded, not counted as 0."
    )
    k[2].metric(fat_label, U.fmt_int(m["fatalities"]), help=fat_help)
    k[3].metric("Events with a fatality figure", U.fmt_pct(m["fatality_data_coverage"], 1),
                help="Denominator: all recorded events in the selection.")  # fmt: skip
    k[4].metric("Precisely located", U.fmt_pct(m["share_precise_location"]),
                help="UCDP where_prec 1-2 (exact or within ~25 km); ACLED geo_precision 1.")  # fmt: skip
    st.caption(NOT_ALL)

    t_trend, t_geo, t_cat, t_rep, t_dl = st.tabs(
        ["Trends", "Map", "Countries & categories", "Reporting & completeness", "Data & download"]
    )

    with t_trend:
        by = st.segmented_control("Split by", ["None", "Event type"], default="None",
                                  key="trend_split") or "None"  # fmt: skip
        tc = C.temporal_counts(df, freq, by="event_type" if by == "Event type" else None,
                               start=start, end=end)  # fmt: skip
        st.plotly_chart(V.events_over_time(tc, "event_type" if by == "Event type" else None, freq, syn),
                        width="stretch")  # fmt: skip
        tot = C.temporal_counts(df, freq, start=start, end=end)
        lh = None
        if kind == "estimate":
            d = df.assign(period=df["event_date"].dt.to_period(C.FREQ[freq][0]).dt.start_time)
            lh = d.groupby("period").agg(low=("fatalities_low", "sum"), high=("fatalities_high", "sum")).reset_index()
        st.plotly_chart(V.fatalities_over_time(tot, freq, kind, syn, lh), width="stretch")
        st.caption(
            "Fatality figures are "
            + ("UCDP estimates; the shaded band is the sum of low and high estimates."
               if kind == "estimate" else "reported by the source and typically conservative.")  # fmt: skip
            + " Periods with no recorded events show 0. Monthly peaks can reflect reporting "
            "batches rather than real changes."
        )

    with t_geo:
        c1, c2 = st.columns([3, 1])
        with c2:
            mode = st.radio("Map layer", ["Points", "Density"], key="map_mode")
            precise = st.toggle("Precise locations only", value=True,
                                help="Exclude events located only to a region or country centroid.")  # fmt: skip
            lq = S.location_quality(df)
            st.metric("Valid coordinates", U.fmt_pct(lq["share_valid_coordinates"], 1))
            st.metric("Inside stated country (±10 km)", U.fmt_pct(lq["share_inside_stated_country"], 1),
                      help="Point-in-polygon test against Natural Earth 1:50m present-day borders.")  # fmt: skip
            conc = S.concentration(S.located(df, precise), cell_deg=0.5)
            st.metric("Share in 10 busiest 0.5° cells", U.fmt_pct(conc["share_in_top_cells"]),
                      help=f"Of {conc['located_events']:,} located events in {conc['cells_with_events']:,} cells.")  # fmt: skip
        with c1:
            mapped = S.located(df, precise)
            st.plotly_chart(V.event_map(mapped, mode, syn), width="stretch")
            st.caption(
                f"Showing {len(mapped):,} of {len(df):,} events "
                f"({len(df) - len(mapped):,} without valid or precise coordinates are excluded). "
                "Low-precision events are placed at administrative centroids and create artificial clusters."
            )
        st.markdown("##### Spatial summary")
        a, b = st.columns(2)
        with a:
            st.caption("Most frequently recorded first-level administrative units")
            st.dataframe(S.admin1_summary(df), hide_index=True, width="stretch")
        with b:
            st.caption("Annual mean centre and standard distance of located events (EPSG:3035)")
            mc = S.mean_centre_by_period(S.located(df, precise), "Y")
            mc["period"] = mc["period"].dt.year
            st.dataframe(mc.rename(columns={"period": "year"}), hide_index=True, width="stretch",
                         column_config={"lat": st.column_config.NumberColumn(format="%.2f"),
                                        "lon": st.column_config.NumberColumn(format="%.2f"),
                                        "standard_distance_km": st.column_config.NumberColumn("std. distance (km)", format="%.0f")})  # fmt: skip

    with t_cat:
        cs = C.country_summary(df)
        a, b = st.columns(2)
        with a:
            st.plotly_chart(V.horizontal_bar(cs, "country", "events", "Recorded events by country",
                                             "Recorded events", syn), width="stretch")  # fmt: skip
        with b:
            cat = C.category_summary(df, "event_type")
            st.plotly_chart(V.horizontal_bar(cat, "event_type", "events", "Recorded events by type",
                                             "Recorded events", syn), width="stretch")  # fmt: skip
        level = "sub_event_type" if df["sub_event_type"].notna().any() else "conflict_name"
        sub = C.category_summary(df, level)
        st.plotly_chart(V.horizontal_bar(
            sub, level, "events",
            "Recorded events by sub-event type" if level == "sub_event_type" else "Recorded events by UCDP conflict",
            "Recorded events", syn, top=12), width="stretch")  # fmt: skip
        if level == "conflict_name":
            st.caption("UCDP does not code sub-event types; its conflict identifier is shown instead.")
        st.markdown("##### Country table")
        st.dataframe(cs, hide_index=True, width="stretch", column_config={
            "share_of_events": st.column_config.ProgressColumn("share of events", format="percent", min_value=0, max_value=1),
            "precise_location": st.column_config.NumberColumn("precisely located", format="percent"),
            "fatality_data_coverage": st.column_config.NumberColumn("fatality data coverage", format="percent"),
            "fatalities": st.column_config.NumberColumn(fat_label.lower(), format="%d"),
            "first_event": st.column_config.DateColumn(), "last_event": st.column_config.DateColumn(),
        })  # fmt: skip

        st.markdown("##### Compare two equal periods")
        span = (pd.Timestamp(end) - pd.Timestamp(start)).days
        half = span // 2
        b0 = pd.Timestamp(end) - pd.Timedelta(days=half)
        a1 = b0 - pd.Timedelta(days=1)
        a0 = a1 - pd.Timedelta(days=half)
        pc = C.period_comparison(df, (a0, a1), (b0, pd.Timestamp(end)), by="country")
        st.caption(
            f"Period A: {a0.date()} to {a1.date()} · Period B: {b0.date()} to {pd.Timestamp(end).date()} "
            "(the selected range split into two equal halves). % change is shown only when "
            "period A has at least 10 events."
        )
        st.dataframe(pc, hide_index=True, width="stretch",
                     column_config={"pct_change": st.column_config.NumberColumn("% change", format="%+.0f%%")})  # fmt: skip

    with t_rep:
        cot = C.completeness_over_time(df, "Year")
        st.plotly_chart(V.completeness(cot, syn), width="stretch")
        f = V.sources_per_event(cot, syn)
        if f is not None:
            st.plotly_chart(f, width="stretch")
        st.markdown(
            """
**How to read this tab.** These series describe the *records*, not the conflict. Event
counts can rise because more sources are monitored, because events are split into finer
units, or because precision improves - without any change on the ground. Read trends in
event counts together with these indicators, and prefer comparisons within one source and
one period of stable coverage.
"""
        )

    with t_dl:
        if src.name in EXPORTABLE_SOURCES:
            st.markdown(f"**Citation (required):** {src['citation']}")
            st.caption(f"Licence: {src['licence']} · {src['redistribution']}")
            c1, c2 = st.columns(2)
            c1.download_button("Download filtered events (CSV)", df.to_csv(index=False).encode(),
                               file_name=f"{src.name}_events_{start}_{end}.csv", mime="text/csv",
                               icon=":material/download:")  # fmt: skip
            agg = C.temporal_counts(df, freq, by="country", start=start, end=end)
            c2.download_button(f"Download {freq.lower()}ly counts by country (CSV)",
                               agg.to_csv(index=False).encode(),
                               file_name=f"{src.name}_{freq.lower()}_counts_{start}_{end}.csv",
                               mime="text/csv", icon=":material/download:")  # fmt: skip
            st.dataframe(df.head(500), hide_index=True, width="stretch")
            st.caption("Preview of the first 500 rows.")
        else:
            st.info(
                "Row-level export is disabled for this dataset because its licence does not "
                f"permit redistribution. {src['redistribution']}",
                icon=":material/lock:",
            )
