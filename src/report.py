"""Generate the research brief (reports/RESEARCH_BRIEF.md) and its figures.

All numbers in the brief are computed here from the database at generation
time. The interpretive commentary was written after examining one specific
data version; the brief records that version's file hashes and prints a
visible warning if the data have changed since, so stale interpretation is
never silently presented as current.

If only synthetic data are available, a clearly labelled DEMONSTRATION brief is
produced instead, containing no claims about real-world conditions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from src.analysis import conflict as C
from src.analysis import defence as D
from src.analysis import spatial as S
from src.config import FIGURES_DIR, REPORTS_DIR
from src.database import queries as Q
from src.database.db import connect
from src.visualization import charts as V
from src.visualization.theme import SERIES

# SHA-256 prefixes of the input files the commentary was written against.
REVIEWED = {"ucdp_ged": "8c941d84954e555e", "sipri_milex": "6cc3a30b1064f9f0"}


def _save(fig: go.Figure, name: str, width: int = 900, height: int = 420) -> str:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.write_html(FIGURES_DIR / f"{name}.html", include_plotlyjs="cdn")
    try:  # static export needs kaleido + a local Chrome; HTML is always written
        fig.update_layout(paper_bgcolor="white", plot_bgcolor="white")
        fig.write_image(FIGURES_DIR / f"{name}.png", width=width, height=height, scale=2)
        return f"figures/{name}.png"
    except Exception:  # pragma: no cover - environment dependent
        return f"figures/{name}.html"


def _pct(x: float, d: int = 0) -> str:
    return f"{x * 100:.{d}f}%"


def _n(x: float) -> str:
    return f"{x:,.0f}"


# ---------------------------------------------------------------- conflict part


def conflict_section(con, synthetic: bool, src: str) -> tuple[str, dict]:
    ev = Q.events(con, src)
    yr = ev.groupby("year").agg(
        events=("event_id", "size"), best=("fatalities", "sum"),
        low=("fatalities_low", "sum"), high=("fatalities_high", "sum"),
    ).reset_index()  # fmt: skip
    yr = yr.set_index("year").reindex(range(int(yr["year"].min()), int(yr["year"].max()) + 1)).fillna(0).reset_index()

    f1 = go.Figure(go.Bar(x=yr["year"], y=yr["events"], marker=dict(color=SERIES[0], cornerradius=3)))
    f1.update_layout(title="Recorded events per year, UCDP GED, Europe", yaxis_title="Recorded events")
    p1 = _save(V._finish(f1, synthetic), "conflict_events_per_year")

    lh = yr.rename(columns={"year": "period"})
    tc = lh.rename(columns={"best": "fatalities"})
    f2 = V.fatalities_over_time(tc, "Year", "estimate", synthetic, lh)
    f2.update_layout(title="Estimated fatalities per year (best, with low-high range)")
    p2 = _save(f2, "conflict_fatalities_per_year")

    recent = ev[ev["year"] >= 2010]
    cot = C.completeness_over_time(recent, "Year")
    p3 = _save(V.completeness(cot, synthetic), "conflict_completeness")

    w = ev[ev["year"] >= 2022]
    y = yr.set_index("year")
    last = int(y.index.max())
    share_ukr = (w["country"] == "Ukraine").mean()
    by_conf = C.category_summary(w, "conflict_name")
    top_conf = by_conf.iloc[0]
    rus = w[w["country"] == "Russia"].groupby("year").size()
    cot_i = cot.set_index(cot["period"].dt.year)
    conc = S.concentration(S.located(w, precise_only=True), 0.5, 10)
    fpe = (y["best"] / y["events"]).loc[2022:last]
    peak_90s = y.loc[1991:1999, "events"].idxmax()
    bih_90s = ev[(ev["year"].between(1991, 1999)) & (ev["country"] == "Bosnia and Herzegovina")]
    az20 = ev[(ev["year"] == 2020) & (ev["country"] == "Azerbaijan")]
    elsewhere = (ev["coord_check"] == "elsewhere").sum()

    facts = {
        "events_total": len(ev), "date_min": ev["event_date"].min().date(), "date_max": ev["event_date"].max().date(),
        "events_2022_on": len(w), "share_ukr": share_ukr, "top_conf": top_conf["conflict_name"],
        "top_conf_share": top_conf["share_of_events"],
    }  # fmt: skip

    md = f"""
