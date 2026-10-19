"""Plotly figure builders. Inputs are tidy frames from ``src.analysis``.

Every builder takes ``synthetic`` and stamps a watermark when True, so a
screenshot of demo data can never be mistaken for a real-world chart.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.visualization.theme import (
    DIVERGING,
    INK_2,
    MUTED,
    OTHER,
    SEQ_BLUE,
    SERIES,
    TEMPLATE,
    color_map,
)

WATERMARK = "SYNTHETIC DEMO DATA"


def _finish(fig: go.Figure, synthetic: bool, height: int = 380) -> go.Figure:
    fig.update_layout(template=TEMPLATE, height=height)
    if synthetic:
        fig.add_annotation(
            text=WATERMARK, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(size=34, color="rgba(227,73,72,0.16)"), textangle=-12,
        )  # fmt: skip
    return fig


def fold_other(df: pd.DataFrame, col: str, weight: str = "events", keep: int = 7) -> pd.DataFrame:
    """Keep the ``keep`` largest categories by total ``weight``; fold the rest into Other."""
    top = df.groupby(col)[weight].sum().nlargest(keep).index
    out = df.copy()
    out[col] = out[col].where(out[col].isin(top), "Other")
    return out


def events_over_time(tc: pd.DataFrame, by: str | None, freq: str, synthetic: bool) -> go.Figure:
    if by:
        tc = fold_other(tc, by)
        tc = tc.groupby(["period", by], as_index=False)["events"].sum()
        cmap = color_map(tc[by].unique().tolist())
        fig = px.line(tc, x="period", y="events", color=by, color_discrete_map=cmap,
                      labels={"period": "", "events": f"Recorded events per {freq.lower()}", by: ""})  # fmt: skip
    else:
        fig = px.line(tc, x="period", y="events", color_discrete_sequence=[SERIES[0]],
                      labels={"period": "", "events": f"Recorded events per {freq.lower()}"})  # fmt: skip
    fig.update_traces(line=dict(width=2), hovertemplate="%{y:,} events")
    fig.update_layout(title=f"Recorded events per {freq.lower()}")
    fig.update_yaxes(rangemode="tozero")
    return _finish(fig, synthetic)


def fatalities_over_time(tc: pd.DataFrame, freq: str, kind: str, synthetic: bool,
                         low_high: pd.DataFrame | None = None) -> go.Figure:  # fmt: skip
    """Fatalities per period; for UCDP the low-high estimate range is shaded."""
    fig = go.Figure()
    if low_high is not None and not low_high.empty:
        fig.add_trace(go.Scatter(x=low_high["period"], y=low_high["high"], mode="lines",
                                 line=dict(width=0), hoverinfo="skip", showlegend=False))  # fmt: skip
        fig.add_trace(go.Scatter(
            x=low_high["period"], y=low_high["low"], mode="lines", line=dict(width=0),
            fill="tonexty", fillcolor="rgba(42,120,214,0.15)", name="Low-high estimate range",
            hovertemplate="low %{y:,.0f}<extra></extra>",
        ))  # fmt: skip
    label = "Best estimate" if kind == "estimate" else "Reported fatalities"
    fig.add_trace(go.Scatter(x=tc["period"], y=tc["fatalities"], mode="lines", name=label,
                             line=dict(width=2, color=SERIES[0]),
                             hovertemplate="%{y:,.0f}<extra>" + label + "</extra>"))  # fmt: skip
    noun = "Estimated" if kind == "estimate" else "Reported"
    fig.update_layout(title=f"{noun} fatalities per {freq.lower()}",
                      yaxis_title=f"{noun} fatalities", showlegend=low_high is not None)  # fmt: skip
    fig.update_yaxes(rangemode="tozero")
    return _finish(fig, synthetic)


def horizontal_bar(df: pd.DataFrame, label: str, value: str, title: str, axis_title: str,
                   synthetic: bool, fmt: str = ",.0f", top: int = 15) -> go.Figure:  # fmt: skip
    d = df.head(top).iloc[::-1]
    fig = go.Figure(go.Bar(
        x=d[value], y=d[label], orientation="h", marker=dict(color=SERIES[0], cornerradius=4),
        hovertemplate="%{y}: %{x:" + fmt + "}<extra></extra>",
    ))  # fmt: skip
    fig.update_layout(title=title, xaxis_title=axis_title, hovermode="closest", bargap=0.25)
    return _finish(fig, synthetic, height=max(260, 26 * len(d) + 90))


def completeness(cot: pd.DataFrame, synthetic: bool) -> go.Figure:
    """Shares (0-100%) of record-quality attributes per period - one unit, one axis."""
    series = {
        "share_precise_location": "Precisely located",
        "share_date_uncertain": "Date uncertain",
        "share_with_fatality_data": "Fatality figure present",
    }
    fig = go.Figure()
    for (col, name), colr in zip(series.items(), SERIES):
        if col in cot and cot[col].notna().any():
            fig.add_trace(go.Scatter(x=cot["period"], y=cot[col] * 100, name=name, mode="lines",
                                     line=dict(width=2, color=colr),
                                     hovertemplate="%{y:.1f}%<extra>" + name + "</extra>"))  # fmt: skip
    fig.update_layout(title="Record completeness over time (share of events)", yaxis_title="% of events")
    fig.update_yaxes(range=[0, 101])
    return _finish(fig, synthetic, height=340)


def sources_per_event(cot: pd.DataFrame, synthetic: bool) -> go.Figure | None:
    if "mean_sources_per_event" not in cot or cot["mean_sources_per_event"].isna().all():
        return None
    fig = go.Figure(go.Scatter(x=cot["period"], y=cot["mean_sources_per_event"], mode="lines+markers",
                               line=dict(width=2, color=SERIES[6]), marker=dict(size=8),
                               hovertemplate="%{y:.2f} sources per event<extra></extra>"))  # fmt: skip
    fig.update_layout(title="Mean number of source reports per event", yaxis_title="Sources per event")
    fig.update_yaxes(rangemode="tozero")
    return _finish(fig, synthetic, height=300)


def event_map(df: pd.DataFrame, mode: str, synthetic: bool, max_points: int = 25_000) -> go.Figure:
    """Point or density map of located events (MapLibre, no token needed)."""
    d = df.dropna(subset=["latitude", "longitude"]).copy()
    d["latitude"], d["longitude"] = d["latitude"].astype(float), d["longitude"].astype(float)
    center = dict(lat=float(d["latitude"].median()), lon=float(d["longitude"].median())) if len(d) else dict(lat=50, lon=20)
    if mode == "Density":
        fig = px.density_map(d, lat="latitude", lon="longitude", radius=6, zoom=3.4, center=center,
                             color_continuous_scale=SEQ_BLUE, map_style="carto-positron")  # fmt: skip
        fig.update_traces(hovertemplate="%{lat:.2f}, %{lon:.2f}<extra></extra>")
        fig.update_coloraxes(colorbar=dict(title="Relative<br>density", tickvals=[]))
    else:
        if len(d) > max_points:
            d = d.sample(max_points, random_state=0)
        d["fatalities_txt"] = d["fatalities"].astype(object).where(d["fatalities"].notna(), "not reported")
        d["date_txt"] = d["event_date"].dt.strftime("%Y-%m-%d")
        cmap = color_map(d["event_type"].dropna().unique().tolist())
        fig = px.scatter_map(
            d, lat="latitude", lon="longitude", color="event_type", color_discrete_map=cmap,
            zoom=3.4, center=center, map_style="carto-positron", opacity=0.75,
            custom_data=["date_txt", "event_type", "country", "admin1", "fatalities_txt"],
        )  # fmt: skip
        fig.update_traces(
            marker=dict(size=8),
            hovertemplate="<b>%{customdata[1]}</b><br>%{customdata[0]} · %{customdata[2]}, "
            "%{customdata[3]}<br>Fatalities: %{customdata[4]}<extra></extra>",
        )
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), legend=dict(y=0.02, x=0.01, bgcolor="rgba(255,255,255,0.85)"),
                      hovermode="closest")  # fmt: skip
    return _finish(fig, synthetic, height=560)


# ------------------------------------------------------------------ defence charts


def milex_lines(df: pd.DataFrame, y_title: str, title: str, synthetic: bool,
                baseline: float | None = None, cmap: dict | None = None) -> go.Figure:  # fmt: skip
    # The caller passes a persistent colour registry so countries keep their colour.
    cmap = cmap or color_map(sorted(df["country"].unique().tolist()))
    fig = px.line(df, x="year", y="value", color="country", color_discrete_map=cmap,
                  labels={"year": "", "value": y_title, "country": ""})  # fmt: skip
    fig.update_traces(line=dict(width=2), hovertemplate="%{y:,.2f}")
    est = df[df["value_flag"].isin(["estimate", "highly_uncertain"])]
    if len(est):
        fig.add_trace(go.Scatter(
            x=est["year"], y=est["value"], mode="markers", name="SIPRI estimate / uncertain",
            marker=dict(symbol="circle-open", size=8, color=INK_2, line=dict(width=1.5)),
            hoverinfo="skip",
        ))  # fmt: skip
    if baseline is not None:
        fig.add_hline(y=baseline, line=dict(color=MUTED, width=1, dash="dot"))
    fig.update_layout(title=title)
    return _finish(fig, synthetic, height=420)


def milex_ranking(df: pd.DataFrame, x_title: str, title: str, synthetic: bool, fmt: str) -> go.Figure:
    d = df.iloc[::-1]
    est = d["value_flag"].isin(["estimate", "highly_uncertain"])
    fig = go.Figure(go.Bar(
        x=d["value"], y=d["country"], orientation="h",
        marker=dict(color=SERIES[0], cornerradius=4, pattern=dict(shape=["/" if e else "" for e in est],
                    fgcolor="white", solidity=0.35)),
        customdata=d["value_flag"],
        hovertemplate="%{y}: %{x:" + fmt + "}<br>%{customdata}<extra></extra>",
    ))  # fmt: skip
    fig.update_layout(title=title, xaxis_title=x_title, hovermode="closest", bargap=0.25)
    return _finish(fig, synthetic, height=max(280, 22 * len(d) + 100))


def change_bars(df: pd.DataFrame, col: str, x_title: str, title: str, synthetic: bool) -> go.Figure:
    d = df.iloc[::-1]
    colors = [DIVERGING["pos"] if v >= 0 else DIVERGING["neg"] for v in d[col]]
    fig = go.Figure(go.Bar(x=d[col], y=d["country"], orientation="h",
                           marker=dict(color=colors, cornerradius=4),
                           hovertemplate="%{y}: %{x:+,.1f}<extra></extra>"))  # fmt: skip
    fig.add_vline(x=0, line=dict(color=MUTED, width=1))
    fig.update_layout(title=title, xaxis_title=x_title, hovermode="closest", bargap=0.25)
    return _finish(fig, synthetic, height=max(280, 22 * len(d) + 100))


def threshold_counts(df: pd.DataFrame, threshold: float, synthetic: bool) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["year"], y=df["countries_with_data"], name="Countries with data",
                         marker=dict(color=OTHER, opacity=0.35, cornerradius=3)))  # fmt: skip
    fig.add_trace(go.Bar(x=df["year"], y=df["countries_at_or_above"],
                         name=f"Countries at or above {threshold:g}% of GDP",
                         marker=dict(color=SERIES[0], cornerradius=3)))  # fmt: skip
    fig.update_layout(barmode="overlay", title=f"European countries with military expenditure ≥ {threshold:g}% of GDP",
                      yaxis_title="Number of countries", bargap=0.2)  # fmt: skip
    return _finish(fig, synthetic, height=360)


# ------------------------------------------------------------- research charts


def event_study_chart(es: pd.DataFrame, y_title: str, title: str) -> go.Figure:
    """Year-by-year gradient with 95% CIs; base year at zero by construction."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=es["year"], y=es["coef"], mode="lines+markers", name="Estimate",
        line=dict(width=2, color=SERIES[0]), marker=dict(size=8, color=SERIES[0]),
        error_y=dict(type="data", symmetric=False, array=es["hi"] - es["coef"],
                     arrayminus=es["coef"] - es["lo"], color=SERIES[0], thickness=1.2, width=0),
        customdata=es[["lo", "hi"]],
        hovertemplate="%{x}: %{y:.3f}<br>95% CI %{customdata[0]:.3f} to %{customdata[1]:.3f}<extra></extra>",
    ))  # fmt: skip
    fig.add_hline(y=0, line=dict(color=MUTED, width=1))
    for x, label in [(2014, "Crimea annexed"), (2022, "Full-scale invasion")]:
        fig.add_vline(x=x - 0.5, line=dict(color=MUTED, width=1, dash="dot"))
        fig.add_annotation(x=x - 0.5, y=1, yref="paper", text=label, showarrow=False, xanchor="left",
                           font=dict(size=11, color=INK_2), xshift=4)  # fmt: skip
    fig.update_layout(title=title, yaxis_title=y_title, hovermode="closest", showlegend=False)
    return _finish(fig, False, height=420)


