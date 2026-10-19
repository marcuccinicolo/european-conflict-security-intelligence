# Methodology & limitations

## 1. Scope and design principles

The platform has two analytical areas that are **computed separately and never pooled**:

| Area | Question | Primary source | Unit of observation |
|---|---|---|---|
| A. Conflict patterns | Where and when is organised violence *recorded* in Europe, of what type, and how complete are the records? | UCDP GED v26.1 (optional: ACLED) | One reported event |
| B. Defence trends | How have European military expenditure levels and burdens changed? | SIPRI Military Expenditure Database (1949–2025) | One country-year-indicator value |

Principles applied in code (not only in prose):

1. **One source per aggregate.** Every query and every analysis function is restricted to a single source; functions raise an error if a frame mixes sources.
2. **Missing is not zero.** Missing fatalities, unavailable SIPRI values ("...") and non-existent states ("xxx") stay missing. Every sum is reported with the number of observations it covers.
3. **Units travel with values.** Each expenditure row carries `unit` and `price_basis`; analysis functions refuse frames with more than one indicator.
4. **No causal claims.** The two areas are shown side by side as context, with separate axes, never as a regression or a correlation coefficient.
5. **Synthetic data are visibly synthetic.** Separate source keys, a red banner, a watermark on every chart and an explicit `data_status` column.

## 2. Europe definition

- **UCDP:** UCDP's own `region` field ("Europe"). This includes Russia, the South Caucasus (Armenia, Azerbaijan, Georgia) and the countries of the former Yugoslavia. UCDP assigns events to the **state that existed at the time** (Gleditsch–Ward system), so 1991–1999 events in Croatia, Bosnia and Kosovo appear as "Serbia (Yugoslavia)", and 1989–1991 events in the Caucasus as "Russia (Soviet Union)". The country filter therefore reflects UCDP's historical coding, not present-day borders.
- **SIPRI:** SIPRI's Central, Eastern and Western Europe sub-regions. Türkiye is in SIPRI's Middle East region and is excluded. Historical entities (USSR, Yugoslavia, Czechoslovakia, GDR) and the EU aggregate are kept in the database with `entity_type` = `historical` / `aggregate` but are excluded from country comparisons.

## 3. Conflict metrics

| Metric | Definition | Denominator / coverage |
|---|---|---|
| Recorded events | Number of distinct source records in the selection after de-duplication by event id | — |
| Estimated fatalities (UCDP) | Sum of UCDP `best` estimates; the low–high range is the sum of `low` and `high` | All events (UCDP has no missing values) |
| Reported fatalities (ACLED) | Sum of reported fatalities | Only events with a figure; coverage shown separately |
| Events with a fatality figure | Events with non-missing fatalities ÷ all events | All events in selection |
| Precisely located | UCDP `where_prec` ∈ {1, 2} (exact place or within ~25 km); ACLED `geo_precision` = 1 | All events in selection |
| Date uncertain | UCDP `date_prec` > 1; ACLED `time_precision` > 1 | All events in selection |
| Share in 10 busiest cells | Located events in the 10 busiest 0.5°×0.5° grid cells ÷ all located events | Located events only |
| Mean centre / standard distance | Mean of projected coordinates (EPSG:3035) and root-mean-square distance to it, per year | Located events only |
| % change between periods | (B − A) ÷ A for two windows of equal length | Shown only when A ≥ 10 events |

**Dating.** Events are dated by their start date. Events that span several days (UCDP `date_prec` > 1) are counted once, in the period of their start date.

**Empty periods.** A month with no records shows 0 events: "no recorded events", which is not the same as "no events".

### Hot-spot analysis (Conflict page, *Hot spots* tab; brief §A4)

| Element | Choice | Why |
|---|---|---|
| Unit | Square cells of 10, 25 or 50 km in EPSG:3035 | Equal area, so cell counts are comparable |
| Study area | Cells containing an event, plus cells whose centre is on the land of the selected countries within 100 km of an event | Follows the theatre of activity and its quiet margins, without the empty space a convex hull adds between distant events |
| Zero-event cells | **Kept** | Dropping them makes busy cells look ordinary; a common error |
| Events | Precise locations only by default (UCDP `where_prec` 1–2) | Region- or country-level events sit at centroids and create false clusters |
| Statistic | Getis-Ord Gi*, binary queen weights including the cell itself, analytic z-scores | Standard local clustering statistic; validated against PySAL `esda.G_Local` |
| Multiple testing | Benjamini–Hochberg FDR at 1%, 5%, 10% | Thousands of cells are tested at once |
| Trends | One Gi* per calendar year on a fixed grid: Persistent / Intermittent / New / Diminishing | Comparable maps across years |
| Active area | km² of cells with ≥1 recorded event per month | Spread of recorded activity, **not** front line or control |

Caveats: results change with cell size (the modifiable areal unit problem), so the dashboard offers
three sizes and the brief reports all three. Cold spots are almost impossible with zero-dominated
counts. Hot spots describe the frequency of *recorded* events, not lethality and not true incidence.

### What an "event" means differs by source

