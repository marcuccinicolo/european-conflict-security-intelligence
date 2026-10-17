"""Canonical schemas shared by every source adapter.

All conflict sources are mapped to ONE event schema and all expenditure sources
to ONE long-format indicator schema. Source-specific meaning is preserved in
explicit columns (``source``, ``fatalities_kind``, ``unit``, ``price_basis``)
rather than being silently harmonised away.
"""

from __future__ import annotations

EVENT_COLUMNS: dict[str, str] = {
    "event_id": "string",  # source event identifier, unique within a source
    "source": "string",  # ucdp_ged | acled | synthetic
    "data_status": "string",  # real | synthetic
    "event_date": "datetime64[ns]",  # start date of the event
    "year": "Int64",
    "date_uncertain": "boolean",  # True when the source reports a date range / low precision
    "country": "string",  # harmonised display name
    "iso3": "string",
    "subregion": "string",
    "admin1": "string",
    "latitude": "Float64",  # NaN when missing or invalid
    "longitude": "Float64",
    "coord_status": "string",  # valid | missing | out_of_range | null_island
    "coord_check": "string",  # inside | within_10km | elsewhere | not_checked
    "location_precise": "boolean",  # True when located to (approx.) the named place
    "event_type": "string",
    "sub_event_type": "string",  # ACLED sub-event type; null for UCDP
    "conflict_name": "string",  # UCDP conflict; null for ACLED
    "fatalities": "Float64",  # best estimate (UCDP) or reported (ACLED); NaN = not reported
    "fatalities_low": "Float64",
    "fatalities_high": "Float64",
    "fatalities_kind": "string",  # estimate | reported
    "n_sources": "Int64",  # number of source reports (UCDP only)
}

MILEX_COLUMNS: dict[str, str] = {
    "source": "string",
    "data_status": "string",
    "country": "string",
    "iso3": "string",
    "subregion": "string",
    "entity_type": "string",  # country | historical | aggregate
    "year": "Int64",
    "indicator": "string",
    "unit": "string",
    "price_basis": "string",
    "value": "Float64",  # NaN = unavailable; never zero-filled
    "value_flag": "string",  # reported | estimate | highly_uncertain | unavailable | not_independent
}

# Indicator catalogue: one entry per indicator. Nothing that has a different unit
# or price basis may be combined in a single comparison (see analysis.defence).
MILEX_INDICATORS: dict[str, dict[str, str]] = {
    "milex_constant_usd_m": {
        "label": "Military expenditure, constant (2024) US$ m",
        "unit": "US$ million",
        "price_basis": "constant 2024 prices and exchange rates",
        "sheet": "Constant (2024) US$",
        "scale": "1",
        "definition": "SIPRI military expenditure deflated by the US CPI to 2024 prices "
        "and converted at 2024 exchange rates. Suitable for real growth over time.",
    },
    "milex_current_usd_m": {
        "label": "Military expenditure, current US$ m",
        "unit": "US$ million",
        "price_basis": "current prices and exchange rates",
        "sheet": "Current US$",
        "scale": "1",
        "definition": "Nominal military expenditure converted at each year's market "
        "exchange rate. Not suitable for real growth comparisons.",
    },
    "share_gdp_pct": {
        "label": "Military expenditure, % of GDP",
        "unit": "% of GDP",
        "price_basis": "ratio (both terms in current local currency)",
        "sheet": "Share of GDP",
        "scale": "100",  # SIPRI stores a fraction; we convert to percent
        "definition": "Military expenditure divided by gross domestic product, both in "
        "current local currency. Denominator: GDP.",
    },
    "per_capita_current_usd": {
        "label": "Military expenditure per capita, current US$",
        "unit": "US$ per person",
        "price_basis": "current prices and exchange rates",
        "sheet": "Per capita",
        "scale": "1",
        "definition": "Military expenditure in current US$ divided by population. "
        "Denominator: population.",
    },
    "share_govt_pct": {
        "label": "Military expenditure, % of government spending",
        "unit": "% of general government expenditure",
        "price_basis": "ratio (both terms in current local currency)",
        "sheet": "Share of Govt. spending",
        "scale": "100",
        "definition": "Military expenditure divided by general government expenditure. "
        "Denominator: total government spending.",
    },
}


def empty_events():
    import pandas as pd

    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in EVENT_COLUMNS.items()})


def conform(df, columns: dict[str, str]):
    """Return ``df`` with exactly the schema columns, in order, with schema dtypes."""
    import pandas as pd

    out = pd.DataFrame(index=df.index)
    for col, dtype in columns.items():
        s = df[col] if col in df.columns else pd.Series(pd.NA, index=df.index)
        if dtype.startswith("datetime"):
            s = pd.to_datetime(s, errors="coerce")
        else:
            s = s.astype(dtype)
        out[col] = s
    return out.reset_index(drop=True)