# Hand-placed label positions where neighbouring points would collide.
LABEL_POS = {"LVA": "middle left", "POL": "middle right", "LTU": "bottom right", "EST": "middle right",
             "FIN": "middle right", "GBR": "middle right", "FRA": "top center",
             "DEU": "bottom center"}  # fmt: skip


def distance_scatter(raw: pd.DataFrame, label_iso: set[str]) -> go.Figure:
    """Raw change in % of GDP 2013-2025 against distance; a few points labelled."""
    lab = raw["iso3"].isin(label_iso)
    fig = go.Figure(go.Scatter(
        x=raw["dist"] * 1000, y=raw["change_pp"], mode="markers+text",
        text=raw["country"].where(lab, ""), textfont=dict(size=11, color=INK_2),
        textposition=[LABEL_POS.get(i, "top center") for i in raw["iso3"]],
        marker=dict(size=10, color=SERIES[0], line=dict(color="white", width=2)),
        customdata=raw["country"],
        hovertemplate="%{customdata}<br>%{x:,.0f} km from Russia<br>%{y:+.2f} pp<extra></extra>",
    ))  # fmt: skip
    fig.add_hline(y=0, line=dict(color=MUTED, width=1))
    fig.update_layout(title="Change in military expenditure, % of GDP, 2013–2025",
                      xaxis_title="Distance from capital to Russia (km, Crimea excluded)",
                      yaxis_title="Change (percentage points)", hovermode="closest")  # fmt: skip
    return _finish(fig, False, height=440)


