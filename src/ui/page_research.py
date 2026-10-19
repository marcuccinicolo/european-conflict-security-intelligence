"""Research page: proximity to Russia and military burden (event study)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from src import research as R
from src.ui import common as U
from src.visualization import charts as V

LABELS = {"LTU", "LVA", "POL", "EST", "FIN", "DEU", "NOR", "FRA", "GBR", "ITA", "ESP", "PRT", "IRL"}


@st.cache_data(show_spinner="Estimating the models (wild cluster bootstrap, 9,999 draws)...")
def results(version: str) -> dict:
    return R.run(U.cursor())


def sc_bullet(sc: dict) -> str:
    units = sc["units"].values()
    sig = [u["name"] for u in units if u["placebo_p"] <= 0.05 + 1e-9]
    nsig = [u["name"] for u in units if u["placebo_p"] > 0.05 + 1e-9]
    return ("**Synthetic control:** every exposed unit spends more than its distant synthetic comparison after "
            "2014" if all(u["mean_gap_2022_2025"] > 0 for u in units) else "**Synthetic control:** gaps are mixed") + (
        f"; the gap is distinguishable from placebos for {', '.join(sig) or 'no unit'}"
        f" but not for {', '.join(nsig)}, where the pre-2014 fit is weaker or placebos vary more."
        if nsig else "; every unit ranks first among its placebos.")


def _p(p: float) -> str:
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def render() -> None:
    v = U.db_version()
    U.page_header("Research · pre-specified analysis", "Does proximity to Russia predict higher military burden?",
                  "An event-study design on SIPRI data for 37 European countries, 2005–2025.")  # fmt: skip
    if not R.available(U.cursor()):
        st.warning("This analysis needs the SIPRI data and the exposure table. Run "
                   "`python -m src.pipeline fetch` and `python -m src.pipeline build`.")  # fmt: skip
        return
    r = results(v)
    f = R.as_frames(r)
    m = r["main"]
    st.info(
        "The specification, sample, robustness checks and inference method were **fixed in writing before "
        "estimation**: see `docs/RESEARCH_DESIGN.md`. The randomization test, synthetic control and SIPRI-estimate "
        "checks were added after the first results, and specified in §9 before being run. Estimates describe whether the *timing and "
        "geographic gradient* of budget changes fit the threat-proximity hypothesis. They are not a causal "
        "effect of distance, and they say nothing about whether spending deters conflict.",
        icon=":material/assignment:",
    )

    st.plotly_chart(V.distance_scatter(f["raw"], LABELS), width="stretch")
    st.caption("Descriptive only: each point is one country's change between 2013 and 2025, with no model. "
               "Russia, Ukraine, Belarus, Iceland and the South Caucasus are excluded (see sample notes).")  # fmt: skip

    st.markdown("#### Main estimates")
    combined = m["post2014"] + m["post2022"]
    k = st.columns(3)
    k[0].metric("Gradient after 2014", f"{m['post2014']:+.2f} pp", help=(
        f"Change in % of GDP per 1,000 km farther from Russia, relative to 2005–2013. "
        f"95% CI {m['ci_post2014'][0]:.2f} to {m['ci_post2014'][1]:.2f}; wild-bootstrap p {_p(m['p_boot_post2014'])}."))
    k[1].metric("Additional gradient after 2022", f"{m['post2022']:+.2f} pp", help=(
        f"On top of the post-2014 gradient. 95% CI {m['ci_post2022'][0]:.2f} to {m['ci_post2022'][1]:.2f}; "
        f"wild-bootstrap p {_p(m['p_boot_post2022'])}."))
    k[2].metric("Total gradient since 2022", f"{combined:+.2f} pp", help="Sum of the two estimates.")
    st.markdown(
        f"Read: since 2022, a country **1,000 km closer to Russia** spends about **{abs(combined):.1f} "
        f"percentage points of GDP more** relative to its own 2005–2013 level than a country 1,000 km "
        f"farther away, after removing Europe-wide year effects. Wild cluster bootstrap p-values: "
        f"{_p(m['p_boot_post2014'])} (2014) and {_p(m['p_boot_post2022'])} (2022); "
        f"{r['sample']['n_countries']} countries, {r['sample']['n_obs']} country-years."
    )  # fmt: skip

    st.markdown("#### Event study")
    outcome = st.segmented_control("Outcome", ["% of GDP", "Log real expenditure"], default="% of GDP",
                                   key="es_outcome") or "% of GDP"  # fmt: skip
    if outcome == "% of GDP":
        es, pt, yt = f["event_study"], r["pretrend"], "Gradient (pp of GDP per 1,000 km)"
    else:
        es, pt, yt = f["event_study_log_real"], r["pretrend_log_real"], "Gradient (log points per 1,000 km)"
    st.plotly_chart(V.event_study_chart(es, yt, f"Year-by-year gradient relative to {2013} (95% CI)"),
                    width="stretch")  # fmt: skip
    verdict = "rejects" if pt["p"] < 0.05 else "does not reject"
    st.markdown(
        f"**Pre-trend test:** the joint test that all 2005–2012 coefficients are zero {verdict} at 5% "
        f"(F({pt['df1']}, {pt['df2']}) = {pt['F']:.2f}, p = {pt['p']:.3f}). "
        + ("The pre-2014 coefficients are small (at most a few hundredths of a point) next to the "
           "post-2022 ones, and they move in both directions, but the post-2014 estimate should be "
           "read with caution: the gradient was not perfectly flat beforehand. The post-2022 break is "
           "far larger than any pre-period movement." if pt["p"] < 0.05 else
           "The gradient was flat before 2014, which supports reading later changes as a break.")
    )  # fmt: skip

    st.markdown("#### Robustness (pre-specified)")
    rob = f["robustness"].copy()
    st.dataframe(rob.drop(columns=["outcome", "exposure"]), hide_index=True, width="stretch", column_config={
        "post2014": st.column_config.NumberColumn("after 2014", format="%+.3f"),
        "se_post2014": st.column_config.NumberColumn("s.e.", format="%.3f"),
        "p_boot_post2014": st.column_config.NumberColumn("boot. p", format="%.3f"),
        "post2022": st.column_config.NumberColumn("extra after 2022", format="%+.3f"),
        "se_post2022": st.column_config.NumberColumn("s.e.", format="%.3f"),
        "p_boot_post2022": st.column_config.NumberColumn("boot. p", format="%.3f"),
    })  # fmt: skip
    by = rob.set_index("specification")
    logb = float(by.loc["Outcome: log real expenditure", "post2022"])
    cau = by.loc["Including South Caucasus"]
    base_ok = all(by["p_boot_post2022"] < 0.05)
    lo = r["leave_one_out"]
    plc = r["placebo_2009"]
    st.markdown(
        f"- **Leave one country out:** the post-2022 estimate stays between {lo['post2022_min']:+.2f} and "
        f"{lo['post2022_max']:+.2f} (most influential: {lo['most_influential_2022']}); the post-2014 estimate "
        f"between {lo['post2014_min']:+.2f} and {lo['post2014_max']:+.2f}.\n"
        f"- **Placebo** (pretend treatment in 2009, 2005–2013 data only): {plc['coef']:+.3f}, bootstrap p "
        f"{_p(plc['p_boot'])}.\n"
        f"- Log outcomes are in log points: the additional post-2022 estimate of {logb:+.2f} means roughly "
        f"{(1 - np.exp(logb)) * 100:.0f}% lower real expenditure, relative to each country's own baseline, "
        "per 1,000 km farther from Russia.\n"
        "- The exposure 'nearest war event' uses UCDP Russia–Ukraine events in 2022–2025, including strikes "
        "far behind the front, so it is a broader measure than front-line distance."
    )  # fmt: skip

    st.markdown("#### Inference without large-sample assumptions")
    pm = r["permutation"]
    a, b = st.columns(2)
    a.plotly_chart(V.permutation_hist(pm["null_post2022"], pm["post2022"], "Randomization inference: post-2022 gradient"),
                   width="stretch")  # fmt: skip
    b.plotly_chart(V.permutation_hist(pm["null_post2014"], pm["post2014"], "Randomization inference: post-2014 gradient"),
                   width="stretch")  # fmt: skip
    st.markdown(
        f"Distances re-assigned at random across the {r['sample']['n_countries']} countries "
        f"{pm['draws']:,} times. Permutation p-values: **{_p(pm['p_perm_post2014'])}** (2014) and "
        f"**{_p(pm['p_perm_post2022'])}** (2022)"
        + (" — no random assignment produced a post-2022 gradient as strong as the observed one."
           if pm["p_perm_post2022"] <= 1 / (pm["draws"] + 1) + 1e-12 else ".")
    )  # fmt: skip

    st.markdown("#### Synthetic control: the most exposed countries")
    sc = r["synthetic_control"]
    units = sc["units"]
    pick = st.selectbox("Treated unit", list(units), format_func=lambda k: units[k]["name"], key="sc_unit")
    u = units[pick]
    st.plotly_chart(V.synth_chart(u["years"], u["actual"], u["synthetic"], u["name"]), width="stretch")
    k = st.columns(4)
    k[0].metric("Mean gap 2014–2021", f"{u['mean_gap_2014_2021']:+.2f} pp")
    k[1].metric("Mean gap 2022–2025", f"{u['mean_gap_2022_2025']:+.2f} pp")
    k[2].metric("Pre-2014 fit (RMSPE)", f"{u['pre_rmspe']:.2f} pp",
                help="Root mean squared gap 2005–2013. A poor pre-fit makes post-2014 gaps less informative.")  # fmt: skip
    k[3].metric("Placebo rank", f"{u['placebo_rank']} of {u['placebo_units']}",
                help=f"Post/pre RMSPE ratio ranked against every donor treated as a placebo. p = {u['placebo_p']:.3f}; "
                f"the smallest attainable p is {1 / u['placebo_units']:.3f}.")  # fmt: skip
    st.caption(
        "Synthetic weights: " + ", ".join(f"{n} {w:.2f}" for n, w in u["weights"].items())
        + f". Donors: countries more than {sc['donor_min_km']:,} km from Russia with complete data ({len(sc['donors'])}). "
        f"Placebo-in-time (fake 2009 treatment): mean gap {u['placebo_in_time_gap']:+.2f} pp. All of Europe responded "
        "to 2014 and 2022, so distant donors are not untreated: the gap is the *excess* response over a distant "
        "comparison."
    )
    tab = pd.DataFrame([{"unit": x["name"], "gap 2014–21": x["mean_gap_2014_2021"], "gap 2022–25": x["mean_gap_2022_2025"],
                         "pre-fit RMSPE": x["pre_rmspe"], "placebo rank": f"{x['placebo_rank']}/{x['placebo_units']}",
                         "placebo p": x["placebo_p"]} for x in units.values()])  # fmt: skip
    st.dataframe(tab, hide_index=True, width="stretch", column_config={
        "gap 2014–21": st.column_config.NumberColumn(format="%+.2f"), "gap 2022–25": st.column_config.NumberColumn(format="%+.2f"),
        "pre-fit RMSPE": st.column_config.NumberColumn(format="%.2f"), "placebo p": st.column_config.NumberColumn(format="%.3f")})  # fmt: skip

    st.markdown("#### What this does and does not show")
    robust_tail = (
        ", and the post-2022 estimate is significant (bootstrap p < 0.05) in every pre-specified robustness check."
        if base_ok else "."
    )
    pre_clean = "is not clean" if r["pretrend"]["p"] < 0.05 else "passes"
    bullets = [
        "**Consistent with the hypothesis:** a geographic gradient appears after 2014 and steepens after 2022, "
        "in levels as well as in shares of GDP" + robust_tail,
        "**Not identified:** *why*. Distance is bundled with history, alliance position and threat perception. "
        "NATO's 2014 Wales pledge, EU instruments and domestic politics change at the same dates. The estimate "
        "is a gradient in observed budgets, not the effect of moving a country.",
        f"**The post-2014 result is less secure:** including the South Caucasus moves it to "
        f"{cau['post2014']:+.2f} (bootstrap p {_p(cau['p_boot_post2014'])}), and the pre-trend test {pre_clean}. "
        "The post-2022 gradient is the more robust finding.",
        f"**Few clusters:** {r['sample']['n_countries']} countries, so the main p-values come from a wild cluster "
        f"bootstrap and are confirmed by randomization inference (post-2022 p {_p(r['permutation']['p_perm_post2022'])}).",
        sc_bullet(r["synthetic_control"]),
    ]
    st.markdown("\n".join(f"- {b}" for b in bullets))
    with st.expander("Sample notes"):
        s = r["sample"]
        st.markdown(
            f"Countries ({s['n_countries']}): {', '.join(s['countries'])}.  \n"
            f"Excluded: " + "; ".join(f"{k} ({v})" for k, v in s["excluded"].items())
            + f"; South Caucasus ({', '.join(s['caucasus_excluded_in_main'])}) excluded from the main "
            "sample because of their own wars, included in a robustness check.  \n"
            "Country-years with missing SIPRI values are dropped, not imputed."
        )
    st.caption(U.md("Data: SIPRI Military Expenditure Database; Natural Earth; UCDP GED v26.1; World Bank WDI; "
                    "nato.int. Estimation: two-way fixed effects OLS, CR1 cluster-robust standard errors by "
                    "country, wild cluster bootstrap (Rademacher, null imposed)."))  # fmt: skip
