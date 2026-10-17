"""Source-independent steps applied to every conflict-event dataset."""

from __future__ import annotations

import pandas as pd

from src.data import countries
from src.data.boundaries import check_points_in_country, load_boundaries
from src.data.schema import EVENT_COLUMNS, conform
from src.data.validation import (
    QualityReport,
    check_date_range,
    classify_coordinates,
    drop_duplicate_ids,
    flag_possible_duplicates,
    report_coordinates,
    report_missing,
)


def finalize_events(
    df: pd.DataFrame, report: QualityReport, earliest: str, check_boundaries: bool = True
) -> pd.DataFrame:
    """Common validation and enrichment.

    ``df`` must already carry the canonical column names with ``country`` holding
    the *source* spelling and ``event_date`` parsed (NaT where unparseable).
    """
    report.rows_in = report.rows_in or len(df)

    df = drop_duplicate_ids(df, "event_id", report)

    no_date = df["event_date"].isna()
    df = df.loc[~no_date]
    out_of_range = check_date_range(df["event_date"], report, earliest)
    df = df.loc[~out_of_range].copy()
    df["year"] = df["event_date"].dt.year

    # Country harmonisation - unknown names are reported and kept out.
    df["iso3"] = df["country"].map(countries.to_iso3)
    unknown = df["iso3"].isna()
    names = sorted(df.loc[unknown, "country"].dropna().astype(str).unique().tolist())
    report.add(
        "country_harmonisation",
        "warn" if unknown.any() else "pass",
        int(unknown.sum()),
        len(df),
        f"Unmapped country names: {names}" if names else "All country names mapped to ISO3.",
        "unmapped rows dropped (outside European scope)" if unknown.any() else "none",
    )
    df = df.loc[~unknown].copy()
    df["country"] = df["iso3"].map(countries.display_name)
    df["subregion"] = df["iso3"].map(countries.subregion)

    # Coordinates: invalid values become null; the event still counts.
    df["coord_status"] = classify_coordinates(df["latitude"], df["longitude"])
    report_coordinates(df["coord_status"], report)
    bad = df["coord_status"] != "valid"
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce").astype("Float64").mask(bad)
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce").astype("Float64").mask(bad)

    boundaries = load_boundaries() if check_boundaries else None
    df["coord_check"] = check_points_in_country(df, boundaries)
    checked = df["coord_check"] != "not_checked"
    elsewhere = int((df["coord_check"] == "elsewhere").sum())
    by_country = (
        df.loc[df["coord_check"] == "elsewhere", "country"].value_counts().head(5).to_dict()
    )
    report.add(
        "coordinates_inside_stated_country",
        "not_run" if boundaries is None else ("warn" if elsewhere else "pass"),
        elsewhere,
        int(checked.sum()),
        (
            "Boundary file not available; check skipped."
            if boundaries is None
            else f"{elsewhere} points fall more than 10 km outside the stated country "
            f"(Natural Earth 1:50m, present-day borders). Top stated countries: {by_country}. "
            "Expected where the source codes the state that existed at the time (UCDP: "
            "'Serbia (Yugoslavia)' for 1991-99 events in Croatia, Bosnia and Kosovo; "
            "'Russia (Soviet Union)' for 1989-91 events in the Caucasus) and in contested "
            "areas (Natural Earth draws Crimea as Russia; UCDP codes it Ukraine)."
        ),
        "flagged only; coordinates kept",
    )

    flag_possible_duplicates(df, ["event_date", "latitude", "longitude", "event_type"], report)
    report_missing(df, ["fatalities", "admin1"], report)

    out = conform(df, EVENT_COLUMNS)
    report.rows_out = len(out)
    if len(out):
        report.coverage = {
            "date_min": str(out["event_date"].min().date()),
            "date_max": str(out["event_date"].max().date()),
            "n_countries": int(out["iso3"].nunique()),
            "countries": sorted(out["country"].unique().tolist()),
            "events": int(len(out)),
        }
    return out