# ------------------------------------------------------------- hot-spot maps

HOTSPOT_COLORS = {
    "Hot spot (FDR 1%)": "#b42318",
    "Hot spot (FDR 5%)": "#e34948",
    "Hot spot (FDR 10%)": "#f4a3a2",
    "Cold spot (FDR 1%)": "#104281",
    "Cold spot (FDR 5%)": "#3987e5",
    "Cold spot (FDR 10%)": "#9ec5f4",
    "Not significant, with events": "#c3c2b7",
}
TREND_COLORS = {"Persistent": "#b42318", "Intermittent": "#eb6834", "New": "#6250d6",
                "Diminishing": "#2a78d6"}  # fmt: skip


def _focus(cells, quantile: float = 0.05) -> tuple[dict, float]:
    """Centre and zoom on the bulk of the drawn cells (5th-95th percentile extent),
    so a few isolated cells far away do not pull the view off the main cluster."""
    import numpy as np

    if cells.empty:
        return dict(lon=20.0, lat=50.0), 3.5
    c = cells.to_crs("EPSG:3035").geometry.centroid.to_crs("EPSG:4326")
    lo_x, hi_x = np.quantile(c.x, [quantile, 1 - quantile])
    lo_y, hi_y = np.quantile(c.y, [quantile, 1 - quantile])
    span = max(hi_x - lo_x, (hi_y - lo_y) * 1.6, 1.5)
    zoom = float(np.clip(np.log2(360 / span) - 0.6, 3, 9))
    return dict(lon=float((lo_x + hi_x) / 2), lat=float((lo_y + hi_y) / 2)), zoom


