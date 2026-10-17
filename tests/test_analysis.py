"""Aggregation logic: conflict, spatial and defence analysis."""

import numpy as np
import pandas as pd
import pytest

from src.analysis import conflict as C
from src.analysis import defence as D
from src.analysis import spatial as S
from tests.conftest import make_events

# --------------------------------------------------------------------- conflict


@pytest.fixture
def ev():
    return make_events([
        {"event_date": "2024-01-03", "fatalities": 2, "country": "Ukraine"},
        {"event_date": "2024-01-20", "fatalities": None, "country": "Ukraine"},
        {"event_date": "2024-03-05", "fatalities": 1, "country": "Russia", "iso3": "RUS"},
        {"event_date": "2024-04-10", "fatalities": None, "country": "Russia", "iso3": "RUS"},
    ])  # fmt: skip


def test_temporal_counts_fills_gaps_without_inventing_fatalities(ev):
    tc = C.temporal_counts(ev, "Month").set_index("period")
    assert tc["events"].tolist() == [2, 0, 1, 1]
    assert tc.loc["2024-01-01", "fatalities"] == 2  # missing excluded, not zero-filled
    assert tc.loc["2024-01-01", "events_with_fatality_data"] == 1
    assert tc.loc["2024-02-01", "fatalities"] == 0  # no events -> 0
    assert pd.isna(tc.loc["2024-04-01", "fatalities"])  # events, but no data -> missing


def test_temporal_counts_respects_requested_range(ev):
    tc = C.temporal_counts(ev, "Quarter", start="2023-10-01", end="2024-12-31")
    assert len(tc) == 5 and tc["events"].sum() == len(ev)


def test_no_double_counting_by_category(ev):
    tc = C.temporal_counts(ev, "Year", by="country")
    assert tc["events"].sum() == len(ev)


def test_mixing_sources_is_refused(ev):
    mixed = pd.concat([ev, ev.assign(source="acled", event_id=ev["event_id"] + "x")])
    with pytest.raises(ValueError, match="mixes sources"):
        C.temporal_counts(mixed)


def test_country_summary_coverage(ev):
    cs = C.country_summary(ev).set_index("country")
    assert cs.loc["Ukraine", "events"] == 2
    assert cs.loc["Ukraine", "fatality_data_coverage"] == 0.5
    assert cs["share_of_events"].sum() == pytest.approx(1.0)


def test_period_comparison_guards():
    df = make_events([{"event_date": f"2024-01-{d:02d}", "fatalities": 1} for d in range(1, 13)]
                     + [{"event_date": "2024-02-01", "fatalities": 1}])  # fmt: skip
    pc = C.period_comparison(df, ("2024-01-01", "2024-01-31"), ("2024-02-01", "2024-03-02"))
    row = pc.iloc[0]
    assert row["events_a"] == 12 and row["events_b"] == 1
    assert row["pct_change"] == pytest.approx((1 - 12) / 12 * 100)
    small = C.period_comparison(df, ("2024-01-01", "2024-01-31"), ("2024-02-01", "2024-03-02"), min_base=50)
    assert np.isnan(small.iloc[0]["pct_change"])
    with pytest.raises(ValueError, match="equal length"):
        C.period_comparison(df, ("2024-01-01", "2024-01-31"), ("2024-02-01", "2024-02-10"))


def test_headline_metrics(ev):
    m = C.headline_metrics(ev)
    assert m["events"] == 4 and m["fatalities"] == 3
    assert m["fatality_data_coverage"] == 0.5


def test_completeness_over_time(ev):
    cot = C.completeness_over_time(ev)
    assert cot.iloc[0]["share_with_fatality_data"] == 0.5


# ---------------------------------------------------------------------- spatial


def test_grid_counts_and_concentration():
    df = make_events([
        {"event_date": "2024-01-01", "latitude": 50.1, "longitude": 30.1},
        {"event_date": "2024-01-01", "latitude": 50.4, "longitude": 30.4},
        {"event_date": "2024-01-01", "latitude": 51.2, "longitude": 30.1},
        {"event_date": "2024-01-01", "latitude": None, "longitude": None, "coord_status": "missing"},
    ])  # fmt: skip
    g = S.grid_counts(df, 0.5)
    assert g["events"].sum() == 3  # missing coordinates excluded
    assert g.iloc[0]["events"] == 2 and g.iloc[0]["cell_lat"] == 50.0
    conc = S.concentration(df, 0.5, top_n=1)
    assert conc["share_in_top_cells"] == pytest.approx(2 / 3)


