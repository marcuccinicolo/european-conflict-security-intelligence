"""ACLED adapter: local CSV exports (and the synthetic demo, which uses ACLED's layout).

ACLED data require a myACLED account and are licensed under ACLED's EULA, which
forbids redistributing raw data. This module therefore only *reads* files the
user has obtained themselves (via the export tool or ``src.data.fetch``) from
``data/raw/acled/``, which is git-ignored.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.events import finalize_events
from src.data.validation import QualityReport, parse_dates, require_columns, to_nullable_number

REQUIRED = [
    "event_id_cnty", "event_date", "event_type", "sub_event_type",
    "country", "latitude", "longitude", "fatalities",
]  # fmt: skip

# ISO first; then ACLED's long export format; then day-first slash dates, which
# is the convention in ACLED's European-style exports. US month-first dates are
# deliberately NOT tried, so 03/04/2024 is never silently read as 4 March.
DATE_FORMATS = ("%Y-%m-%d", "%d %B %Y", "%d/%m/%Y")

# geo_precision 1 = exact town/village coordinates.
PRECISE_GEO = {1}


def load_acled_csv(
    path: Path, source: str = "acled", check_boundaries: bool = True
) -> tuple[pd.DataFrame, QualityReport]:
    """Load an ACLED-format CSV. ``source='synthetic_events'`` marks the demo file."""
    if source not in {"acled", "synthetic_events"}:
        raise ValueError("source must be 'acled' or 'synthetic_events'")
    report = QualityReport(source=source, input_file=Path(path).name)
    raw = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    report.rows_in = len(raw)
    require_columns(raw, REQUIRED, report)

    if source == "synthetic_events":
        status = raw.get("data_status", pd.Series("", index=raw.index)).str.upper()
        if not (status == "SYNTHETIC").all():
            raise ValueError("Synthetic file must label every row data_status=SYNTHETIC")

    dates = parse_dates(raw["event_date"], report, DATE_FORMATS)
    fat = to_nullable_number(raw["fatalities"])
    neg = fat < 0
    report.add(
        "fatalities_non_negative",
        "fail" if neg.fillna(False).any() else "pass",
        int(neg.fillna(False).sum()),
        len(raw),
        "Negative fatality values set to missing.",
    )
    fat = fat.mask(neg.fillna(False))

    geo_prec = _optional_number(raw, "geo_precision")
    time_prec = _optional_number(raw, "time_precision")
    out = pd.DataFrame(
        {
            "event_id": raw["event_id_cnty"],
            "source": source,
            "data_status": "synthetic" if source == "synthetic_events" else "real",
            "event_date": dates,
            "date_uncertain": (time_prec > 1).astype("boolean").mask(time_prec.isna()),
            "country": raw["country"].str.strip(),
            "admin1": raw["admin1"] if "admin1" in raw else pd.NA,
            "latitude": raw["latitude"],
            "longitude": raw["longitude"],
            "location_precise": geo_prec.isin(PRECISE_GEO).astype("boolean").mask(geo_prec.isna()),
            "event_type": raw["event_type"],
            "sub_event_type": raw["sub_event_type"],
            "conflict_name": pd.NA,
            "fatalities": fat,
            "fatalities_kind": "reported",
        }
    )
    report.transformations += [
        "event_date parsed with explicit formats " + ", ".join(DATE_FORMATS) + ".",
        "fatalities: blank -> missing (never 0); ACLED reports conservative counts.",
        "location_precise = geo_precision == 1; date_uncertain = time_precision > 1.",
    ]
    return finalize_events(out, report, earliest="1997-01-01", check_boundaries=check_boundaries), report


def _optional_number(raw: pd.DataFrame, col: str) -> pd.Series:
    if col not in raw.columns:
        return pd.Series(pd.NA, index=raw.index, dtype="Float64")
    return pd.to_numeric(raw[col], errors="coerce").astype("Float64")


def acled_files(raw_dir: Path) -> list[Path]:
    return sorted(p for p in Path(raw_dir).glob("*.csv") if not p.name.startswith("."))


def load_acled_dir(raw_dir: Path, check_boundaries: bool = True):
    """Concatenate every ACLED CSV in ``raw_dir``; duplicates across files are dropped."""
    files = acled_files(raw_dir)
    if not files:
        return None, None
    if len(files) == 1:
        return load_acled_csv(files[0], check_boundaries=check_boundaries)
    combined = pd.concat([pd.read_csv(f, dtype=str) for f in files], ignore_index=True)
    tmp = Path(raw_dir) / ".combined.csv"
    combined.to_csv(tmp, index=False)
    try:
        df, report = load_acled_csv(tmp, check_boundaries=check_boundaries)
    finally:
        tmp.unlink(missing_ok=True)
    report.input_file = ", ".join(f.name for f in files)
    return df, report
