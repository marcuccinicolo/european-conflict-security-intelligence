"""Validation primitives and the machine-readable data-quality report.

Every adapter records what it checked and what it changed in a ``QualityReport``.
The report is written to ``reports/data_quality/<source>.json`` and loaded into
the database, so the dashboard shows exactly the same numbers as the files.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


class SchemaError(ValueError):
    """Raised when an input file is missing columns the adapter cannot do without."""


@dataclass
class Check:
    name: str
    status: str  # pass | warn | fail | info
    affected_rows: int
    total_rows: int
    detail: str
    action: str = "none"

    @property
    def share(self) -> float:
        return self.affected_rows / self.total_rows if self.total_rows else 0.0


@dataclass
class QualityReport:
    source: str
    input_file: str
    rows_in: int = 0
    rows_out: int = 0
    checks: list[Check] = field(default_factory=list)
    transformations: list[str] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def add(self, name, status, affected, total, detail, action="none") -> Check:
        chk = Check(name, status, int(affected), int(total), detail, action)
        self.checks.append(chk)
        return chk

    def to_dict(self) -> dict:
        d = asdict(self)
        for c, chk in zip(d["checks"], self.checks):
            c["share"] = round(chk.share, 6)
        d["summary"] = {
            s: sum(1 for c in self.checks if c.status == s)
            for s in ("pass", "warn", "fail", "info", "not_run")
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "QualityReport":
        keys = ("name", "status", "affected_rows", "total_rows", "detail", "action")
        checks = [Check(**{k: c[k] for k in keys}) for c in d["checks"]]
        return cls(
            source=d["source"], input_file=d["input_file"], rows_in=d["rows_in"],
            rows_out=d["rows_out"], checks=checks, transformations=list(d["transformations"]),
            coverage=d["coverage"], generated_at=d["generated_at"],
        )  # fmt: skip

    def write(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.source}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str))
        return path


def require_columns(df: pd.DataFrame, required: list[str], report: QualityReport) -> None:
    missing = [c for c in required if c not in df.columns]
    report.add(
        "required_columns",
        "fail" if missing else "pass",
        len(missing),
        len(required),
        f"Missing: {missing}" if missing else f"All {len(required)} required columns present.",
    )
    if missing:
        raise SchemaError(f"{report.source}: missing required columns {missing}")


def parse_dates(
    values: pd.Series, report: QualityReport, formats: tuple[str, ...] = ("%Y-%m-%d",)
) -> pd.Series:
    """Parse dates trying each explicit format in turn - never ``dayfirst`` guessing.

    ISO 8601 is tried first. A value that matches no format becomes NaT and is
    counted. Values parsed by a non-primary format are reported as a format
    inconsistency so that the analyst can see it happened.
    """
    raw = values.astype("string").str.strip()
    # Drop a trailing time component ("2024-01-02 00:00:00.000") before matching.
    raw = raw.str.replace(r"[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$", "", regex=True)
    out = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    used = {}
    for fmt in formats:
        todo = out.isna() & raw.notna()
        if not todo.any():
            break
        parsed = pd.to_datetime(raw[todo], format=fmt, errors="coerce")
        out.loc[todo] = parsed
        used[fmt] = int(parsed.notna().sum())
    n = len(values)
    failed = int((out.isna() & raw.notna()).sum()) + int(raw.isna().sum())
    secondary = sum(v for k, v in used.items() if k != formats[0])
    report.add(
        "date_parse",
        "fail" if failed else "pass",
        failed,
        n,
        f"Formats used: {used}. Unparseable or empty dates: {failed}.",
        "rows with unparseable dates dropped" if failed else "none",
    )
    report.add(
        "date_format_consistency",
        "warn" if secondary else "pass",
        secondary,
        n,
        f"{secondary} dates were not in the primary format {formats[0]!r} and were parsed "
        "with an explicit secondary format.",
    )
    return out


def check_date_range(
    dates: pd.Series, report: QualityReport, earliest: str, latest: str | None = None
) -> pd.Series:
    """Flag dates before ``earliest`` or after ``latest`` (default: today)."""
    lo = pd.Timestamp(earliest)
    hi = pd.Timestamp(latest) if latest else pd.Timestamp.today().normalize()
    bad = dates.notna() & ((dates < lo) | (dates > hi))
    report.add(
        "date_range",
        "fail" if bad.any() else "pass",
        int(bad.sum()),
        len(dates),
        f"Expected {lo.date()} to {hi.date()}.",
        "out-of-range rows dropped" if bad.any() else "none",
    )
    return bad


def classify_coordinates(lat: pd.Series, lon: pd.Series) -> pd.Series:
    """Return a coordinate status per row: valid | missing | out_of_range | null_island."""
    lat = pd.to_numeric(lat, errors="coerce")
    lon = pd.to_numeric(lon, errors="coerce")
    status = pd.Series("valid", index=lat.index, dtype="string")
    status[lat.isna() | lon.isna()] = "missing"
    oor = lat.notna() & lon.notna() & ((lat.abs() > 90) | (lon.abs() > 180))
    status[oor] = "out_of_range"
    status[(lat == 0) & (lon == 0)] = "null_island"
    return status


def report_coordinates(status: pd.Series, report: QualityReport) -> None:
    n = len(status)
    for kind, label in [
        ("missing", "coordinates_missing"),
        ("out_of_range", "coordinates_out_of_range"),
        ("null_island", "coordinates_null_island"),
    ]:
        k = int((status == kind).sum())
        report.add(
            label,
            "warn" if k else "pass",
            k,
            n,
            f"{k} rows with status '{kind}'.",
            "coordinates set to null; event kept for counts, excluded from map" if k else "none",
        )


def drop_duplicate_ids(df: pd.DataFrame, id_col: str, report: QualityReport) -> pd.DataFrame:
    dup = df.duplicated(subset=[id_col], keep="first")
    report.add(
        "duplicate_event_ids",
        "warn" if dup.any() else "pass",
        int(dup.sum()),
        len(df),
        f"{int(dup.sum())} rows repeat an event id already seen.",
        "later duplicates dropped (first occurrence kept)" if dup.any() else "none",
    )
    return df.loc[~dup]


def flag_possible_duplicates(df: pd.DataFrame, keys: list[str], report: QualityReport) -> None:
    """Report (but do not drop) rows sharing date, place and type under different ids.

    These can be legitimate distinct events, so they are informational only.
    """
    sub = df.dropna(subset=keys)
    k = int(sub.duplicated(subset=keys, keep=False).sum())
    report.add(
        "possible_duplicate_events",
        "info",
        k,
        len(df),
        f"{k} rows share {keys} with at least one other row under a different id. "
        "Not removed: same-day events at the same coordinates can be distinct.",
    )


def report_missing(df: pd.DataFrame, columns: list[str], report: QualityReport) -> None:
    n = len(df)
    for col in columns:
        k = int(df[col].isna().sum())
        report.add(
            f"missing_{col}",
            "warn" if k else "pass",
            k,
            n,
            f"{k} null values in '{col}'. Nulls are kept as missing, never filled with 0.",
        )


def to_nullable_number(values: pd.Series) -> pd.Series:
    """Convert to numeric; blanks and non-numeric strings become NA (never zero)."""
    return pd.to_numeric(values.replace({"": np.nan}), errors="coerce").astype("Float64")
