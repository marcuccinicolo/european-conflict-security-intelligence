"""Military-expenditure analysis with explicit units and price bases.

Rules enforced in code, not only in documentation:

* A frame passed to any function here must contain exactly ONE indicator, so a
  single unit and price basis (``assert_single_indicator``).
* Growth rates are computed only on constant-price series or on ratios.
  Growth of current-US$ series mixes inflation and exchange-rate movements and
  is refused unless ``allow_nominal=True`` is passed deliberately.
* Missing values stay missing. Totals across countries are computed only on a
  balanced panel (countries with data in every year), and the excluded
  countries are returned alongside the total.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.schema import MILEX_INDICATORS

NOMINAL = {"milex_current_usd_m", "per_capita_current_usd"}
RATIOS = {"share_gdp_pct", "share_govt_pct"}


class IncompatibleUnitsError(ValueError):
    pass


def assert_single_indicator(df: pd.DataFrame) -> str:
    inds = df["indicator"].dropna().unique()
    if len(inds) != 1:
        raise IncompatibleUnitsError(f"Expected one indicator, got {sorted(inds)}")
    units = df[["unit", "price_basis"]].drop_duplicates()
    if len(units) != 1:
        raise IncompatibleUnitsError(f"Mixed units/price bases: {units.to_dict('records')}")
    if "source" in df and df["source"].nunique() != 1:
        raise IncompatibleUnitsError("Mixed sources in one comparison.")
    return str(inds[0])


def wide(df: pd.DataFrame) -> pd.DataFrame:
    """Year x country matrix of values (NaN where unavailable)."""
    assert_single_indicator(df)
    return df.pivot_table(index="year", columns="country", values="value", aggfunc="first").astype(float)


def growth(
    df: pd.DataFrame, periods: int = 1, allow_nominal: bool = False
) -> pd.DataFrame:
    """Percentage change over ``periods`` years for each country.

    For ratio indicators (% of GDP) the change is reported in percentage
    *points* (``change_pp``), not percent, to avoid ambiguity.
    """
    ind = assert_single_indicator(df)
    if ind in NOMINAL and not allow_nominal:
        raise IncompatibleUnitsError(
            f"{ind} is in current prices; use the constant-price series for growth."
        )
    d = df.sort_values(["country", "year"]).copy()
    d["value"] = d["value"].astype(float)
    # Lag by calendar year, not by row: a gap year must not become a 1-year change.
    lag = d[["country", "year", "value"]].assign(year=d["year"] + periods)
    d = d.merge(lag.rename(columns={"value": "value_lag"}), on=["country", "year"], how="left")
    if ind in RATIOS:
        d["change_pp"] = d["value"] - d["value_lag"]
    else:
        d["pct_change"] = (d["value"] / d["value_lag"] - 1) * 100
    return d


def change_between(
    df: pd.DataFrame, year_from: int, year_to: int, allow_nominal: bool = False
) -> pd.DataFrame:
    """Change from ``year_from`` to ``year_to`` per country; both years must have data."""
    ind = assert_single_indicator(df)
    if ind in NOMINAL and not allow_nominal:
        raise IncompatibleUnitsError(f"{ind} is in current prices; use constant prices.")
    w = wide(df)
    if year_from not in w.index or year_to not in w.index:
        return pd.DataFrame(columns=["country", "value_from", "value_to"])
    out = pd.DataFrame({"value_from": w.loc[year_from], "value_to": w.loc[year_to]}).dropna()
    if ind in RATIOS:
        out["change_pp"] = out["value_to"] - out["value_from"]
    else:
        out["pct_change"] = (out["value_to"] / out["value_from"] - 1) * 100
        years = year_to - year_from
        out["cagr_pct"] = ((out["value_to"] / out["value_from"]) ** (1 / years) - 1) * 100
    flags = df[df["year"].isin([year_from, year_to])].groupby("country")["value_flag"].agg(
        lambda s: ", ".join(sorted(set(s) - {"reported"})) or "reported"
    )
    out["flags"] = flags
    out.index.name = "country"
    sort_col = "change_pp" if ind in RATIOS else "pct_change"
    return out.reset_index().sort_values(sort_col, ascending=False, ignore_index=True)


def index_to_base(df: pd.DataFrame, base_year: int) -> pd.DataFrame:
    """Rebase each country's series to 100 in ``base_year`` (constant prices only)."""
    ind = assert_single_indicator(df)
    if ind in NOMINAL:
        raise IncompatibleUnitsError("Index only constant-price series.")
    w = wide(df)
    if base_year not in w.index:
        raise ValueError(f"No data for base year {base_year}")
    base = w.loc[base_year]
    idx = w.div(base.where(base > 0)) * 100
    return idx.dropna(axis=1, how="all").reset_index().melt(
        id_vars="year", var_name="country", value_name="index"
    ).dropna()


def latest_values(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Values for one year, sorted, with the flag shown. No cross-year mixing."""
    assert_single_indicator(df)
    d = df[(df["year"] == year) & df["value"].notna()].copy()
    d["value"] = d["value"].astype(float)
    return d.sort_values("value", ascending=False, ignore_index=True)[
        ["country", "iso3", "subregion", "year", "value", "value_flag", "unit"]
    ]


def balanced_total(df: pd.DataFrame, year_from: int, year_to: int) -> dict:
    """Sum across countries with complete data for every year in the range.

    Returns the yearly totals plus the countries included and excluded, so the
    reader knows which entities the total covers. Not defined for ratios.
    """
    ind = assert_single_indicator(df)
    if ind in RATIOS:
        raise IncompatibleUnitsError("Ratios cannot be summed across countries.")
    w = wide(df).loc[year_from:year_to]
    complete = w.columns[w.notna().all()]
    return {
        "indicator": ind,
        "unit": MILEX_INDICATORS[ind]["unit"],
        "totals": w[complete].sum(axis=1),
        "included": sorted(complete.tolist()),
        "excluded": sorted(set(w.columns) - set(complete)),
    }


def count_at_or_above(df: pd.DataFrame, threshold: float = 2.0) -> pd.DataFrame:
    """Number of countries with share of GDP >= threshold, per year, with denominator.

    Note: SIPRI's definition of military expenditure differs from NATO's, so this
    is NOT a measure of compliance with the NATO 2% guideline.
    """
    ind = assert_single_indicator(df)
    if ind != "share_gdp_pct":
        raise IncompatibleUnitsError("Threshold counts apply to share_gdp_pct only.")
    d = df.dropna(subset=["value"])
    g = d.groupby("year")["value"]
    return pd.DataFrame(
        {"countries_at_or_above": g.apply(lambda s: int((s.astype(float) >= threshold).sum())),
         "countries_with_data": g.size()}  # fmt: skip
    ).reset_index()


def estimate_share(df: pd.DataFrame) -> float:
    """Share of non-missing values that are SIPRI estimates or highly uncertain."""
    d = df[df["value"].notna()]
    return float(d["value_flag"].isin(["estimate", "highly_uncertain"]).mean()) if len(d) else np.nan