- **UCDP GED** includes only events within conflicts, dyads or actors that reach **25 battle-related deaths in a calendar year**, and every event has at least one death. Protests, riots and non-lethal incidents are out of scope. A drop in UCDP events can mean a conflict fell below the threshold.
- **ACLED** records political violence *and* demonstrations with no fatality threshold. Its counts are therefore much larger and include many zero-fatality events.

Event counts from the two sources are **not comparable** and are never combined.

## 4. Defence metrics

| Indicator | Unit | Price basis | Denominator | Valid uses |
|---|---|---|---|---|
| Military expenditure, constant (2024) US$ | US$ million | constant 2024 prices and exchange rates | — | Real growth over time; cross-country level comparisons |
| Military expenditure, current US$ | US$ million | current prices and exchange rates | — | Nominal size in a given year. **Growth is refused** (it mixes inflation and exchange rates) |
| % of GDP | percent | ratio of current local-currency values | GDP | Economic burden; changes in **percentage points** |
| Per capita | current US$ per person | current | Population | Per-person comparison in one year |
| % of government spending | percent | ratio | General government expenditure | Budget priority |

Additional rules:

- **Balanced-panel totals.** Totals across countries use only countries with data in *every* year of the range; the excluded countries are listed in the tooltip. This prevents a total from rising simply because a country's data begin.
- **Estimate flags.** SIPRI shows estimates in blue and highly uncertain figures in red. The parser reads cell font colours and stores them in `value_flag`. Estimated values are shown with open circles (trend lines) and hatching (bar charts).
- **Thresholds.** The "≥ 2% of GDP" view counts countries per year with the number of countries with data as the denominator. SIPRI's definition of military expenditure differs from NATO's, so this is **not** a NATO compliance measure.
- **Rankings.** Bar charts order by point value only. Small differences are within measurement error and do not rank "effort".

## 5. Data-quality checks

Each adapter produces a JSON report (`reports/data_quality/<source>.json`) and writes every check to the `quality_checks` table. Checks include:

- required columns (hard failure if missing);
- date parsing with **explicit formats only** (ISO, then "05 March 2023", then day-first "05/03/2023"; US month-first is never guessed), format consistency, start ≤ end, and date range;
- duplicate event ids (dropped, first kept) and possible duplicates sharing date + coordinates + type (reported, *not* dropped, because they can be distinct events);
- coordinates: missing, out of range, (0, 0) "null island" → set to null; the event still counts but is excluded from maps;
- a **point-in-country test** against Natural Earth 1:50m borders, with a 10 km tolerance in EPSG:3035. This is a plausibility flag. Mismatches arise legitimately from historical state coding (see §2) and contested areas (Natural Earth draws Crimea as Russia; UCDP codes it Ukraine);
- country-name harmonisation (unmapped names are listed and dropped);
- fatalities: negative values are set to missing, UCDP low ≤ best ≤ high, missingness;
- SIPRI: duplicate country-year-indicator rows, negative values, shares above 100%, counts per value flag.

## 6. Known limitations

**Reporting bias.** Both event datasets rely on news, NGO and partner reports. Coverage is better in accessible, media-dense areas and in high-profile conflicts. Changes in monitoring effort, language coverage or source partnerships change counts without any change on the ground. The *Reporting & completeness* tab shows proxies for this (precision shares, sources per event), but it cannot remove the bias.

**Fog of war.** Fatality figures in active wars are contested and often revised. UCDP's `best` is an estimate within a low–high band, and the band is shown. For Ukraine since 2022, recorded figures are widely understood to be partial.

**Classification limits.** Event-type categories are the source's own. Similar incidents can be classified differently across sources, versions and coders. UCDP's type of violence describes the actors (state, non-state, one-sided), not the weapon.

**Location precision.** Events coded only to a region or country are placed at a centroid and create artificial clusters. The map defaults to precise locations only.

**Versioning.** UCDP and SIPRI revise back-data between releases. Results are tied to the file versions and SHA-256 hashes recorded in the registry.

**SIPRI estimates.** Recent values for several countries, especially those at war, are SIPRI estimates and highly uncertain. SIPRI's figures include items that national budgets classify differently, so they can differ from national or NATO figures.

## 7. Research extension

The proximity event study (dashboard *Research* page, brief section 5) follows its own written
design in [RESEARCH_DESIGN.md](RESEARCH_DESIGN.md). Gradients are in percentage points of GDP per
1,000 km. Negative values mean that countries closer to Russia increased their burden more.
Inference combines a wild cluster bootstrap, randomization inference over distances, and a synthetic
control for the Baltic states and Poland (§9 of the design, added after the first results and
specified before being run).

## 8. What can and cannot be concluded

**Can:** describe how recorded events and estimated fatalities in a source are distributed over time, space and type; describe changes in real military expenditure and in its share of GDP; identify where data are incomplete.

**Cannot:** infer total real-world violence; read the proximity gradient as the causal effect of distance; compare event counts across sources; attribute changes in spending to conflict (or the reverse); predict future events; locate individuals or support operational decisions.
