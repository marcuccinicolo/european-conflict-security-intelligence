"""Descriptive analysis of conflict events (pure pandas, no UI code).

Conventions used throughout:

* An *event count* is the number of distinct source records in the selection.
  It is a count of **reported/recorded** events, not of all incidents that occurred.
* Fatality totals sum the source's figure (UCDP 'best' estimate, ACLED reported
  count). Missing values are excluded - never treated as zero - and every
  fatality figure is returned together with the number of events it covers.
* A period with no records has an event count of 0 ("no recorded events");
  its fatality total is also 0 because there are no events to be missing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FREQ = {"Month": "MS", "Quarter": "QS", "Year": "YS"}


def _check_single_source(df: pd.DataFrame) -> None:
    if "source" in df and df["source"].nunique() > 1:
        raise ValueError(
            "Selection mixes sources "
            f"{sorted(df['source'].unique())}; aggregate one source at a time."
        )


def temporal_counts(
    df: pd.DataFrame,
    freq: str = "Month",
    by: str | None = None,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Events and fatalities per period, with empty periods filled explicitly.

    Returns columns: period, [by], events, fatalities, events_with_fatality_data.
    """
    _check_single_source(df)
    rule = FREQ.get(freq, freq)
    keys = [by] if by else []
    if df.empty:
        return pd.DataFrame(columns=["period", *keys, "events", "fatalities",
                                     "events_with_fatality_data"])  # fmt: skip
    d = df.assign(period=df["event_date"].dt.to_period(rule[0]).dt.start_time)
    g = d.groupby(["period", *keys], observed=True)
    out = g.agg(
        events=("event_id", "size"),
        fatalities=("fatalities", lambda s: s.sum(min_count=1)),
        events_with_fatality_data=("fatalities", "count"),
    ).reset_index()

    lo = pd.Timestamp(start) if start is not None else d["period"].min()
    hi = pd.Timestamp(end) if end is not None else d["period"].max()
    periods = pd.date_range(
        pd.Timestamp(lo).to_period(rule[0]).start_time,
        pd.Timestamp(hi).to_period(rule[0]).start_time,
        freq=rule,
    )
    if by:
        full = pd.MultiIndex.from_product([periods, sorted(d[by].dropna().unique())],
                                          names=["period", by])  # fmt: skip
    else:
        full = pd.Index(periods, name="period")
    out = out.set_index(["period", *keys]).reindex(full).reset_index()
    out["events"] = out["events"].fillna(0).astype(int)
    out["events_with_fatality_data"] = out["events_with_fatality_data"].fillna(0).astype(int)
    # A period with zero events has zero fatalities; a period whose events all
    # lack fatality data stays missing.
    empty = out["events"] == 0
    out["fatalities"] = out["fatalities"].astype("Float64").mask(empty, 0)
    return out


def country_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per country with counts, fatalities and data-coverage shares."""
    _check_single_source(df)
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("country", observed=True)
    out = g.agg(
        events=("event_id", "size"),
        fatalities=("fatalities", lambda s: s.sum(min_count=1)),
        events_with_fatality_data=("fatalities", "count"),
        precise_location=("location_precise", lambda s: s.astype("boolean").mean()),
        first_event=("event_date", "min"),
        last_event=("event_date", "max"),
    ).reset_index()
    out["share_of_events"] = out["events"] / out["events"].sum()
    out["fatality_data_coverage"] = out["events_with_fatality_data"] / out["events"]
    return out.sort_values("events", ascending=False, ignore_index=True)


def category_summary(df: pd.DataFrame, level: str = "event_type") -> pd.DataFrame:
    """Counts and fatalities by event category (or sub-type / conflict)."""
    _check_single_source(df)
    if df.empty or level not in df or df[level].isna().all():
        return pd.DataFrame(columns=[level, "events", "fatalities", "share_of_events"])
    g = df.groupby(df[level].fillna("Not specified"), observed=True)
    out = g.agg(
        events=("event_id", "size"),
        fatalities=("fatalities", lambda s: s.sum(min_count=1)),
        events_with_fatality_data=("fatalities", "count"),
    ).reset_index()
    out["share_of_events"] = out["events"] / out["events"].sum()
    out["fatalities_per_event"] = out["fatalities"] / out["events_with_fatality_data"].replace(0, np.nan)
    return out.sort_values("events", ascending=False, ignore_index=True)


def period_comparison(
    df: pd.DataFrame,
    period_a: tuple[str, str],
    period_b: tuple[str, str],
    by: str = "country",
    min_base: int = 10,
) -> pd.DataFrame:
    """Compare event counts between two date windows of EQUAL length.

    Percentage change is reported only when the baseline has at least
    ``min_base`` events; smaller bases give unstable, misleading percentages.
    """
    _check_single_source(df)
    a0, a1 = map(pd.Timestamp, period_a)
    b0, b1 = map(pd.Timestamp, period_b)
    if (a1 - a0) != (b1 - b0):
        raise ValueError("Comparison windows must have equal length.")
    in_a = df[(df["event_date"] >= a0) & (df["event_date"] <= a1)]
    in_b = df[(df["event_date"] >= b0) & (df["event_date"] <= b1)]
    out = pd.concat(
        [in_a.groupby(by).size().rename("events_a"), in_b.groupby(by).size().rename("events_b")],
        axis=1,
    ).fillna(0).astype(int)
    out["change"] = out["events_b"] - out["events_a"]
    out["pct_change"] = np.where(
        out["events_a"] >= min_base, out["change"] / out["events_a"].replace(0, np.nan) * 100, np.nan
    )
    return out.reset_index().sort_values("events_b", ascending=False, ignore_index=True)


def completeness_over_time(df: pd.DataFrame, freq: str = "Year") -> pd.DataFrame:
    """Reporting-quality indicators per period.

    These describe the *records*, not the conflict: a rising share of precisely
    located events, or more sources per event, signals changing coverage that
    can move event counts on its own.
    """
    _check_single_source(df)
    if df.empty:
        return pd.DataFrame()
    rule = FREQ.get(freq, freq)
    d = df.assign(period=df["event_date"].dt.to_period(rule[0]).dt.start_time)
    g = d.groupby("period")
    out = g.agg(
        events=("event_id", "size"),
        share_precise_location=("location_precise", lambda s: s.astype("boolean").mean()),
        share_date_uncertain=("date_uncertain", lambda s: s.astype("boolean").mean()),
        share_with_fatality_data=("fatalities", lambda s: s.notna().mean()),
        share_valid_coordinates=("coord_status", lambda s: (s == "valid").mean()),
        mean_sources_per_event=("n_sources", "mean"),
    ).reset_index()
    return out


def headline_metrics(df: pd.DataFrame) -> dict:
    """Well-defined KPIs for the current selection, each with its denominator."""
    _check_single_source(df)
    n = len(df)
    fat = df["fatalities"]
    has_fat = int(fat.notna().sum())
    out = {
        "events": n,
        "countries": int(df["country"].nunique()) if n else 0,
        "fatalities": float(fat.sum()) if has_fat else None,
        "events_with_fatality_data": has_fat,
        "fatality_data_coverage": has_fat / n if n else None,
        "share_precise_location": float(df["location_precise"].astype("boolean").mean())
        if n and df["location_precise"].notna().any()
        else None,
        "date_min": df["event_date"].min() if n else None,
        "date_max": df["event_date"].max() if n else None,
    }
    if "fatalities_low" in df and df["fatalities_low"].notna().any():
        out["fatalities_low"] = float(df["fatalities_low"].sum())
        out["fatalities_high"] = float(df["fatalities_high"].sum())
    return out