### A1. Coverage

UCDP GED v26.1 contains **{_n(len(ev))} European events** dated {facts['date_min']} to
{facts['date_max']}, in {ev['country'].nunique()} countries (UCDP's historical state coding).
Every event has at least one estimated death, because UCDP includes only conflicts that
cross 25 battle-related deaths in a year. Protests, riots and non-lethal incidents are out of
scope by design.

![Recorded events per year]({p1})

### A2. Descriptive findings

1. **Two eras dominate the record.** The 1991–1999 wars in the former Yugoslavia peak in
   {peak_90s} with {_n(y.loc[peak_90s, 'events'])} recorded events; {_n(len(bih_90s))} of the
   1991–99 events are coded to Bosnia and Herzegovina. From 2022 the Russia–Ukraine war
   produces more recorded events per year than any earlier year in the series:
   {_n(y.loc[2022, 'events'])} in 2022, {_n(y.loc[2023, 'events'])} in 2023,
   {_n(y.loc[2024, 'events'])} in 2024 and {_n(y.loc[last, 'events'])} in {last}.
2. **Recent European conflict events are almost entirely one conflict.** Of
   {_n(len(w))} events since 2022, {_pct(share_ukr, 1)} are located in Ukraine, and
   {_pct(top_conf['share_of_events'], 1)} belong to the UCDP conflict "{top_conf['conflict_name']}".
   {_pct((w['event_type'] == 'State-based conflict').mean(), 1)} are state-based conflict events. Any
   Europe-wide aggregate for this period is therefore effectively a Ukraine aggregate.
3. **Events recorded inside Russia rose** from {_n(rus.get(2022, 0))} in 2022 to
   {_n(rus.get(2024, 0))} in 2024 and {_n(rus.get(last, 0))} in {last}. The data record *where* events
   were located. They do not by themselves explain why the location changed.
4. **Fatality estimates are wide.** For 2022 the summed best estimate is
   {_n(y.loc[2022, 'best'])}, within a low–high range of {_n(y.loc[2022, 'low'])} to
   {_n(y.loc[2022, 'high'])}. The high estimate is {y.loc[2022, 'high'] / y.loc[2022, 'low']:.1f}×
   the low. Point estimates for an active war should not be quoted without this band.
5. **Fatality peaks need not coincide with event peaks.** In 2020, {_n(len(az20))} events coded to
   Azerbaijan carry {_n(az20['fatalities'].sum())} estimated deaths
   ({_pct(az20['fatalities'].sum() / max(y.loc[2020, 'best'], 1))} of Europe's 2020 total), so a small
   number of very lethal events dominates that year.
6. **Spatial concentration.** Since 2022, {_pct(conc['share_in_top_cells'])} of precisely located
   events fall in the 10 busiest of {conc['cells_with_events']} occupied 0.5° grid cells
   (roughly 35 × 55 km each). This reflects frontline intensity together with UCDP's practice of
   locating events at the nearest identifiable place.

![Estimated fatalities per year]({p2})

### A3. Reporting and data-quality signals

- **The latest year is coded differently.** Recorded events fall from {_n(y.loc[2024, 'events'])} (2024)
  to {_n(y.loc[last, 'events'])} ({last}), but summed best fatalities move from
  {_n(y.loc[2024, 'best'])} to {_n(y.loc[last, 'best'])}. Fatalities per event rise from
  {fpe.loc[2024]:.1f} to {fpe.loc[last]:.1f}. At the same time, the share of events with an
  uncertain date falls from {_pct(cot_i.loc[2024, 'share_date_uncertain'])} to
  {_pct(cot_i.loc[last, 'share_date_uncertain'], 1)}, and precisely located events fall from
  {_pct(cot_i.loc[2024, 'share_precise_location'])} to {_pct(cot_i.loc[last, 'share_precise_location'])}.
  Together these point to a change in how events were aggregated or coded, so **the fall in
  {last} event counts should not be read as a fall in violence**. Comparisons across the
  2024/{last} boundary should use fatalities (with ranges) as well as counts, and be re-checked
  against the next UCDP release.
- **Location precision varies by year.** For example, only {_pct(cot_i.loc[2013, 'share_precise_location'])}
  of 2013 events are precisely located, against {_pct(cot_i.loc[2014, 'share_precise_location'])} in 2014.
- **Sources per event** fall from {cot_i.loc[2022, 'mean_sources_per_event']:.2f} (2022) to
  {cot_i.loc[last, 'mean_sources_per_event']:.2f} ({last}). Fewer independent reports per event mean
  less corroboration.
- **Historical coding.** {_n(elsewhere)} events ({_pct(elsewhere / len(ev), 1)}) fall more than 10 km
  outside the stated country's present-day border. Almost all are 1989–1999 events coded to
  "Serbia (Yugoslavia)" or "Russia (Soviet Union)", plus contested areas. This is a property of the
  coding system, not an error, but it matters for any present-day country filter.

![Record completeness]({p3})
"""
    return md, facts


# --------------------------------------------------------------- hot spots


def hotspot_section(con, start: str = "2022-01-01") -> str:
    from src.analysis import hotspots as H

    ev = Q.events(con, "ucdp_ged", start=pd.Timestamp(start).date())
    sens = []
    for k in (10, 25, 50):
        cells, s = H.hotspots(ev, k)
        sens.append(s)
        if k == 25:
            main_cells, main = cells, s
    tcells, per_year = H.hotspot_trend(ev, 25)
    active = H.monthly_active_area(ev, 25)
    p1 = _save(V.hotspot_map(main_cells, False), "hotspots_gi_star_2022_2025", width=1000, height=640)
    p2 = _save(V.trend_map(tcells, False), "hotspots_trend_2022_2025", width=1000, height=640)
    p3 = _save(V.active_area_chart(active, False), "hotspots_active_area")
    tc = tcells["trend"].value_counts()
    a = active.assign(year=active["month"].dt.year).groupby("year")["active_area_km2"].median()
    srows = "\n".join(
        f"| {s['cell_km']} km | {s['cells']:,} | {s['study_area_km2'] / 1000:,.0f}k | {s['hot_cells']} | "
        f"{s['hot_area_km2'] / 1000:,.1f}k | {s['share_events_in_hot_cells'] * 100:.0f}% |"
        for s in sens
    )
    yrows = "\n".join(f"| {int(r.year)} | {int(r.hot_cells)} | {r.hot_area_km2 / 1000:,.1f}k |" for r in per_year.itertuples())
    return f"""
### A4. Where recorded violence clusters: hot spots, 2022–2025

Getis-Ord Gi* on counts of precisely located UCDP events per cell of an **equal-area grid**
(EPSG:3035), with the 8 neighbouring cells plus the cell itself. The study area is land within
100 km of any recorded event, and **cells with no events are included**. P-values are adjusted for
the thousands of simultaneous tests with the Benjamini–Hochberg false discovery rate. Validated
against PySAL's `esda.G_Local` to 1e-10. {main['events_excluded_imprecise']:,} events located only
to a region or country are excluded, because UCDP places them at centroids, which would create
artificial hot spots.

![Gi* hot spots]({p1})

- At 25 km, **{main['hot_cells']} cells ({main['hot_area_km2'] / 1000:,.0f}k km², {main['hot_area_km2'] / main['study_area_km2'] * 100:.1f}% of the study area) hold
  {main['share_events_in_hot_cells'] * 100:.0f}% of the {main['events_used']:,} located events.** Recorded violence is
  overwhelmingly concentrated along a narrow band, not spread across the country.
- **The result depends on the cell size (MAUP), so it is reported for three sizes:**

| Cell | Cells | Study area (km²) | Hot cells | Hot area (km²) | Events in hot cells |
|---|---|---|---|---|---|
{srows}

  Finer cells find smaller, more numerous hot spots. The concentration finding holds at every size.

- **Year by year, on a fixed grid** (hot at FDR 5%):

| Year | Hot cells | Hot area (km²) |
|---|---|---|
{yrows}

  Of the cells that were ever hot: {tc.get('Persistent', 0)} persistent (hot every year), {tc.get('Intermittent', 0)} intermittent,
  {tc.get('New', 0)} new in {per_year['year'].max()} and {tc.get('Diminishing', 0)} diminishing (hot earlier, not in {per_year['year'].max()}).
  The hot-spot geography shifts over time rather than staying fixed. The {per_year['year'].max()} figure should be
  read alongside the coding change noted in A3: fewer, more aggregated events in the latest year
  change what each cell's count means.

![Hot-spot history]({p2})

- **Monthly area with recorded events** (25 km cells): median {a.iloc[0] / 1000:,.0f}k km² per month in
  {a.index[0]} and {a.iloc[-1] / 1000:,.0f}k km² in {a.index[-1]}. This measures the *spread of recorded activity*,
  not the front line or territorial control, and it moves with reporting as well as with fighting.

![Active area]({p3})

**Limitations.** Hot spots are clusters of *recorded* events and inherit UCDP's reporting coverage.
Areas with little access or media presence can look quiet. Cold spots almost never occur with counts
dominated by zeros, so their absence is not a finding. The statistic is computed on event counts, not
fatalities, so a hot spot describes how often violence is recorded, not how lethal it is.
"""


# ---------------------------------------------------------------- defence part


def defence_section(con, synthetic: bool, src: str) -> tuple[str, dict]:
    k = Q.milex(con, src, "milex_constant_usd_m")
    g = Q.milex(con, src, "share_gdp_pct")
    last = int(k.dropna(subset=["value"])["year"].max())
    first = 2014 if (k["year"] == 2014).any() else int(k["year"].min())

    bt = D.balanced_total(k, 2000, last)
    ex = D.balanced_total(k[~k["country"].isin(["Russia", "Ukraine"])], 2000, last)
    f = go.Figure()
    f.add_trace(go.Scatter(x=bt["totals"].index, y=bt["totals"] / 1000, name=f"All ({len(bt['included'])} countries)",
                           mode="lines", line=dict(width=2, color=SERIES[0])))  # fmt: skip
    f.add_trace(go.Scatter(x=ex["totals"].index, y=ex["totals"] / 1000, name="Excluding Russia and Ukraine",
                           mode="lines", line=dict(width=2, color=SERIES[1])))  # fmt: skip
    f.update_layout(title="European military expenditure, balanced panel, constant (2024) US$ bn",
                    yaxis_title="US$ bn, constant 2024 prices")  # fmt: skip
    f.update_yaxes(rangemode="tozero")
    p1 = _save(V._finish(f, synthetic), "defence_total_constant")

    tc = D.count_at_or_above(g, 2.0)
    tc = tc[tc["year"] >= 2000]
    p2 = _save(V.threshold_counts(tc, 2.0, synthetic), "defence_gdp_threshold")

    ch = D.change_between(g, first, last)
    p3 = _save(V.change_bars(ch.head(15), "change_pp", "Change, percentage points",
                             f"Largest increases in military expenditure as % of GDP, {first}–{last}", synthetic),
               "defence_gdp_change", height=520)  # fmt: skip

    def chg(b, a, z):
        t = b["totals"]
        return t.loc[z] / t.loc[a] - 1

    lv = D.latest_values(k, last)
    est = lv[lv["value_flag"] != "reported"]["country"].tolist()
    tci = tc.set_index("year")
    gl = g[g["year"] == last].dropna(subset=["value"])
    gf = g[g["year"] == first].dropna(subset=["value"])
    top5 = ", ".join(f"{r.country} (+{r.change_pp:.1f} pp)" for r in ch.head(5).itertuples())
    falls = ch[ch["change_pp"] < 0]
    facts = {"growth_all": chg(bt, first, last), "count_2pct_last": int(tci.loc[last, "countries_at_or_above"])}

    md = f"""
### B1. Coverage

SIPRI's European series cover {len(bt['included'])} countries with constant-price data in every year
from 2000 to {last}, the balanced panel used for totals. Values for {', '.join(est) or 'no countries'}
in {last} are SIPRI estimates. Military expenditure follows SIPRI's definition, which is broader than
some national budget lines and differs from NATO's.

![Total expenditure]({p1})

### B2. Descriptive findings

1. **Real expenditure has more than doubled since {first}.** The balanced-panel total in constant
   2024 US$ rises by {_pct(chg(bt, first, last))} from {first} to {last}, and by
   {_pct(chg(bt, 2021, last))} since 2021. Excluding Russia and Ukraine, whose {last} figures are
   estimates, the increases are {_pct(chg(ex, first, last))} and {_pct(chg(ex, 2021, last))}.
   **The rise is not only driven by the war's two belligerents.**
2. **The latest annual increase is {_pct(chg(bt, last - 1, last), 1)}** in real terms from {last - 1}
   to {last} ({_pct(chg(ex, last - 1, last), 1)} excluding Russia and Ukraine). The year before, it
   was {_pct(chg(bt, last - 2, last - 1), 1)} ({_pct(chg(ex, last - 2, last - 1), 1)}).
3. **More countries spend at least 2% of GDP.** The count goes from {int(tci.loc[first, 'countries_at_or_above'])}
   of {int(tci.loc[first, 'countries_with_data'])} countries with data in {first} to
   {int(tci.loc[last, 'countries_at_or_above'])} of {int(tci.loc[last, 'countries_with_data'])} in {last}.
   The median share rises from {gf['value'].astype(float).median():.2f}% to
   {gl['value'].astype(float).median():.2f}% of GDP. Because SIPRI's definition differs from NATO's,
   this is not an assessment of NATO commitments.
4. **The largest burden increases are on the eastern flank and among belligerents:** {top5}.
   Ukraine's figure ({gl.set_index('country').loc['Ukraine', 'value']:.1f}% of GDP in {last}, an
   estimate) is of a different order and dominates any unweighted average. This is why medians
   are used. {len(falls)} of {len(ch)} countries record a lower share in {last} than in {first}.
5. **Levels are concentrated.** In {last} the five largest spenders ({', '.join(lv.head(5)['country'])})
   account for {_pct(lv.head(5)['value'].sum() / lv['value'].sum())} of the European total
   in constant US$.

![Threshold counts]({p2})

![Change in share of GDP]({p3})
"""
    return md, facts


# ---------------------------------------------------------------- research part


def research_section(con) -> str:
    from src import research as R

    if not R.available(con):
        return ""
    r = R.run(con)
    R.save(r)
    f = R.as_frames(r)
    from src.ui.page_research import LABELS

    p1 = _save(V.distance_scatter(f["raw"], LABELS), "research_distance_scatter", height=460)
    p2 = _save(V.event_study_chart(f["event_study"], "Gradient (pp of GDP per 1,000 km)",
                                   "Event study: gradient by year relative to 2013 (95% CI)"), "research_event_study")  # fmt: skip
    m, pt, lo, plc = r["main"], r["pretrend"], r["leave_one_out"], r["placebo_2009"]
    rob = f["robustness"].set_index("specification")
    cau = rob.loc["Including South Caucasus"]
    pv = lambda p: "< 0.001" if p < 0.001 else f"{p:.3f}"  # noqa: E731
    rows = "\n".join(
        f"| {k} | {v.post2014:+.3f} ({v.se_post2014:.3f}) | {pv(v.p_boot_post2014)} | "
        f"{v.post2022:+.3f} ({v.se_post2022:.3f}) | {pv(v.p_boot_post2022)} | {v.countries} |"
        for k, v in rob.iterrows()
    )
    return f"""
## 5. Research extension: does proximity to Russia predict military burden?

Design fixed in writing before estimation: [`docs/RESEARCH_DESIGN.md`](../docs/RESEARCH_DESIGN.md).
Two-way fixed-effects event study, {r['sample']['n_countries']} European countries, 2005–2025
({r['sample']['n_obs']} country-years). Exposure: distance from the capital to Russia's
internationally recognised territory, in 1,000 km. Russia, Ukraine, Belarus and Iceland are excluded,
and the South Caucasus is excluded from the main sample. Inference: cluster-robust by country and a
wild cluster bootstrap (9,999 draws, null imposed).

![Raw change by distance]({p1})

**Main estimates** (pp of GDP per 1,000 km farther from Russia; negative = closer countries rose more):

- After 2014: **{m['post2014']:+.2f}** (95% CI {m['ci_post2014'][0]:.2f} to {m['ci_post2014'][1]:.2f};
  bootstrap p {pv(m['p_boot_post2014'])}).
- Additional after 2022: **{m['post2022']:+.2f}** (95% CI {m['ci_post2022'][0]:.2f} to
  {m['ci_post2022'][1]:.2f}; bootstrap p {pv(m['p_boot_post2022'])}).
- Combined since 2022, a country 1,000 km closer to Russia raised its burden by about
  **{abs(m['post2014'] + m['post2022']):.1f} pp of GDP more**, relative to its own 2005–2013 level.

![Event study]({p2})

**Pre-trends.** The joint test that the 2005–2012 coefficients are zero
{'**rejects** at 5%' if pt['p'] < 0.05 else 'does not reject'} (F({pt['df1']}, {pt['df2']}) =
{pt['F']:.2f}, p = {pt['p']:.3f}). The pre-period coefficients are small (largest absolute value
{max(abs(x) for x in f['event_study'].query('year < 2013')['coef']):.2f}) next to the post-2022 ones,
but the post-2014 estimate should not be read as a clean break.

**Robustness** (coefficient (s.e.), bootstrap p):

| Specification | After 2014 | p | Extra after 2022 | p | Countries |
|---|---|---|---|---|---|
{rows}

Leave-one-out range for the post-2022 estimate: {lo['post2022_min']:+.2f} to {lo['post2022_max']:+.2f}
(most influential country: {lo['most_influential_2022']}). Placebo treatment in 2009:
{plc['coef']:+.3f}, bootstrap p {pv(plc['p_boot'])}.

**Interpretation.** The post-2022 gradient is the robust finding: it holds in levels and in shares,
with either exposure measure, with a NATO control, and without the Baltic states. The post-2014
gradient is weaker. Including the South Caucasus moves it to {cau['post2014']:+.2f} (p
{pv(cau['p_boot_post2014'])}), and the pre-trend test is not clean. None of this identifies *why*
closer countries spent more: distance is bundled with history, alliance position and threat
perception, and the estimate is a gradient in observed budgets, not the effect of moving a country.
"""


# -------------------------------------------------------------------- assembly


def _version_check(reg: pd.DataFrame) -> str:
    stale = []
    for src, sha in REVIEWED.items():
        row = reg[reg["source"] == src]
        if row.empty or not str(row.iloc[0]["sha256"]).startswith(sha):
            stale.append(src)
    if not stale:
        return ""
    return (
        "> ⚠️ **Data version changed.** The commentary below was written for earlier versions of "
        f"{', '.join(stale)}. All numbers are recomputed, but the interpretation must be re-checked "
        "before this brief is shared.\n"
    )


def build_report() -> list[Path]:
    con = connect()
    reg = Q.datasets(con)
    real = set(reg.loc[reg["data_status"] == "real", "source"])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if {"ucdp_ged", "sipri_milex"} <= real:
        c_md, _ = conflict_section(con, False, "ucdp_ged")
        c_md += hotspot_section(con)
        d_md, _ = defence_section(con, False, "sipri_milex")
        body = _real_brief(reg[reg["domain"].isin(["conflict", "defence"])], c_md, d_md, now)
        body = body.replace("## 5. Data-quality and reporting limitations", research_section(con)
                            + "\n## 6. Data-quality and reporting limitations")
        body = body.replace("## 6. What can and cannot reasonably be concluded", "## 7. What can and cannot reasonably be concluded")
        body = body.replace("## 7. Ideas for further research", "## 8. Ideas for further research")
        path = REPORTS_DIR / "RESEARCH_BRIEF.md"
    else:
        body = _demo_brief(con, now)
        path = REPORTS_DIR / "RESEARCH_BRIEF_SYNTHETIC_DEMO.md"
    path.write_text(body)
    con.close()
    return [path, *sorted(FIGURES_DIR.glob("*.png"))]


def _sources_table(reg: pd.DataFrame) -> str:
    rows = ["| Dataset | Status | Coverage | Retrieved | Licence |", "|---|---|---|---|---|"]
    for r in reg.itertuples():
        cov = r.coverage or {}
        span = f"{cov.get('date_min', cov.get('year_min'))} – {cov.get('date_max', cov.get('year_max'))}"
        rows.append(f"| {r.name} | {r.data_status} | {span} | {str(r.retrieved_at_utc)[:10]} | {r.licence} |")
    return "\n".join(rows)


def _real_brief(reg, c_md, d_md, now) -> str:
    return f"""# European Conflict & Security Intelligence: research brief

*Generated {now} by `python -m src.pipeline report`. Every figure in this document is
computed from the processed database; no number is typed by hand.*

{_version_check(reg)}
## 1. Research questions

1. How has recorded organised violence in Europe changed since 1989, and where is it concentrated?
2. How complete and consistent is the event record, and which apparent trends could be reporting artefacts?
3. How have European military expenditure levels (constant prices) and burdens (% of GDP) changed since 2014?
4. What can, and cannot, be concluded by viewing these two areas side by side?

## 2. Data sources and coverage

{_sources_table(reg[reg['data_status'] == 'real'])}

Full provenance (URLs, SHA-256 hashes, transformations) is in the dashboard's *Data quality* page
and in `reports/data_quality/*.json`. Definitions and denominators are in `docs/METHODOLOGY.md`.

## 3. Area A: conflict patterns (UCDP GED)
{c_md}
## 4. Area B: European defence trends (SIPRI)
{d_md}
## 5. Data-quality and reporting limitations

- **Recorded is not occurred.** UCDP relies on reports. Access, media attention and the fog of war
  shape what is recorded, especially in active war zones.
- **Threshold-based inclusion.** UCDP excludes conflicts below 25 battle deaths per year, so low-level
  violence and non-lethal unrest elsewhere in Europe are absent by construction.
- **Latest-year revisions.** Both sources revise back-data. The latest-year coding shift noted in
  A3 is a reason to treat the most recent UCDP year as provisional.
- **Estimates in key cases.** SIPRI figures for Russia and Ukraine are estimates with large uncertainty.
  Wartime budgets are partly secret or off-budget.
- **Definitions.** SIPRI's military expenditure definition is not NATO's. % of GDP depends on GDP
  revisions as well as on spending.

## 6. What can and cannot reasonably be concluded

**Can be concluded (descriptively):** since 2022, European conflict events in UCDP are concentrated
almost entirely in the Russia–Ukraine war. Real military expenditure across Europe rose markedly over
the same period, including outside the two belligerents. The share of countries at or above 2% of
GDP has risen sharply.

**Cannot be concluded:** that rising expenditure was *caused* by the conflict events shown here, or
that it deters them. Both are plausible hypotheses, but they share drivers (threat perception, alliance
decisions, fiscal space), and timing alone cannot separate them. Nor can total casualties or
total violence be inferred from recorded events, or the 2025 drop in event counts be treated as
de-escalation.

## 7. Ideas for further research

1. **Add ACLED for sub-national, non-lethal and threshold-free coverage.** Compare UCDP and ACLED
   counts for Ukraine *as a measurement exercise* (where and why they diverge), not to pool them.
2. **UCDP Candidate Events** (monthly releases) to cover the months after the annual GED cut-off,
   with explicit flags for provisional data.
3. **Sharpen the proximity design (section 5).** Use budget *announcements* rather than outturns to
   date the response, try synthetic-control comparisons for the most exposed countries, and test
   mechanisms (threat perception surveys, NATO capability targets).
4. **Composition of spending.** NATO and EDA data on equipment versus personnel shares to see
   *what* the increases buy.
5. **Uncertainty propagation.** Carry UCDP low/high bands and SIPRI estimate flags into every
   aggregate as intervals rather than point values.
"""


def _demo_brief(con, now) -> str:
    ev = Q.events(con, "synthetic_events")
    m = C.headline_metrics(ev)
    tc = C.temporal_counts(ev, "Year")
    tc_md = "\n".join(f"| {p.year} | {e:,} |" for p, e in zip(tc["period"], tc["events"]))
    checks = Q.quality_checks(con, "synthetic_events")
    chk_md = "\n".join(f"| {r.check_name} | {r.status} | {r.affected_rows} |" for r in checks.itertuples())
    return f"""# DEMONSTRATION BRIEF: SYNTHETIC DATA ONLY

> **Every number below describes SYNTHETIC records generated by this project.** They say nothing
> about real conflicts or real defence budgets. Run `python -m src.pipeline fetch` and
> `python -m src.pipeline build` to load UCDP and SIPRI data, then regenerate this brief.

*Generated {now}.*

## What this demonstrates

The pipeline ingested {m['events']:,} synthetic events, caught the defects deliberately injected
by `scripts/generate_synthetic_data.py`, and produced the aggregates below.

| Year | Synthetic events |
|---|---|
{tc_md}

The step increase in 2022 was **programmed into the generator** to illustrate how a change in
coverage creates an apparent trend. It is an artefact by design.

## Validation results

| Check | Status | Rows affected |
|---|---|---|
{chk_md}
"""
