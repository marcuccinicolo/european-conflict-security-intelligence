"""World Bank WDI adapter (CC BY 4.0): GDP per capita, constant 2015 US$.

Documented API, no key: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
Used only as a robustness control in the proximity analysis.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests

from src.config import RAW_DIR
from src.data import countries
from src.data.validation import QualityReport

INDICATOR = "NY.GDP.PCAP.KD"
API = "https://api.worldbank.org/v2/country/{codes}/indicator/{ind}"
RAW_JSON = RAW_DIR / "worldbank" / f"wdi_{INDICATOR}.json"


def fetch_wdi(start: int = 2000, end: int = 2025, dest: Path = RAW_JSON) -> Path:
    from src.data.fetch import USER_AGENT, write_provenance

    codes = [k for k in countries.EUROPE if k not in countries.HISTORICAL]
    url = API.format(codes=";".join(codes), ind=INDICATOR)
    params = {"format": "json", "date": f"{start}:{end}", "per_page": 20000}
    r = requests.get(url, params=params, timeout=120, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, list) or len(payload) < 2:
        raise RuntimeError(f"Unexpected World Bank response: {str(payload)[:200]}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload))
    write_provenance(dest, f"{url}?date={start}:{end}", method="World Bank API v2")
    return dest


def load_wdi(path: Path = RAW_JSON) -> tuple[pd.DataFrame, QualityReport]:
    report = QualityReport(source="world_bank_wdi", input_file=Path(path).name)
    meta, rows = json.loads(Path(path).read_text())[:2]
    df = pd.DataFrame(
        {
            "iso3": [r["countryiso3code"] for r in rows],
            "year": [int(r["date"]) for r in rows],
            "gdp_pc_const2015_usd": [r["value"] for r in rows],
        }
    )
    report.rows_in = len(df)
    df["gdp_pc_const2015_usd"] = pd.to_numeric(df["gdp_pc_const2015_usd"], errors="coerce").astype("Float64")
    miss = int(df["gdp_pc_const2015_usd"].isna().sum())
    report.add("missing_gdp_pc", "warn" if miss else "pass", miss, len(df),
               f"{miss} country-years without a value (kept as missing).")  # fmt: skip
    dup = df.duplicated(["iso3", "year"])
    report.add("duplicate_country_year", "fail" if dup.any() else "pass", int(dup.sum()), len(df),
               "Each country-year must appear once.")  # fmt: skip
    df = df.loc[~dup]
    df["country"] = df["iso3"].map(countries.display_name)
    report.transformations += [
        f"Indicator {INDICATOR} (GDP per capita, constant 2015 US$), API last updated {meta.get('lastupdated')}.",
        "Null values kept as missing.",
    ]
    report.rows_out = len(df)
    have = df.dropna(subset=["gdp_pc_const2015_usd"])
    report.coverage = {"year_min": int(have["year"].min()), "year_max": int(have["year"].max()),
                       "n_entities": int(have["iso3"].nunique())}  # fmt: skip
    return df.reset_index(drop=True), report