def _cell_map(cells, color_col: str, cmap: dict, hover: list[str], synthetic: bool,
              outline=None) -> go.Figure:  # fmt: skip
    cells = cells.reset_index(drop=True)
    center, zoom = _focus(cells)
    fig = px.choropleth_map(
        cells, geojson=cells.geometry.__geo_interface__, locations=cells.index, color=color_col,
        color_discrete_map=cmap, category_orders={color_col: list(cmap)}, map_style="carto-positron",
        center=center, zoom=zoom, opacity=0.8, hover_data={h: True for h in hover},
    )  # fmt: skip
    fig.update_traces(marker_line_width=0)
    if outline is not None:
        for poly in getattr(outline, "geoms", [outline]):
            for ring in [poly.exterior]:
                xs, ys = ring.xy
                fig.add_trace(go.Scattermap(lon=list(xs), lat=list(ys), mode="lines", hoverinfo="skip",
                                            line=dict(width=1, color=MUTED), showlegend=False))  # fmt: skip
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), hovermode="closest",
                      legend=dict(y=0.02, x=0.01, bgcolor="rgba(255,255,255,0.88)", title=None))  # fmt: skip
    return _finish(fig, synthetic, height=560)


def hotspot_map(cells, synthetic: bool) -> go.Figure:
    """Gi* classes. Zero-count non-significant cells are not drawn; the study area is outlined."""
    import shapely

    show = cells[cells["cls"] != "Not significant"].copy()
    rest = cells[(cells["cls"] == "Not significant") & (cells["events"] > 0)].copy()
    rest["cls"] = "Not significant, with events"
    d = pd.concat([show, rest])
    d["events"] = d["events"].astype(int)
    d["z"] = d["z"].round(2)
    d["p_fdr"] = d["p_fdr"].round(4)
    outline = shapely.union_all(cells.geometry.values).simplify(0.02)
    return _cell_map(d, "cls", HOTSPOT_COLORS, ["events", "z", "p_fdr"], synthetic, outline)


