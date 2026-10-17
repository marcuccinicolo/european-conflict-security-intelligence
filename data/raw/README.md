# data/raw — original source files (git-ignored)

Files here are never committed. Re-create them with `python -m src.pipeline fetch`
or place them manually:

| Folder | Expected file | Source |
|---|---|---|
| `ucdp/` | `ged261-csv.zip` (or `GEDEvent_v26_1.csv`) | https://ucdp.uu.se/downloads/ |
| `sipri/` | `SIPRI-Milex-data-1949-2025_v1.2.xlsx` | https://www.sipri.org/databases/milex |
| `naturalearth/` | `ne_50m_admin_0_countries.zip` | https://www.naturalearthdata.com |
| `acled/` | any `*.csv` export from ACLED (optional) | https://acleddata.com (account required) |

Each downloaded file gets a `<file>.provenance.json` sidecar (URL, UTC time, size, SHA-256).
Manually placed files are accepted; their provenance falls back to file metadata.
