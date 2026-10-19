"""Hot-spot analysis of recorded conflict events (Getis-Ord Gi*).

Method, in order:

1. **Equal-area grid.** Square cells of ``cell_km`` in ETRS89-LAEA (EPSG:3035),
   so every cell has the same area.
2. **Study area.** A cell is included if it contains at least one event, or if
   its centre lies on the land of the selected countries *and* within
   ``buffer_km`` (default 100 km) of a recorded event. The area therefore follows
   the theatre of activity plus its quiet margins, which is what a hot spot is
   judged against, without the empty space a convex hull would add between
   distant events. **Cells with zero events are kept**: dropping them would make
   every busy cell look ordinary and is a common error in hot-spot work.
3. **Gi\\*.** Queen contiguity (the 8 surrounding cells) plus the cell itself,
   binary weights, analytic z-scores (Getis & Ord 1992; Ord & Getis 1995).
4. **Multiple testing.** Thousands of cells are tested at once, so p-values are
   adjusted with the Benjamini-Hochberg false discovery rate.

Results describe where *recorded* events cluster more than chance would
suggest, given this grid. They inherit every reporting bias of the source and
depend on the cell size (the modifiable areal unit problem). Both are shown in
the dashboard rather than hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy import stats

from src.data.boundaries import load_boundaries

CRS = "EPSG:3035"
HOT_COLD_LEVELS = (0.01, 0.05, 0.10)


@dataclass
class Grid:
    cells: gpd.GeoDataFrame  # row, col, geometry (EPSG:3035), in_area
    x0: float
    y0: float
    size_m: float

    @property
    def cell_km2(self) -> float:
        return (self.size_m / 1000) ** 2


# ---------------------------------------------------------------- geometry


def _events_xy(events: pd.DataFrame) -> np.ndarray:
    pts = gpd.GeoSeries(
        gpd.points_from_xy(events["longitude"].astype(float), events["latitude"].astype(float)),
        crs="EPSG:4326",
    ).to_crs(CRS)
    return np.column_stack([pts.x.to_numpy(), pts.y.to_numpy()])


def make_grid(events: pd.DataFrame, cell_km: float = 25, buffer_km: float = 100,
              boundaries=None) -> Grid:  # fmt: skip
    """Equal-area grid over the study area defined in the module docstring."""
    from scipy.spatial import cKDTree

    boundaries = boundaries if boundaries is not None else load_boundaries()
    if boundaries is None:
        raise RuntimeError("Natural Earth boundaries are required for the hot-spot study area.")
    size, buf = cell_km * 1000, buffer_km * 1000
    xy = _events_xy(events)
    x0 = np.floor((xy[:, 0].min() - buf) / size) * size
    y0 = np.floor((xy[:, 1].min() - buf) / size) * size
    ncol = int(np.ceil((xy[:, 0].max() + buf - x0) / size))
    nrow = int(np.ceil((xy[:, 1].max() + buf - y0) / size))
    cc, rr = np.meshgrid(np.arange(ncol), np.arange(nrow))
    cc, rr = cc.ravel(), rr.ravel()
    cx, cy = x0 + (cc + 0.5) * size, y0 + (rr + 0.5) * size

    land = boundaries[boundaries["iso3"].isin(events["iso3"].dropna().unique())].to_crs(CRS)
    land = shapely.union_all(land.geometry.values)
    shapely.prepare(land)
    on_land = shapely.contains_xy(land, cx, cy)
    dist, _ = cKDTree(xy).query(np.column_stack([cx, cy]), distance_upper_bound=buf + size)
    near = dist <= buf
    occupied = np.zeros(len(cc), dtype=bool)
    ec = np.floor((xy[:, 0] - x0) / size).astype(int)
    er = np.floor((xy[:, 1] - y0) / size).astype(int)
    occupied[er * ncol + ec] = True
    keep = occupied | (on_land & near)
    cc, rr = cc[keep], rr[keep]
    geoms = shapely.box(x0 + cc * size, y0 + rr * size, x0 + (cc + 1) * size, y0 + (rr + 1) * size)
    cells = gpd.GeoDataFrame({"row": rr, "col": cc}, geometry=geoms, crs=CRS)
    return Grid(cells=cells.reset_index(drop=True), x0=x0, y0=y0, size_m=size)


def cell_index(grid: Grid, events: pd.DataFrame) -> pd.Series:
    """Position of each event's cell in ``grid.cells`` (NaN when outside the study area)."""
    xy = _events_xy(events)
    col = np.floor((xy[:, 0] - grid.x0) / grid.size_m).astype(int)
    row = np.floor((xy[:, 1] - grid.y0) / grid.size_m).astype(int)
    lookup = pd.Series(grid.cells.index.to_numpy(), index=pd.MultiIndex.from_arrays(
        [grid.cells["row"].to_numpy(), grid.cells["col"].to_numpy()]))  # fmt: skip
    idx = lookup.reindex(pd.MultiIndex.from_arrays([row, col])).to_numpy()
    return pd.Series(idx, index=events.index, dtype="float")


