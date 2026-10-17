"""Generate the SYNTHETIC demonstration datasets in data/sample/.

THESE ARE NOT REAL OBSERVATIONS. They exist so that the dashboard runs straight
after cloning, and so that the validation layer has known defects to catch.

* Events follow ACLED's column layout so that the same adapter exercises the
  ACLED import path. Every row carries ``data_status=SYNTHETIC`` and every
  ``notes`` field starts with "SYNTHETIC".
* Locations are random draws around a few city-level anchor points; volumes,
  types and fatalities are random. Any resemblance to real patterns is a
  property of the generator's parameters, not of the world.
* Deliberately injected defects (counts are fixed by the seed) are listed in
  INJECTED_DEFECTS and asserted by tests/test_synthetic.py.

Run:  python scripts/generate_synthetic_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import SYNTHETIC_EVENTS_CSV, SYNTHETIC_MILEX_CSV  # noqa: E402
from src.data.schema import MILEX_INDICATORS  # noqa: E402

SEED = 20261017
N_EVENTS = 4000

ANCHORS = {  # country: [(lat, lon), ...] approximate city centres
    "Ukraine": [(49.99, 36.23), (48.00, 37.80), (47.84, 35.14), (50.45, 30.52), (46.48, 30.73)],
    "Russia": [(50.60, 36.60), (51.73, 36.19)],
    "Georgia": [(41.72, 44.79)],
    "Armenia": [(40.18, 44.51)],
    "Azerbaijan": [(40.41, 49.87)],
    "Moldova": [(47.01, 28.86)],
    "Serbia": [(44.79, 20.45)],
    "Kosovo": [(42.66, 21.16)],
    "France": [(48.86, 2.35)],
    "Germany": [(52.52, 13.40)],
    "Poland": [(52.23, 21.01)],
    "United Kingdom": [(51.50, -0.12)],
    "Italy": [(41.90, 12.50)],
    "Spain": [(40.42, -3.70)],
}
COUNTRY_WEIGHTS = np.array([30, 6, 3, 3, 3, 3, 4, 3, 10, 9, 6, 8, 6, 6], dtype=float)

TYPES = {
    "Battles": ["Armed clash", "Government regains territory"],
    "Explosions/Remote violence": [
        "Shelling/artillery/missile attack", "Air/drone strike", "Remote explosive/landmine/IED",
    ],
    "Violence against civilians": ["Attack", "Abduction/forced disappearance"],
    "Protests": ["Peaceful protest", "Protest with intervention"],
    "Riots": ["Violent demonstration", "Mob violence"],
    "Strategic developments": ["Arrests", "Looting/property destruction", "Other"],
}  # fmt: skip
# Conflict-type events concentrate in the first eight (eastern) anchors.
CONFLICT_TYPES = ["Battles", "Explosions/Remote violence", "Violence against civilians"]
FATALITY_MEAN = {"Battles": 2.0, "Explosions/Remote violence": 1.2,
                 "Violence against civilians": 0.8, "Protests": 0.0, "Riots": 0.1,
                 "Strategic developments": 0.05}  # fmt: skip

INJECTED_DEFECTS = {
    "duplicate_ids": 30,
    "missing_coordinates": 40,
    "out_of_range_coordinates": 10,
    "null_island": 5,
    "long_format_dates": 60,  # "05 March 2023"
    "dayfirst_slash_dates": 25,  # "05/03/2023"
    "unparseable_dates": 10,
    "blank_fatalities": 80,
    "negative_fatalities": 3,
    "unknown_country": 5,
}


def make_events(rng: np.random.Generator) -> pd.DataFrame:
    countries = list(ANCHORS)
    p = COUNTRY_WEIGHTS / COUNTRY_WEIGHTS.sum()
    # Volume rises over time, with a step in 2022 standing in for a *coverage*
    # change (more sources monitored) - used in the demo to explain reporting artefacts.
    days = pd.date_range("2019-01-01", "2025-12-31", freq="D")
    w = np.where(days.year >= 2022, 3.0, 1.0) * (1 + 0.15 * np.sin(np.arange(len(days)) / 58))
    dates = rng.choice(days, size=N_EVENTS, p=w / w.sum())

    rows = []
    for i in range(N_EVENTS):
        c = rng.choice(countries, p=p)
        eastern = c in countries[:8]
        tprobs = np.array([3, 3, 2, 1, 1, 1] if eastern else [0.1, 0.2, 0.5, 5, 2, 1.5])
        etype = rng.choice(list(TYPES), p=tprobs / tprobs.sum())
        lat, lon = ANCHORS[c][rng.integers(len(ANCHORS[c]))]
        lat, lon = lat + rng.normal(0, 0.18), lon + rng.normal(0, 0.25)
        rows.append(
            {
                "event_id_cnty": f"SYN{i + 1:05d}",
                "event_date": pd.Timestamp(dates[i]).strftime("%Y-%m-%d"),
                "year": pd.Timestamp(dates[i]).year,
                "time_precision": rng.choice([1, 2, 3], p=[0.85, 0.12, 0.03]),
                "event_type": etype,
                "sub_event_type": rng.choice(TYPES[etype]),
                "country": c,
                "admin1": f"Synthetic area {rng.integers(1, 6)}",
                "latitude": round(lat, 4),
                "longitude": round(lon, 4),
                "geo_precision": rng.choice([1, 2, 3], p=[0.7, 0.25, 0.05]),
                "fatalities": int(rng.poisson(FATALITY_MEAN[etype] * (2 if eastern else 1))),
                "notes": "SYNTHETIC demonstration record - not a real event.",
                "data_status": "SYNTHETIC",
            }
        )
    df = pd.DataFrame(rows)
    df["fatalities"] = df["fatalities"].astype("object")

    d = INJECTED_DEFECTS
    idx = rng.permutation(len(df))
    take = iter(np.split(idx, np.cumsum(list(d.values())))[: len(d)])
    sel = dict(zip(d, take))
    df.loc[sel["missing_coordinates"], ["latitude", "longitude"]] = np.nan
    df.loc[sel["out_of_range_coordinates"], "latitude"] = 95.0
    df.loc[sel["null_island"], ["latitude", "longitude"]] = 0.0
    ts = pd.to_datetime(df.loc[sel["long_format_dates"], "event_date"])
    df.loc[sel["long_format_dates"], "event_date"] = ts.dt.strftime("%d %B %Y")
    ts = pd.to_datetime(df.loc[sel["dayfirst_slash_dates"], "event_date"])
    df.loc[sel["dayfirst_slash_dates"], "event_date"] = ts.dt.strftime("%d/%m/%Y")
    df.loc[sel["unparseable_dates"], "event_date"] = "2023-13-45"
    df.loc[sel["blank_fatalities"], "fatalities"] = ""
    df.loc[sel["negative_fatalities"], "fatalities"] = -1
    df.loc[sel["unknown_country"], "country"] = "Atlantis (synthetic)"
    dups = df.loc[sel["duplicate_ids"]].copy()  # exact copies of existing ids
    df = pd.concat([df, dups], ignore_index=True)
    return df


def make_milex(rng: np.random.Generator) -> pd.DataFrame:
    countries = {  # iso3: (name, subregion, starting level US$ m)
        "DEU": ("Germany", "Western Europe", 40000), "FRA": ("France", "Western Europe", 45000),
        "ITA": ("Italy", "Western Europe", 30000), "ESP": ("Spain", "Western Europe", 15000),
        "GBR": ("United Kingdom", "Western Europe", 50000), "SWE": ("Sweden", "Western Europe", 6000),
        "POL": ("Poland", "Central Europe", 8000), "UKR": ("Ukraine", "Eastern Europe", 3000),
    }  # fmt: skip
    years = range(2000, 2026)
    deflator = {y: 1.0 / (1.02 ** (2024 - y)) for y in years}  # synthetic 2% inflation
    rows = []
    for iso, (name, sub, level) in countries.items():
        real = level
        gdp_share = rng.uniform(1.0, 2.2)
        for y in years:
            real *= 1 + rng.normal(0.01, 0.04) + (0.08 if y >= 2022 else 0)
            gdp_share = max(0.5, gdp_share + rng.normal(0.0, 0.06) + (0.15 if y >= 2022 else 0))
            missing = rng.random() < 0.03
            flag = "unavailable" if missing else ("estimate" if rng.random() < 0.08 else "reported")
            vals = {
                "milex_constant_usd_m": real,
                "milex_current_usd_m": real * deflator[y],
                "share_gdp_pct": gdp_share,
            }
            for ind, v in vals.items():
                meta = MILEX_INDICATORS[ind]
                rows.append({
                    "source": "synthetic_milex", "data_status": "synthetic", "country": name,
                    "iso3": iso, "subregion": sub, "entity_type": "country", "year": y,
                    "indicator": ind, "unit": meta["unit"],
                    "price_basis": meta["price_basis"].replace("2024", "2024 (synthetic)"),
                    "value": None if missing else round(v, 2), "value_flag": flag,
                })  # fmt: skip
    return pd.DataFrame(rows)


def main() -> None:
    rng = np.random.default_rng(SEED)
    SYNTHETIC_EVENTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    make_events(rng).to_csv(SYNTHETIC_EVENTS_CSV, index=False)
    make_milex(rng).to_csv(SYNTHETIC_MILEX_CSV, index=False)
    print(f"wrote {SYNTHETIC_EVENTS_CSV}\nwrote {SYNTHETIC_MILEX_CSV}")


if __name__ == "__main__":
    main()
