# Data dictionary

Database: `data/processed/security.duckdb` (DuckDB). Schemas are defined in `src/data/schema.py`.

## `conflict_events`: one row per source event

| Column | Type | Description | UCDP origin | ACLED origin |
|---|---|---|---|---|
| `event_id` | text | Source id, unique within `source` | `"ucdp-" + id` | `event_id_cnty` |
| `source` | text | `ucdp_ged`, `acled` or `synthetic_events` | | |
| `data_status` | text | `real` or `synthetic` | | |
| `event_date` | date | Event (start) date | `date_start` | `event_date` |
| `year` | int | Year of `event_date` | | |
| `date_uncertain` | bool | Date known only to a range | `date_prec > 1` | `time_precision > 1` |
| `country` | text | Harmonised country name | `country` via ISO3 map | `country` |
| `iso3` | text | ISO 3166-1 alpha-3 (Kosovo `XKX`) | | |
| `subregion` | text | SIPRI subregion (Central/Eastern/Western Europe) | | |
| `admin1` | text | First-level administrative unit | `adm_1` | `admin1` |
| `latitude`, `longitude` | float | WGS84; **null** if missing/invalid | | |
| `coord_status` | text | `valid`, `missing`, `out_of_range`, `null_island` | | |
| `coord_check` | text | `inside`, `within_10km`, `elsewhere` (vs stated country, Natural Earth), `not_checked` | | |
| `location_precise` | bool | Located to the named place | `where_prec ∈ {1,2}` | `geo_precision = 1` |
| `event_type` | text | Source category | `type_of_violence` label | `event_type` |
| `sub_event_type` | text | Source sub-category | — (null) | `sub_event_type` |
| `conflict_name` | text | UCDP conflict | `conflict_name` | — (null) |
| `fatalities` | float | Best estimate (UCDP) / reported (ACLED); **null = not reported** | `best` | `fatalities` |
| `fatalities_low`, `fatalities_high` | float | Estimate bounds | `low`, `high` | — |
| `fatalities_kind` | text | `estimate` or `reported` | | |
| `n_sources` | int | Number of source reports | `number_of_sources` (−1 → null) | — |

UCDP `type_of_violence`: 1 = State-based conflict, 2 = Non-state conflict, 3 = One-sided violence.

## `milex`: one row per entity × year × indicator

| Column | Type | Description |
|---|---|---|
| `source` | text | `sipri_milex` or `synthetic_milex` |
| `data_status` | text | `real` or `synthetic` |
| `country`, `iso3`, `subregion` | text | Entity identifiers (EU aggregate: `EUU`; historical states: `XSU`, `XYU`, `XCS`, `XDD`) |
| `entity_type` | text | `country`, `historical`, `aggregate` |
| `year` | int | Calendar year (local-currency financial-year sheets are not used) |
| `indicator` | text | See below |
| `unit` | text | e.g. `US$ million`, `% of GDP` |
| `price_basis` | text | e.g. `constant 2024 prices and exchange rates` |
| `value` | float | **Null** when unavailable; never zero-filled |
| `value_flag` | text | `reported`, `estimate` (blue in SIPRI), `highly_uncertain` (red), `unavailable` ("..."), `not_independent` ("xxx") |

| `indicator` | SIPRI sheet | Unit | Transformation |
|---|---|---|---|
| `milex_constant_usd_m` | Constant (2024) US$ | US$ million, constant 2024 | none |
| `milex_current_usd_m` | Current US$ | US$ million, current | none |
| `share_gdp_pct` | Share of GDP | % of GDP | fraction × 100 |
| `per_capita_current_usd` | Per capita | current US$ per person | none |
| `share_govt_pct` | Share of Govt. spending | % of government expenditure | fraction × 100 |

## `exposure`: one row per European country (research)

| Column | Description |
|---|---|
| `iso3`, `country`, `capital`, `latitude`, `longitude` | Capital city (Natural Earth `Admin-0 capital`) |
| `dist_russia_km` | Distance from the capital to Russia's internationally recognised territory (Crimea removed, Kaliningrad included), EPSG:3035 |
| `dist_front_km` | Distance to the nearest precisely located UCDP Russia–Ukraine event, 2022–2025 |
| `nato_accession_year` | Year of NATO accession; null for non-members |

## `macro`: country × year (research)

`iso3, year, gdp_pc_const2015_usd` (World Bank `NY.GDP.PCAP.KD`; null = not reported), `country`.

## `datasets`: registry (one row per loaded source)

`source, domain, name, publisher, data_status, licence, licence_url, url, citation,
redistribution, exportable, input_file, retrieved_at_utc, retrieval_method, sha256 (16-char
prefix), rows_in, rows_out, coverage (JSON), transformations (JSON), notes (JSON),
processed_at_utc`.

## `quality_checks`: one row per validation check

`source, check_name, status (pass | warn | fail | info | not_run), affected_rows, total_rows,
share, detail, action`. The same content is written to `reports/data_quality/<source>.json`, with
a summary in `reports/data_quality/index.json`.
