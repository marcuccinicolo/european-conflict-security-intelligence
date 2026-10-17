"""Proximity analysis: exposure geometry, panel rules, estimator, bootstrap."""

import numpy as np
import pandas as pd
import pytest
import statsmodels.formula.api as smf

from src.analysis import proximity as P
from src.data.boundaries import load_boundaries

HAVE_BOUNDARIES = load_boundaries() is not None


def synthetic_panel(effect2022=-0.5, n=30, seed=1):
    """Panel with a known post-2022 gradient and no pre-trend."""
    rng = np.random.default_rng(seed)
    rows = []
    dist = np.linspace(0.1, 2.8, n)
    for i, d in enumerate(dist):
        a = rng.normal(1.5, 0.3)
        for t in range(2005, 2026):
            y = a + 0.02 * (t - 2005) + effect2022 * d * (t >= 2022) + rng.normal(0, 0.05)
            rows.append({"iso3": f"C{i:02d}", "country": f"C{i:02d}", "year": t, "dist": d,
                         "dist_front": d, "share_gdp": y, "nato": 0.0})  # fmt: skip
    return pd.DataFrame(rows)


def test_fit_matches_statsmodels():
    df = synthetic_panel()
    d, terms = P.did_terms(df)
    f = P.fit(d, "share_gdp", terms)
    m = smf.ols("share_gdp ~ exp_x_post2014 + exp_x_post2022 + C(iso3) + C(year)", data=d).fit(
        cov_type="cluster", cov_kwds={"groups": d["iso3"]})
    for t in terms:
        assert f.coef[t] == pytest.approx(m.params[t], rel=1e-8)
        assert f.se[t] == pytest.approx(m.bse[t], rel=1e-6)


def test_recovers_known_effect_and_flat_pretrend():
    df = synthetic_panel(effect2022=-0.5)
    f = P.did(df, draws=499)
    assert f.coef["exp_x_post2022"] == pytest.approx(-0.5, abs=0.03)
    assert abs(f.coef["exp_x_post2014"]) < 0.03
    assert f.p_boot["exp_x_post2022"] < 0.01
    es, pre = P.event_study(df)
    assert es.loc[es["year"] == P.BASE_YEAR, "coef"].item() == 0
    assert pre["p"] > 0.01  # no pre-trend was generated


def test_bootstrap_does_not_overreject_under_null():
    rejections = 0
    for seed in range(20):
        f = P.did(synthetic_panel(effect2022=0.0, seed=seed), draws=199)
        rejections += f.p_boot["exp_x_post2022"] < 0.05
    assert rejections <= 4  # 5% nominal; generous bound for 20 replications


def test_panel_exclusions_and_nato_coding():
    years = range(2005, 2026)
    iso = ["RUS", "UKR", "BLR", "ISL", "ARM", "POL", "FIN", "ESP"]
    names = dict(zip(iso, iso))
    gdp = pd.DataFrame([{"iso3": i, "country": names[i], "year": y, "value": 1.0} for i in iso for y in years])
    real = gdp.assign(value=100.0)
    ex = pd.DataFrame({"iso3": iso, "dist_russia_km": 100.0, "dist_front_km": 100.0,
                       "nato_accession_year": [None, None, None, 1949, None, 1999, 2023, 1982]})  # fmt: skip
    ex["nato_accession_year"] = ex["nato_accession_year"].astype("Int64")
    main = P.build_panel(gdp, real, ex)
    assert set(main["iso3"]) == {"POL", "FIN", "ESP"}
    with_c = P.build_panel(gdp, real, ex, include_caucasus=True)
    assert "ARM" in set(with_c["iso3"])
    fin = main[main["iso3"] == "FIN"].set_index("year")["nato"]
    assert fin[2022] == 0 and fin[2023] == 1
    assert main["dist"].iloc[0] == pytest.approx(0.1)  # km -> 1,000 km


def test_missing_outcome_rows_are_dropped_not_imputed():
    df = synthetic_panel()
    df.loc[df.index[:5], "share_gdp"] = np.nan
    d, terms = P.did_terms(df)
    f = P.fit(d, "share_gdp", terms)
    assert f.n_obs == len(df) - 5


def test_placebo_and_leave_one_out_run():
    df = synthetic_panel()
    assert abs(P.placebo(df, draws=99).coef["exp_x_fake"]) < 0.05
    loo = P.leave_one_out(df)
    assert len(loo) == df["iso3"].nunique()


@pytest.mark.skipif(not HAVE_BOUNDARIES, reason="Natural Earth boundaries not downloaded")
def test_crimea_removed_from_russia():
    from shapely.geometry import Point

    from src.data.exposure import russia_without_crimea

    geom = russia_without_crimea()
    assert not geom.contains(Point(34.1, 44.95))  # Simferopol
    assert geom.contains(Point(37.6, 55.75))  # Moscow
    assert geom.contains(Point(20.5, 54.7))  # Kaliningrad


def test_distance_units():
    from shapely.geometry import box

    from src.data.exposure import distance_to_geometry_km

    caps = pd.DataFrame({"latitude": [50.0], "longitude": [20.0]})
    # A box starting 1 degree of longitude east: ~71.5 km at 50N.
    d = distance_to_geometry_km(caps, box(21.0, 49.0, 22.0, 51.0)).iloc[0]
    assert 65 < d < 78
