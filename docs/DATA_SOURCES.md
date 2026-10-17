# Data sources: access, licences and decisions

Investigated on 2026-10-17. Terms change, so check the linked pages before any reuse beyond this project.

## Summary

| Source | Used for | Access | Format | Licence / terms | Committed to Git? | Dashboard export |
|---|---|---|---|---|---|---|
| **UCDP GED v26.1** | Area A (default) | Free download, no account | CSV in ZIP (39 MB → 274 MB) | **CC BY 4.0**, citation required | No (size; re-downloadable) | Yes, filtered rows + aggregates, with citation |
| **SIPRI Milex 1949–2025 v1.2** | Area B | Free download, no account | XLSX, one sheet per indicator | SIPRI T&C: free non-commercial use with attribution; reproducing >10% of a dataset needs permission | **No** | **No**: charts only, with credit line |
| **ACLED** | Area A (optional) | myACLED account; OAuth API or export tool | CSV/JSON | ACLED EULA: non-commercial, **no redistribution of raw data**, derived outputs must be transformative | **Never** | **Never** |
| **Natural Earth 1:50m admin-0** | Coordinate plausibility check | Free download | Shapefile in ZIP | Public domain | No (re-downloadable) | n/a |
| **Synthetic demo** | Runs out of the box; validation demo | Generated locally | CSV | MIT (this project) | Yes (`data/sample/`) | Yes |

## UCDP Georeferenced Event Dataset (GED)

- Download: <https://ucdp.uu.se/downloads/ged/ged261-csv.zip> (listed at <https://ucdp.uu.se/downloads/>).
- API: `https://ucdpapi.pcr.uu.se/api/gedevents/26.1` **requires an access token** (header
  `x-ucdp-access-token`, requested from UCDP). The project therefore uses the documented bulk
  download, which needs no token.
- Licence: CC BY 4.0. Cite Davies, Pettersson & Öberg (2026), *Organized violence 1989–2025*,
  Journal of Peace Research, and Sundberg & Melander (2013), *Introducing the UCDP Georeferenced
  Event Dataset*, Journal of Peace Research 50(4).
- Why it is the default: event-level, georeferenced, fatality estimates with uncertainty bounds,
  open licence, no credentials. Its 25-death inclusion threshold is a scope limitation, documented
  in `METHODOLOGY.md`.

## SIPRI Military Expenditure Database

- Download: <https://www.sipri.org/sites/default/files/SIPRI-Milex-data-1949-2025_v1.2.xlsx>
  (from <https://www.sipri.org/databases/milex>, DOI 10.55163/CQGC9685; revised 27 April 2026).
- Terms: <https://www.sipri.org/about/terms-and-conditions>. Fair use for research and teaching
  covers less than 10% of a dataset, with due reference. Charts based on the data may be published
  with SIPRI clearly identified. Commercial use requires a licence.
- Credit line used in the app and report: *"Information from the Stockholm International Peace
  Research Institute (SIPRI), Military Expenditure Database, https://www.sipri.org/databases/milex"*.
- Consequences for this project: the workbook and all derived tables are git-ignored, and the
  dashboard offers no SIPRI export.

## ACLED

- API guide: <https://acleddata.com/api-documentation/getting-started>. OAuth password grant at
  `https://acleddata.com/oauth/token` (`client_id=acled`), data at `https://acleddata.com/api/acled/read`.
- EULA: <https://acleddata.com/eula>. Raw data are licensed for non-commercial use, may not be
  redistributed or made directly accessible, and scraping is prohibited.
- Consequences for this project: no ACLED data are included. `src/data/fetch.py::fetch_acled`
  reads credentials only from environment variables or `.env` (git-ignored), and writes to
  `data/raw/acled/` (git-ignored). Row-level export is disabled for ACLED in the dashboard. Before
  publishing any ACLED-derived chart, check ACLED's attribution policy and its "transformative"
  requirement.

## Natural Earth

- <https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_0_countries.zip>, public domain.
- Shows de facto boundaries for some disputed areas (e.g. Crimea as Russia), which this project
  documents as a source of expected point-in-country mismatches.

## What was not used, and why

- **Scraping** of any website: unnecessary (documented downloads exist) and against ACLED's terms.
- **NATO defence-expenditure data**: a different definition from SIPRI's. Mixing the two would
  combine incompatible indicators. It is a candidate for a separate, clearly labelled comparison.
- **Internship material (EoDynamics)**: deliberately excluded. This project uses only public or
  synthetic data.