def test_standard_distance_zero_for_identical_points():
    df = make_events([{"event_date": "2024-01-01"}, {"event_date": "2024-06-01"}])
    mc = S.mean_centre_by_period(df, "Y")
    assert mc.iloc[0]["standard_distance_km"] == pytest.approx(0, abs=1e-6)
    assert mc.iloc[0]["lat"] == pytest.approx(50.0, abs=1e-6)


def test_standard_distance_in_km():
    # Two points ~111 km apart (1 degree of latitude): standard distance ~55.6 km.
    df = make_events([
        {"event_date": "2024-01-01", "latitude": 50.0, "longitude": 30.0},
        {"event_date": "2024-01-02", "latitude": 51.0, "longitude": 30.0},
    ])  # fmt: skip
    sd = S.mean_centre_by_period(df, "Y").iloc[0]["standard_distance_km"]
    assert 54 < sd < 57


# ---------------------------------------------------------------------- defence


def milex_frame(indicator="milex_constant_usd_m", values=None, unit="US$ million",
                basis="constant 2024 prices and exchange rates"):  # fmt: skip
    values = values or {"A": {2020: 100, 2021: 110, 2022: 121}, "B": {2020: 50, 2022: 60}}
    rows = [
        {"source": "s", "country": c, "iso3": c, "year": y, "indicator": indicator, "unit": unit,
         "price_basis": basis, "value": v, "value_flag": "reported"}
        for c, ys in values.items() for y, v in ys.items()
    ]  # fmt: skip
    return pd.DataFrame(rows)


def test_growth_uses_calendar_lag_not_row_lag():
    g = D.growth(milex_frame()).set_index(["country", "year"])
    assert g.loc[("A", 2021), "pct_change"] == pytest.approx(10.0)
    # B has no 2021 value: its 2022 change must be missing, not a 2020->2022 jump.
    assert pd.isna(g.loc[("B", 2022), "pct_change"])


def test_growth_refuses_nominal_series():
    df = milex_frame("milex_current_usd_m", basis="current prices and exchange rates")
    with pytest.raises(D.IncompatibleUnitsError):
        D.growth(df)
    assert "pct_change" in D.growth(df, allow_nominal=True)


def test_ratio_change_is_in_percentage_points():
    df = milex_frame("share_gdp_pct", {"A": {2020: 1.5, 2024: 2.1}}, unit="% of GDP", basis="ratio")
    ch = D.change_between(df, 2020, 2024)
    assert ch.iloc[0]["change_pp"] == pytest.approx(0.6)
    assert "pct_change" not in ch


def test_mixed_indicators_refused():
    df = pd.concat([milex_frame(), milex_frame("share_gdp_pct", unit="% of GDP", basis="ratio")])
    with pytest.raises(D.IncompatibleUnitsError):
        D.wide(df)


def test_balanced_total_excludes_incomplete_countries():
    bt = D.balanced_total(milex_frame(), 2020, 2022)
    assert bt["included"] == ["A"] and bt["excluded"] == ["B"]
    assert bt["totals"].tolist() == [100, 110, 121]


def test_ratios_cannot_be_summed():
    df = milex_frame("share_gdp_pct", unit="% of GDP", basis="ratio")
    with pytest.raises(D.IncompatibleUnitsError):
        D.balanced_total(df, 2020, 2022)


def test_index_to_base():
    idx = D.index_to_base(milex_frame(), 2020).set_index(["country", "year"])["index"]
    assert idx[("A", 2022)] == pytest.approx(121.0)
    assert idx[("B", 2020)] == pytest.approx(100.0)


def test_threshold_count_reports_denominator():
    df = milex_frame("share_gdp_pct", {"A": {2024: 2.0}, "B": {2024: 1.9}, "C": {2024: None}},
                     unit="% of GDP", basis="ratio")  # fmt: skip
    tc = D.count_at_or_above(df, 2.0).iloc[0]
    assert tc["countries_at_or_above"] == 1 and tc["countries_with_data"] == 2


def test_estimate_share():
    df = milex_frame()
    df.loc[0, "value_flag"] = "estimate"
    assert D.estimate_share(df) == pytest.approx(1 / 5)
