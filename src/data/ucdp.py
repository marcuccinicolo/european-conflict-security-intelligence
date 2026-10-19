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
    df = _europe(raw, report)
    return _map(df, report, "ucdp_ged", earliest="1989-01-01", check_boundaries=check_boundaries)


def load_candidate(paths: list[Path], year: int, check_boundaries: bool = True
                   ) -> tuple[pd.DataFrame, QualityReport]:  # fmt: skip
    """UCDP Candidate Events (provisional, monthly). ``paths`` in release order, oldest first.

    Monthly releases contain every event whose start OR end date falls in the month,
    so an event spanning two months appears twice. Duplicates are resolved on the
    persistent ``id`` keeping the LATEST release, which carries any revision.
    """
    report = QualityReport(source="ucdp_candidate", input_file=", ".join(Path(p).name for p in paths))
    frames = []
    for order, p in enumerate(paths):
        raw = read_raw(p)
        require_columns(raw, REQUIRED + ["code_status"], report)
        frames.append(raw.assign(_release=order))
    raw = pd.concat(frames, ignore_index=True)
    df = _europe(raw, report)
    dup = df.duplicated(subset=["id"], keep="last")
    report.add("duplicate_ids_across_releases", "info" if dup.any() else "pass", int(dup.sum()), len(df),
               "Events present in more than one monthly release (start and end in different months).",
               "latest release kept" if dup.any() else "none")  # fmt: skip
    df = df.sort_values("_release").drop_duplicates(subset=["id"], keep="last")
    start_year = pd.to_datetime(df["date_start"].astype(str).str[:10], errors="coerce").dt.year
    outside = start_year != year
    report.add("outside_candidate_year", "info" if outside.any() else "pass", int(outside.sum()), len(df),
               f"Events starting before {year} (already covered by the annual GED release).",
               "dropped" if outside.any() else "none")  # fmt: skip
    df = df.loc[~outside]
    status = df["code_status"].astype("string").fillna("missing")
    for k, v in status.value_counts().items():
        report.add(f"code_status[{k}]", "info", int(v), len(df), f"{int(v)} events with code_status '{k}'.")
    report.transformations += [
        f"Releases combined in order: {report.input_file}; duplicate ids resolved to the latest release.",
        f"Restricted to events starting in {year} (the year after the latest annual GED).",
        "PROVISIONAL: Candidate data relax the 25-death annual threshold and are revised in the annual GED; "
        "counts are not comparable with UCDP GED.",
    ]
    return _map(df, report, "ucdp_candidate", earliest=f"{year}-01-01", check_boundaries=check_boundaries)


def _europe(raw: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    europe = raw["region"].astype("string").str.contains("Europe", na=False)
    report.rows_in = int(europe.sum())
    report.transformations.append(
        f"Selected UCDP region containing 'Europe': {int(europe.sum())} of {len(raw)} global events."
    )
    return raw.loc[europe].copy()


def _map(df: pd.DataFrame, report: QualityReport, source: str, earliest: str,
         check_boundaries: bool = True) -> tuple[pd.DataFrame, QualityReport]:  # fmt: skip

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
            "event_id": ("ucdp-" if source == "ucdp_ged" else "ucdpc-") + df["id"].astype(str),
            "source": source,
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
            "code_status": df["code_status"] if "code_status" in df else pd.NA,
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
    return finalize_events(out, report, earliest=earliest, check_boundaries=check_boundaries), report
