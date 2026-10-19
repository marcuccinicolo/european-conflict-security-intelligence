"""Hot-spot analysis: Gi* against PySAL, FDR against statsmodels, grid and study-area rules."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box
from statsmodels.stats.multitest import multipletests

from src.analysis import hotspots as H

# A fictitious square "country" (about 900 x 700 km) in central Europe.
LAND = gpd.GeoDataFrame({"iso3": ["XXX"]}, geometry=[box(20, 48, 32, 54)], crs="EPSG:4326")


def centroids(cells):
    c = cells.to_crs("EPSG:3035").geometry.centroid.to_crs("EPSG:4326")
    return c.x.to_numpy(), c.y.to_numpy()


def events(n_background=400, cluster=(28.0, 51.0), n_cluster=400, seed=0, years=(2023,)):
    rng = np.random.default_rng(seed)
    lon = np.r_[rng.uniform(21, 31, n_background), rng.normal(cluster[0], 0.08, n_cluster)]
    lat = np.r_[rng.uniform(48.5, 53.5, n_background), rng.normal(cluster[1], 0.06, n_cluster)]
    n = len(lon)
    dates = pd.to_datetime([f"{rng.choice(years)}-{rng.integers(1, 13):02d}-15" for _ in range(n)])
    return pd.DataFrame({"event_id": [f"e{i}" for i in range(n)], "latitude": lat, "longitude": lon,
                         "iso3": "XXX", "location_precise": True, "event_date": dates})  # fmt: skip


def test_gi_star_matches_pysal():
    esda = pytest.importorskip("esda")
    libpysal = pytest.importorskip("libpysal")
    grid = H.make_grid(events(), 25, boundaries=LAND)
    x = H.counts(grid, events())
    z, _ = H.gi_star(x, H.queen_neighbours(grid))
    nb = H.queen_neighbours(grid, include_self=False)
    w = libpysal.weights.W({i: list(n) for i, n in enumerate(nb)}, silence_warnings=True)
    ref = esda.G_Local(x, w, star=True, transform="B", permutations=0)
    assert np.nanmax(np.abs(ref.Zs - z)) < 1e-10


def test_fdr_matches_statsmodels():
    p = np.random.default_rng(1).uniform(0, 1, 500) ** 3
    assert np.allclose(H.fdr_bh(p), multipletests(p, method="fdr_bh")[1])


def test_grid_is_equal_area_and_keeps_empty_cells():
    ev = events()
    grid = H.make_grid(ev, 25, boundaries=LAND)
    areas = grid.cells.geometry.area / 1e6
    assert np.allclose(areas, 625)
    x = H.counts(grid, ev)
    assert x.sum() == len(ev)  # every event lands in a cell of the study area
    assert (x == 0).any()  # zero-event cells are part of the study area


def test_occupied_cells_kept_even_off_land():
    ev = events(n_background=50, n_cluster=0)
    sea = pd.DataFrame({"event_id": ["sea"], "latitude": [47.0], "longitude": [26.0], "iso3": ["XXX"],
                        "location_precise": [True], "event_date": [pd.Timestamp("2023-05-01")]})  # fmt: skip
    ev = pd.concat([ev, sea], ignore_index=True)
    grid = H.make_grid(ev, 25, boundaries=LAND)
    assert H.counts(grid, ev).sum() == len(ev)


def test_planted_cluster_is_detected_and_background_is_not():
    cells, s = H.hotspots(events(), 25, boundaries=LAND)
    hot = cells[cells["cls"].str.startswith("Hot")]
    assert len(hot) > 0
    lon, lat = centroids(hot)
    assert (abs(lon - 28.0) < 1).all() and (abs(lat - 51.0) < 0.7).all()
    assert s["share_events_in_hot_cells"] > 0.45
    # Pure background (complete spatial randomness): FDR keeps false hot spots rare.
    _, s0 = H.hotspots(events(n_cluster=0, n_background=800), 25, boundaries=LAND)
    assert s0["hot_cells"] <= 3


def test_imprecise_events_excluded_by_default():
    ev = events()
    ev.loc[:99, "location_precise"] = False
    _, s = H.hotspots(ev, 25, boundaries=LAND)
    assert s["events_excluded_imprecise"] == 100
    assert s["events_used"] == len(ev) - 100


def test_trend_categories():
    a = events(n_background=300, n_cluster=300, cluster=(22.5, 49.5), seed=2, years=(2022,))
    b = events(n_background=300, n_cluster=300, cluster=(29.0, 52.5), seed=3, years=(2023,))
    both = events(n_background=0, n_cluster=300, cluster=(25.5, 51.0), seed=4, years=(2022, 2023))
    ev = pd.concat([a, b, both], ignore_index=True)
    ev["event_id"] = [f"e{i}" for i in range(len(ev))]
    cells, per_year = H.hotspot_trend(ev, 25, boundaries=LAND)
    lon, lat = centroids(cells)
    near = lambda x, y: cells["trend"][(abs(lon - x) < 0.6) & (abs(lat - y) < 0.4)]  # noqa: E731
    assert (near(22.5, 49.5) == "Diminishing").any()
    assert (near(29.0, 52.5) == "New").any()
    assert (near(25.5, 51.0) == "Persistent").any()
    assert list(per_year["year"]) == [2022, 2023]


def test_monthly_active_area_fills_empty_months():
    ev = events(n_background=60, n_cluster=0)
    ev["event_date"] = pd.to_datetime(["2023-01-10"] * 30 + ["2023-04-10"] * 30)
    ma = H.monthly_active_area(ev, 25, boundaries=LAND)
    assert list(ma["month"].dt.month) == [1, 2, 3, 4]
    assert ma.loc[1, "active_area_km2"] == 0 and ma.loc[0, "active_area_km2"] > 0