def counts(grid: Grid, events: pd.DataFrame) -> np.ndarray:
    idx = cell_index(grid, events).dropna().astype(int).to_numpy()
    return np.bincount(idx, minlength=len(grid.cells)).astype(float)


def queen_neighbours(grid: Grid, include_self: bool = True) -> list[np.ndarray]:
    pos = {(r, c): i for i, (r, c) in enumerate(zip(grid.cells["row"], grid.cells["col"]))}
    out = []
    for r, c in zip(grid.cells["row"], grid.cells["col"]):
        nb = [pos[(r + dr, c + dc)] for dr in (-1, 0, 1) for dc in (-1, 0, 1)
              if (dr or dc or include_self) and (r + dr, c + dc) in pos]  # fmt: skip
        out.append(np.array(nb, dtype=int))
    return out


# --------------------------------------------------------------- statistics


def gi_star(x: np.ndarray, neighbours: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Getis-Ord Gi* z-scores and two-sided p-values (binary weights including self)."""
    x = np.asarray(x, float)
    n = len(x)
    xbar = x.mean()
    s = np.sqrt((x**2).mean() - xbar**2)
    z = np.full(n, np.nan)
    if n < 3 or s == 0:
        return z, np.full(n, np.nan)
    for i, nb in enumerate(neighbours):
        w = len(nb)  # sum of binary weights = sum of squared weights
        num = x[nb].sum() - xbar * w
        den = s * np.sqrt((n * w - w**2) / (n - 1))
        z[i] = num / den if den > 0 else np.nan
    p = 2 * stats.norm.sf(np.abs(z))
    return z, p


def fdr_bh(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values (NaN kept as NaN)."""
    p = np.asarray(p, float)
    out = np.full_like(p, np.nan)
    ok = ~np.isnan(p)
    pv = p[ok]
    m = len(pv)
    if not m:
        return out
    order = np.argsort(pv)
    ranked = pv[order] * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1].clip(max=1)
    res = np.empty(m)
    res[order] = adj
    out[ok] = res
    return out


def classify(z: np.ndarray, p_adj: np.ndarray) -> np.ndarray:
    """Hot/cold class at the strictest FDR level each cell passes."""
    labels = np.full(len(z), "Not significant", dtype=object)
    for q in sorted(HOT_COLD_LEVELS, reverse=True):  # loosest first, strictest overwrites
        sig = p_adj < q
        labels[sig & (z > 0)] = f"Hot spot (FDR {int(q * 100)}%)"
        labels[sig & (z < 0)] = f"Cold spot (FDR {int(q * 100)}%)"
    return labels


# --------------------------------------------------------------- pipelines


def located_precise(events: pd.DataFrame, precise_only: bool = True) -> pd.DataFrame:
    m = events["latitude"].notna() & events["longitude"].notna()
    if precise_only:
        m &= events["location_precise"].astype("boolean").fillna(False)
    return events.loc[m]


