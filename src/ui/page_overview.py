"""Overview page: project framing, data sources, and the side-by-side context view."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analysis import conflict as C
from src.ui import common as U
from src.visualization.charts import _finish
from src.visualization.theme import SERIES


def _source_card(col, row: pd.Series, area: str) -> None:
    cov = row["coverage"] or {}
    span = f"{cov.get('date_min', cov.get('year_min'))} – {cov.get('date_max', cov.get('year_max'))}"
    col.markdown(
        f"""<div class="ecsi-card">
        <div class="ecsi-muted">{area}</div>
        <h4>{row['name']}</h4>
        {U.tag(row['data_status'])}
        <p class="ecsi-muted" style="margin-top:.5rem">{row['publisher']}<br>
        Coverage: {span} · {int(row['rows_out']):,} rows<br>
        Licence: {row['licence']}<br>
        Retrieved: {str(row['retrieved_at_utc'])[:10]} · processed {str(row['processed_at_utc'])[:10]}</p>
        </div>""",
        unsafe_allow_html=True,
    )


def render() -> None:
    v = U.db_version()
    U.page_header(
        "Public-data research platform",
        "European Conflict & Security Intelligence",
        "A public-data analytics platform for understanding conflict patterns and European defence trends.",
    )
    st.markdown(
        """
This platform puts two complementary, **separately analysed** views of Europe's security
environment side by side:

- **Area A - Conflict patterns.** Where and when organised violence is *recorded*, by type,
  with explicit data-completeness diagnostics.
- **Area B - Defence trends.** National military expenditure: levels in constant prices,
  burden as a share of GDP, and change over time - with units and estimate flags explicit.

The two areas are descriptive. Nothing here estimates whether spending causes, deters or
responds to conflict.
"""
    )

    reg = U.registry(v)
    st.markdown("#### Datasets loaded")
    cols = st.columns(max(1, len(reg)))
    for col, (_, row) in zip(cols, reg.iterrows()):
        _source_card(col, row, "Area A · conflict" if row["domain"] == "conflict" else "Area B · defence")
    if not (reg["data_status"] == "real").any():
        st.warning("Only synthetic demonstration data are loaded. Run `python -m src.pipeline fetch` "
                   "then `python -m src.pipeline build` to add UCDP and SIPRI data.")  # fmt: skip

    st.divider()
    st.markdown("#### Side by side: one country, two lenses")
    st.caption(
        "Two separate charts with separate axes, on purpose. Co-movement between these series is "
        "not evidence of a causal relationship: both respond to many shared drivers (alliances, "
        "threat perception, economic cycles), and recorded conflict events depend on reporting."
    )
    c_src = U.pick_source("conflict", "ov_conf", "Conflict dataset", container=st)
    d_src = U.pick_source("defence", "ov_def", "Expenditure dataset", container=st)
    opts = U.event_options(v, c_src.name)
    gdp = U.milex(v, d_src.name, "share_gdp_pct")
    both = sorted(set(opts["countries"]) & set(gdp.dropna(subset=["value"])["country"]))
    if not both:
        st.info("No country appears in both selected datasets.")
        return
    default = both.index("Ukraine") if "Ukraine" in both else 0
    country = st.selectbox("Country", both, index=default, key="ov_country")
    ev = U.events(v, c_src.name, pd.Timestamp(opts["date_min"]).date(),
                  pd.Timestamp(opts["date_max"]).date(), (country,), ())  # fmt: skip
    tc = C.temporal_counts(ev, "Year")
    tc["year"] = tc["period"].dt.year
    g = gdp[gdp["country"] == country].dropna(subset=["value"])
    y0 = int(max(tc["year"].min(), g["year"].min()))
    y1 = int(max(tc["year"].max(), g["year"].max()))
    tc, g = tc[tc["year"].between(y0, y1)], g[g["year"].between(y0, y1)]

    a, b = st.columns(2)
    f1 = go.Figure(go.Bar(x=tc["year"], y=tc["events"], marker=dict(color=SERIES[0], cornerradius=3),
                          hovertemplate="%{x}: %{y:,} recorded events<extra></extra>"))  # fmt: skip
    f1.update_layout(title=f"{country}: recorded conflict events per year", yaxis_title="Recorded events",
                     xaxis=dict(range=[y0 - 0.5, y1 + 0.5]), hovermode="closest")  # fmt: skip
    a.plotly_chart(_finish(f1, c_src["data_status"] == "synthetic", 340), width="stretch")
    a.caption(f"Source: {c_src['name']}.")
    f2 = go.Figure(go.Scatter(x=g["year"], y=g["value"].astype(float), mode="lines+markers",
                              line=dict(width=2, color=SERIES[1]), marker=dict(size=8),
                              hovertemplate="%{x}: %{y:.2f}% of GDP<extra></extra>"))  # fmt: skip
    f2.update_layout(title=f"{country}: military expenditure, % of GDP", yaxis_title="% of GDP",
                     xaxis=dict(range=[y0 - 0.5, y1 + 0.5]), hovermode="closest")  # fmt: skip
    f2.update_yaxes(rangemode="tozero")
    b.plotly_chart(_finish(f2, d_src["data_status"] == "synthetic", 340), width="stretch")
    b.caption(f"Source: {d_src['name']}.")
    if (c_src["data_status"] == "synthetic") != (d_src["data_status"] == "synthetic"):
        st.warning("One of the two panels shows synthetic data. Do not read them together.")

    st.divider()
    st.markdown("#### Responsible use")
    st.markdown(
        "This is a public-data research and descriptive analytics project. It is **not** an "
        "operational targeting tool, an authoritative intelligence product, or a conflict "
        "prediction model. Event locations are reported approximations, aggregated for "
        "pattern analysis; they must not be used to locate people or plan operations."
    )
