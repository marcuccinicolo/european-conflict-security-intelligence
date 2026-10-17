"""Missingness and data-quality diagnostics for the current selection."""

from __future__ import annotations

import pandas as pd

# Columns that are null BY DESIGN for some sources (not a quality problem).
STRUCTURAL_NULLS = {
    "ucdp_ged": {"sub_event_type"},
    "acled": {"conflict_name", "fatalities_low", "fatalities_high", "n_sources"},
    "synthetic_events": {"conflict_name", "fatalities_low", "fatalities_high", "n_sources"},
}


def missingness(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Share of nulls per column, marking columns that are structurally empty."""
    structural = STRUCTURAL_NULLS.get(source, set())
    out = pd.DataFrame(
        {
            "column": df.columns,
            "missing": [int(df[c].isna().sum()) for c in df.columns],
        }
    )
    out["share_missing"] = out["missing"] / max(len(df), 1)
    out["note"] = out["column"].map(
        lambda c: "not provided by this source" if c in structural else ""
    )
    return out.sort_values("share_missing", ascending=False, ignore_index=True)


def milex_coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Per-country count of years by value flag for one indicator."""
    return (
        df.groupby(["country", "value_flag"]).size().unstack(fill_value=0).reset_index()
    )
