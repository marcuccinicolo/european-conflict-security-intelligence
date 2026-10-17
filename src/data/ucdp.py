"""UCDP GED adapter (CC BY 4.0).

Input: the official ``ged261-csv.zip`` (or the extracted CSV) from
https://ucdp.uu.se/downloads/. The European subset is selected with the UCDP
``region`` field, which is UCDP's own regional classification.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

from src.data.events import finalize_events
from src.data.validation import QualityReport, parse_dates, require_columns, to_nullable_number

REQUIRED = [
    "id", "year", "type_of_violence", "conflict_name", "where_prec", "adm_1",
    "latitude", "longitude", "country", "region", "date_prec", "date_start",
    "date_end", "best", "low", "high", "number_of_sources",
]  # fmt: skip

VIOLENCE_TYPES = {
    1: "State-based conflict",
    2: "Non-state conflict",
    3: "One-sided violence",
}

# where_prec 1 = exact location, 2 = within ~25 km of a known point.
PRECISE_WHERE = {1, 2}


def read_raw(path: Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            with z.open(name) as fh:
                return pd.read_csv(fh, low_memory=False)
    return pd.read_csv(path, low_memory=False)


def load_ucdp(path: Path, check_boundaries: bool = True) -> tuple[pd.DataFrame, QualityReport]:
    report = QualityReport(source="ucdp_ged", input_file=Path(path).name)
    raw = read_raw(path)
    require_columns(raw, REQUIRED, report)

    europe = raw["region"].astype("string").str.contains("Europe", na=False)
    report.rows_in = int(europe.sum())
    report.transformations.append(
        f"Selected UCDP region containing 'Europe': {int(europe.sum())} of {len(raw)} global events."
    )
    df = raw.loc[europe].copy()

    start = parse_dates(df["date_start"], report)
    end = parse_dates(df["date_end"], QualityReport("tmp", ""))
    inverted = start.notna() & end.notna() & (end < start)
    report.add(
        "date_start_before_end",
        "fail" if inverted.any() else "pass",
        int(inverted.sum()),
        len(df),
        "date_end must not precede date_start.",
    )

    best, low, high = (to_nullable_number(df[c]) for c in ("best", "low", "high"))
    bad_order = (low > best) | (best > high)
    report.add(
        "fatality_bounds_ordered",
        "warn" if bad_order.fillna(False).any() else "pass",
        int(bad_order.fillna(False).sum()),
        len(df),
        "Expected low <= best <= high for every event.",
    )
    yr_mismatch = start.notna() & (start.dt.year != df["year"])
    report.add(
        "year_matches_date",
        "warn" if yr_mismatch.any() else "pass",
        int(yr_mismatch.sum()),
        len(df),
        "UCDP 'year' should equal the year of date_start.",
    )

    out = pd.DataFrame(
        {
            "event_id": "ucdp-" + df["id"].astype(str),
            "source": "ucdp_ged",
            "data_status": "real",
            "event_date": start,
            "date_uncertain": df["date_prec"] > 1,
            "country": df["country"],
            "admin1": df["adm_1"].replace({"": pd.NA}),
            "latitude": df["latitude"],
            "longitude": df["longitude"],
            "location_precise": df["where_prec"].isin(PRECISE_WHERE),
            "event_type": df["type_of_violence"].map(VIOLENCE_TYPES),
            "sub_event_type": pd.NA,
            "conflict_name": df["conflict_name"],
            "fatalities": best,
            "fatalities_low": low,
            "fatalities_high": high,
            "fatalities_kind": "estimate",
            "n_sources": pd.to_numeric(df["number_of_sources"], errors="coerce"),
        }
    )
    # UCDP uses -1 for "number of sources unknown" in older versions.
    out.loc[out["n_sources"] < 0, "n_sources"] = pd.NA
    report.transformations += [
        "event_date = date_start (events spanning several days are dated by their start).",
        "date_uncertain = date_prec > 1 (date known only to a range of days or wider).",
        "location_precise = where_prec in {1, 2} (exact place or within ~25 km).",
        "event_type = UCDP type_of_violence label; fatalities = UCDP 'best' estimate.",
        "Country names mapped to ISO3 (e.g. 'Russia (Soviet Union)' -> RUS).",
    ]
    return finalize_events(out, report, earliest="1989-01-01", check_boundaries=check_boundaries), report