def hotspots(events: pd.DataFrame, cell_km: float = 25, precise_only: bool = True,
             boundaries=None) -> tuple[gpd.GeoDataFrame, dict]:  # fmt: skip
    """Gi* hot-spot map for the selected events. Returns cells (EPSG:4326) and a summary."""
    ev = located_precise(events, precise_only)
    if len(ev) < 30:
        raise ValueError("At least 30 located events are needed for a hot-spot analysis.")
    grid = make_grid(ev, cell_km, boundaries=boundaries)
    x = counts(grid, ev)
    z, p = gi_star(x, queen_neighbours(grid))
    p_adj = fdr_bh(p)
    cells = grid.cells.assign(events=x, z=z, p=p, p_fdr=p_adj, cls=classify(z, p_adj))
    inside = int(x.sum())
    hot = cells["cls"].str.startswith("Hot")
    summary = {
        "cell_km": cell_km,
        "cells": int(len(cells)),
        "cells_with_events": int((x > 0).sum()),
        "study_area_km2": float(len(cells) * grid.cell_km2),
        "events_used": inside,
        "events_excluded_imprecise": int(len(located_precise(events, False)) - len(ev)),
        "hot_cells": int(hot.sum()),
        "hot_area_km2": float(hot.sum() * grid.cell_km2),
        "share_events_in_hot_cells": float(x[hot.to_numpy()].sum() / inside) if inside else np.nan,
        "cold_cells": int(cells["cls"].str.startswith("Cold").sum()),
    }
    return cells.to_crs("EPSG:4326"), summary


TREND_ORDER = ["Persistent", "Intermittent", "New", "Diminishing", "Never hot"]


def hotspot_trend(events: pd.DataFrame, cell_km: float = 25, precise_only: bool = True,
                  q: float = 0.05, boundaries=None) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:  # fmt: skip
    """Classify cells by their hot-spot history, one Gi* map per calendar year.

    The grid is fixed across years (built from all selected events), so maps are
    comparable. Categories, judged against the final year:
    Persistent - hot in every year; New - hot only in the final year;
    Intermittent - hot in the final year and some earlier years;
    Diminishing - hot earlier but not in the final year; Never hot.
    """
    ev = located_precise(events, precise_only)
    years = sorted(ev["event_date"].dt.year.unique())
    if len(years) < 2:
        raise ValueError("Hot-spot trends need at least two calendar years.")
    grid = make_grid(ev, cell_km, boundaries=boundaries)
    nbrs = queen_neighbours(grid)
    hot = {}
    for y in years:
        z, p = gi_star(counts(grid, ev[ev["event_date"].dt.year == y]), nbrs)
        hot[y] = (fdr_bh(p) < q) & (z > 0)
    H = pd.DataFrame(hot)
    last, earlier = H[years[-1]], H[years[:-1]]
    cat = np.select(
        [H.all(axis=1), last & ~earlier.any(axis=1), last, earlier.any(axis=1)],
        ["Persistent", "New", "Intermittent", "Diminishing"],
        default="Never hot",
    )
    cells = grid.cells.assign(trend=cat, years_hot=H.sum(axis=1).to_numpy())
    per_year = pd.DataFrame({"year": years, "hot_cells": [int(H[y].sum()) for y in years],
                             "hot_area_km2": [float(H[y].sum() * grid.cell_km2) for y in years]})  # fmt: skip
    return cells.to_crs("EPSG:4326"), per_year


def monthly_active_area(events: pd.DataFrame, cell_km: float = 25, precise_only: bool = True,
                        boundaries=None) -> pd.DataFrame:  # fmt: skip
    """Area (km²) of grid cells with at least one recorded event, per month."""
    ev = located_precise(events, precise_only)
    grid = make_grid(ev, cell_km, boundaries=boundaries)
    idx = cell_index(grid, ev)
    d = ev.assign(cell=idx).dropna(subset=["cell"])
    d = d.assign(month=d["event_date"].dt.to_period("M").dt.start_time)
    g = d.groupby("month").agg(events=("event_id", "size"), active_cells=("cell", "nunique")).reset_index()
    full = pd.date_range(g["month"].min(), g["month"].max(), freq="MS")
    g = g.set_index("month").reindex(full, fill_value=0).rename_axis("month").reset_index()
    g["active_area_km2"] = g["active_cells"] * grid.cell_km2
    return g
