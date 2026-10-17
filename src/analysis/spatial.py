"""Basic geospatial summaries (GeoPandas / Shapely).

Only events with valid coordinates enter spatial statistics, and the share of
events excluded is always returned. Distances are computed in ETRS89-LAEA
(EPSG:3035), an equal-area projection for Europe, not in degrees.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

EQUAL_AREA_CRS = "EPSG:3035"


def located(df: pd.DataFrame, precise_only: bool = False) -> pd.DataFrame:
    """Rows usable for mapping: valid coordinates (optionally precise locations only)."""
    m = df["latitude"].notna() & df["longitude"].notna()
    if precise_only:
        m &= df["location_precise"].astype("boolean").fillna(False)
    return df.loc[m]


def to_geodataframe(df: pd.DataFrame) -> gpd.GeoDataFrame:
    d = located(df)
    return gpd.GeoDataFrame(
        d,
        geometry=gpd.points_from_xy(d["longitude"].astype(float), d["latitude"].astype(float)),
        crs="EPSG:4326",
    )


def grid_counts(df: pd.DataFrame, cell_deg: float = 0.5) -> gpd.GeoDataFrame:
    """Count events per regular lat/lon grid cell (cell_deg x cell_deg degrees).

    Returns polygons so the result can be mapped or exported. Cells are labelled
    by their south-west corner.
    """
    d = located(df)
    if d.empty:
        return gpd.GeoDataFrame(columns=["cell_lat", "cell_lon", "events", "geometry"],
                                geometry="geometry", crs="EPSG:4326")  # fmt: skip
    lat0 = np.floor(d["latitude"].astype(float) / cell_deg) * cell_deg
    lon0 = np.floor(d["longitude"].astype(float) / cell_deg) * cell_deg
    g = (
        d.assign(cell_lat=lat0.round(6), cell_lon=lon0.round(6))
        .groupby(["cell_lat", "cell_lon"])
        .agg(events=("event_id", "size"), fatalities=("fatalities", lambda s: s.sum(min_count=1)))
        .reset_index()
    )
    geoms = [box(lo, la, lo + cell_deg, la + cell_deg) for la, lo in zip(g["cell_lat"], g["cell_lon"])]
    return gpd.GeoDataFrame(g, geometry=geoms, crs="EPSG:4326").sort_values(
        "events", ascending=False, ignore_index=True
    )


def concentration(df: pd.DataFrame, cell_deg: float = 0.5, top_n: int = 10) -> dict:
    """Share of located events falling in the ``top_n`` busiest grid cells."""
    g = grid_counts(df, cell_deg)
    total = int(g["events"].sum()) if len(g) else 0
    return {
        "cells_with_events": int(len(g)),
        "located_events": total,
        "top_n": top_n,
        "share_in_top_cells": float(g["events"].head(top_n).sum() / total) if total else None,
        "cell_deg": cell_deg,
    }


def mean_centre_by_period(df: pd.DataFrame, freq: str = "Y") -> pd.DataFrame:
    """Mean centre and standard distance (km) of located events per period.

    Standard distance = sqrt(mean squared distance to the mean centre); it
    summarises spatial dispersion. Computed in EPSG:3035.
    """
    gdf = to_geodataframe(df)
    if gdf.empty:
        return pd.DataFrame(columns=["period", "events", "lat", "lon", "standard_distance_km"])
    gdf = gdf.to_crs(EQUAL_AREA_CRS)
    gdf["x"], gdf["y"] = gdf.geometry.x, gdf.geometry.y
    gdf["period"] = gdf["event_date"].dt.to_period(freq).dt.start_time
    rows = []
    for period, grp in gdf.groupby("period"):
        mx, my = grp["x"].mean(), grp["y"].mean()
        sd = float(np.sqrt(((grp["x"] - mx) ** 2 + (grp["y"] - my) ** 2).mean())) / 1000
        pt = gpd.GeoSeries(gpd.points_from_xy([mx], [my]), crs=EQUAL_AREA_CRS).to_crs("EPSG:4326")
        rows.append({"period": period, "events": len(grp), "lat": pt.y[0], "lon": pt.x[0],
                     "standard_distance_km": sd})  # fmt: skip
    return pd.DataFrame(rows)


def admin1_summary(df: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    """Events by first-level administrative unit as recorded by the source."""
    d = df.dropna(subset=["admin1"])
    if d.empty:
        return pd.DataFrame(columns=["country", "admin1", "events", "fatalities"])
    return (
        d.groupby(["country", "admin1"])
        .agg(events=("event_id", "size"), fatalities=("fatalities", lambda s: s.sum(min_count=1)))
        .reset_index()
        .sort_values("events", ascending=False, ignore_index=True)
        .head(top)
    )


def location_quality(df: pd.DataFrame) -> dict:
    n = len(df)
    if not n:
        return {}
    return {
        "events": n,
        "share_valid_coordinates": float((df["coord_status"] == "valid").mean()),
        "share_precise_location": float(df["location_precise"].astype("boolean").mean()),
        "share_inside_stated_country": float(
            df["coord_check"].isin(["inside", "within_10km"]).sum()
            / max(1, (df["coord_check"] != "not_checked").sum())
        ),
    }
