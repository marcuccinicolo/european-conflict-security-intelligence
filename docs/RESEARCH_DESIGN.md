# Research design: proximity to Russia and European military burden

*Specification fixed on 2026-10-17, **before** any estimate was produced. Changes made after seeing
results are listed in §8 with the reason, so specification searching is visible.*

## 1. Question

After Russia's annexation of Crimea (2014) and full-scale invasion of Ukraine (2022), did European
countries **closer to Russia** raise military expenditure, as a share of GDP, by more than countries
farther away?

The "threat-proximity" hypothesis is common in security studies. This design tests whether the
**timing and gradient** of budget changes are consistent with it. It does not identify *why*
governments spent more: proximity is correlated with history, alliance position and threat
perception, which are part of the mechanism, not confounders to remove.

## 2. Data

| Variable | Source | Licence |
|---|---|---|
| Military expenditure, % of GDP; constant 2024 US$ | SIPRI Milex 1949–2025 v1.2 | SIPRI T&C |
| Capital city coordinates | Natural Earth 1:50m populated places (`Admin-0 capital`) | Public domain |
| Russian territory | Natural Earth 1:50m admin-0, **Crimea removed** (internationally recognised borders) | Public domain |
| Nearest war-event locations (robustness) | UCDP GED 2022–2025, precisely located Russia–Ukraine events | CC BY 4.0 |
| GDP per capita, constant 2015 US$ (robustness) | World Bank WDI `NY.GDP.PCAP.KD` | CC BY 4.0 |
| NATO accession year | nato.int, *Member countries* (hand-coded table in `data/reference/`) | Public facts |

## 3. Sample

- European countries in SIPRI, **2005–2025**.
- **Excluded:** Russia and Ukraine (the belligerents; their spending *is* the war), Belarus
  (co-belligerent, and its data are mostly estimates), Iceland (no armed forces: spending is zero
  by construction).
- **Main sample excludes the South Caucasus** (Armenia, Azerbaijan, Georgia), which have their
  own wars (Nagorno-Karabakh 2016, 2020, 2023). They are included in a robustness check.
- Unbalanced panel: country-years with missing SIPRI values are dropped, never imputed.

## 4. Exposure

`distance_i` = straight-line distance, in **1,000 km**, from country *i*'s capital to the
nearest point of Russia's internationally recognised territory (Kaliningrad included, Crimea
excluded). It is computed as planar distance in ETRS89-LAEA (EPSG:3035), which is accurate to a few percent across Europe; it is time-invariant, and is measured before
outcomes are looked at.

**Sign convention:** a *negative* coefficient means that countries farther from Russia increased
their burden *less*, i.e. that closer countries increased it more.

## 5. Estimating equations

**Event study (primary evidence):**

  y_it = α_i + λ_t + Σ_{k ≠ 2013} β_k · (distance_i × 1[t = k]) + ε_it

**Difference-in-differences summary:**

  y_it = α_i + λ_t + β₁ · distance_i × 1[t ≥ 2014] + β₂ · distance_i × 1[t ≥ 2022] + ε_it

- y = military expenditure as % of GDP (percentage points).
- α_i country fixed effects, λ_t year fixed effects (absorb Europe-wide shocks, e.g. the 2008 crisis
  or the 2020 GDP collapse).
- β₂ is the **additional** gradient after 2022, on top of the post-2014 gradient.
- Base year 2013, the last year before the annexation of Crimea.

**Inference.** Standard errors are clustered by country. With fewer than 40 clusters,
conventional cluster-robust inference over-rejects, so the headline p-values come from a **wild
cluster bootstrap with the null imposed** (Rademacher weights, 9,999 draws).

**Pre-trend test.** Joint Wald test that β_2005 … β_2012 = 0 (cluster-robust, F form). A rejection
means the gradient was already moving before 2014, and the post-2014 estimates cannot be read as a
response to 2014.

## 6. Robustness checks (all pre-specified)

1. **Outcome in levels:** log real military expenditure (constant 2024 US$). This separates
   "spent more" from "GDP fell".
2. **Include the South Caucasus.**
3. **Alternative exposure:** distance to the nearest precisely located UCDP Russia–Ukraine event,
   2022–2025 ("war-event proximity").
4. **NATO membership:** add a time-varying NATO-member indicator.
5. **Drop the Baltic states jointly** (EST, LVA, LTU), the most exposed and most-cited cases.
6. **Leave-one-out:** re-estimate β₁ and β₂ dropping each country in turn; report the range.
7. **Placebo timing:** on 2005–2013 only, pretend treatment began in 2009. A sizeable estimate
   would indicate the design picks up spurious drift.
8. **GDP control (levels outcome only):** add log real GDP per capita to the levels regression.
   It is *not* added to the %-of-GDP regression, because GDP is that outcome's denominator (a bad
   control).

## 7. Threats to interpretation

- **Exposure is not randomly assigned.** Eastern-flank countries differ in history, alliance timing
  and politics. The design compares *changes* within countries against Europe-wide year effects, but
  any factor that both correlates with distance and changes in 2014 or 2022 (e.g. NATO's 2014 Wales
  pledge, which bound all members) is part of the estimate.
- **Few clusters, small effective sample:** ~38 countries. Estimates are descriptive gradients with
  honest uncertainty, not precise elasticities.
- **SIPRI estimates and GDP revisions** affect the outcome. Recent values for some countries are
  estimates.
- **Anticipation and announcement lags:** budgets are set in advance, so a 2022 shock appears from
  2022–2023 onwards.

## 8. Changes after seeing results

- **Label of robustness exposure 3 (before estimation).** After computing the distances, and before
  running any regression, the measure was renamed from "front-line proximity" to "distance to the
  nearest recorded war event". UCDP's Russia–Ukraine events include missile and drone strikes far
  behind the front (e.g. near Odesa, 105 km from Chișinău), so "front line" would overstate what
  it measures. The measure itself was not changed.