def trend_map(cells, synthetic: bool) -> go.Figure:
    import shapely

    d = cells[cells["trend"] != "Never hot"].copy()
    outline = shapely.union_all(cells.geometry.values).simplify(0.02)
    return _cell_map(d, "trend", TREND_COLORS, ["years_hot"], synthetic, outline)


def active_area_chart(ma: pd.DataFrame, synthetic: bool) -> go.Figure:
    fig = go.Figure(go.Scatter(x=ma["month"], y=ma["active_area_km2"] / 1000, mode="lines",
                               line=dict(width=2, color=SERIES[0]), customdata=ma[["events", "active_cells"]],
                               hovertemplate="%{x|%b %Y}: %{y:,.1f}k km²<br>%{customdata[1]} cells, "
                               "%{customdata[0]:,} events<extra></extra>"))  # fmt: skip
    fig.update_layout(title="Area with recorded events, per month", yaxis_title="Thousand km²",
                      hovermode="closest")  # fmt: skip
    fig.update_yaxes(rangemode="tozero")
    return _finish(fig, synthetic, height=340)


def permutation_hist(null: list[float], observed: float, title: str) -> go.Figure:
    fig = go.Figure(go.Histogram(x=null, nbinsx=60, marker=dict(color=OTHER, line=dict(color="white", width=1)),
                                 hovertemplate="%{x:.3f}: %{y} permutations<extra></extra>"))  # fmt: skip
    fig.add_vline(x=observed, line=dict(color=SERIES[7], width=2))
    fig.add_annotation(x=observed, y=1, yref="paper", text=f"observed {observed:+.2f}", showarrow=False,
                       xanchor="left", xshift=6, font=dict(color=INK_2, size=12))  # fmt: skip
    lo, hi = min(min(null), observed), max(max(null), observed)
    pad = (hi - lo) * 0.06
    fig.update_xaxes(range=[lo - pad, hi + pad])
    fig.update_layout(title=title, xaxis_title="Gradient under random assignment of distances (pp per 1,000 km)",
                      yaxis_title="Permutations", hovermode="closest", bargap=0.02)  # fmt: skip
    return _finish(fig, False, height=320)


def synth_chart(years: list[int], actual: list[float], synthetic: list[float], name: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=years, y=actual, name=name, mode="lines", line=dict(width=2, color=SERIES[0]),
                             hovertemplate="%{x}: %{y:.2f}%<extra>" + name + "</extra>"))  # fmt: skip
    fig.add_trace(go.Scatter(x=years, y=synthetic, name=f"Synthetic {name}", mode="lines",
                             line=dict(width=2, color=MUTED, dash="dash"),
                             hovertemplate="%{x}: %{y:.2f}%<extra>synthetic</extra>"))  # fmt: skip
    for x in (2014, 2022):
        fig.add_vline(x=x - 0.5, line=dict(color=MUTED, width=1, dash="dot"))
    fig.update_layout(title=f"{name}: actual vs synthetic military burden", yaxis_title="% of GDP",
                      hovermode="x unified")  # fmt: skip
    fig.update_yaxes(rangemode="tozero")
    return _finish(fig, False, height=360)
