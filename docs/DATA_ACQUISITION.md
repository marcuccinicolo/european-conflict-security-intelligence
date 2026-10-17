# Loading real data

The app always runs with the bundled synthetic demo. Real data are added in three ways.

## 1. Official public downloads (UCDP, SIPRI, Natural Earth): one command

```bash
python -m src.pipeline fetch     # downloads to data/raw/, writes provenance sidecars
python -m src.pipeline build     # validates everything -> data/processed/security.duckdb
python -m src.pipeline report    # optional: regenerate reports/RESEARCH_BRIEF.md
```

`fetch` skips files that already exist (`--force` re-downloads). Each file gets
`<file>.provenance.json` with the URL, UTC retrieval time, size and SHA-256.

**New versions.** When UCDP or SIPRI publish a new release, update `download_url` in
`src/config.py` (`SOURCES`). The adapters locate headers and year columns dynamically, and the
SIPRI parser reads the base year from the sheet name, e.g. "Constant (2025) US$". Then re-run
`fetch --force`, `build` and `report`. The report warns that its commentary needs review, because
the file hash will have changed.

## 2. Manual placement (any source, offline)

Download the files in a browser and put them where `data/raw/README.md` says. `build` picks up:

- `data/raw/ucdp/ged*-csv.zip` or `GEDEvent*.csv`
- `data/raw/sipri/SIPRI-Milex-data-*.xlsx` (the latest by name)
- `data/raw/acled/*.csv` (all files are concatenated; duplicate ids across files are dropped)

## 3. ACLED (account required)

**Option A: export tool.** Log in at acleddata.com, export Europe events as CSV, and save the
file into `data/raw/acled/`.

**Option B: API.**

```bash
cp .env.example .env              # then edit: ACLED_USERNAME / ACLED_PASSWORD
python -m src.pipeline fetch --acled --acled-start 2020-01-01
python -m src.pipeline build
```

The fetcher requests an OAuth token, pages through `/api/acled/read` 5,000 rows at a time for the
European countries in `src/data/countries.py`, and saves one CSV plus a provenance sidecar.
Credentials are never written to disk outside `.env`.

### Required ACLED columns

`event_id_cnty, event_date, event_type, sub_event_type, country, latitude, longitude, fatalities`.
These are optional but used: `admin1, geo_precision, time_precision`. Missing required columns
stop the build with a clear error. Unknown countries are listed in the quality report and dropped.

## Your own CSV in ACLED layout

Any events file with the required ACLED columns can be loaded the same way. Rows must be real
observations: synthetic files are recognised only through `data_status=SYNTHETIC`, and they live
in `data/sample/`.

## Licence reminders

- Do not commit `data/raw/` or `data/processed/` (already git-ignored).
- SIPRI: charts with the credit line are fine; republishing tables of more than 10% of the data
  requires permission.
- ACLED: never redistribute rows; follow the attribution policy for any published output.
