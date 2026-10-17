"""Geographic exposure of each European country to Russia and to the front line.

Two time-invariant distance measures, both from the capital city and both in
kilometres (planar distance in ETRS89-LAEA, EPSG:3035):

* ``dist_russia_km`` - to the nearest point of Russia's internationally recognised
  territory: Natural Earth's Russia polygon including Kaliningrad, with the Crimea
  part removed (Natural Earth draws Crimea as Russian).
* ``dist_front_km`` - to the nearest precisely located UCDP event of the
  Russia-Ukraine conflict, 2022-2025 (a front-line proxy).
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon

from src.config import RAW_DIR, ROOT
from src.data import countries
from src.data.boundaries import load_boundaries

PLACES_ZIP = RAW_DIR / "naturalearth_places" / "ne_50m_populated_places_simple.zip"
PLACES_URL = "https://naciscdn.org/naturalearth/50m/cultural/ne_50m_populated_places_simple.zip"
NATO_CSV = ROOT / "data" / "reference" / "nato_accession.csv"
EQUAL_AREA_CRS = "EPSG:3035"
# Bounding box used to identify the Crimea part of Natural Earth's Russia polygon.
CRIMEA_BOX = (32.0, 44.0, 37.0, 46.5)  # lon_min, lat_min, lon_max, lat_max


def load_capitals(path: Path = PLACES_ZIP) -> pd.DataFrame:
    g = gpd.read_file(f"zip://{path}")
    cap = g[g["featurecla"] == "Admin-0 capital"].copy()
    cap["iso3"] = cap["adm0_a3"].replace({"KOS": "XKX"})
    europe = [k for k in countries.EUROPE if k not in countries.HISTORICAL]
    cap = cap[cap["iso3"].isin(europe)]
    if cap["iso3"].duplicated().any():
        raise ValueError(f"More than one capital for {cap.loc[cap.iso3.duplicated(), 'iso3'].tolist()}")
    return cap[["iso3", "name", "latitude", "longitude"]].rename(columns={"name": "capital"}).reset_index(drop=True)


def russia_without_crimea(boundaries: gpd.GeoDataFrame | None = None):
    """Russia polygon (EPSG:4326) with the part whose centroid lies in Crimea removed."""
    boundaries = boundaries if boundaries is not None else load_boundaries()
    geom = boundaries.loc[boundaries["iso3"] == "RUS", "geometry"].iloc[0]
    parts = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    x0, y0, x1, y1 = CRIMEA_BOX
    keep = [p for p in parts if not (x0 < p.centroid.x < x1 and y0 < p.centroid.y < y1)]
    if len(keep) != len(parts) - 1:
        raise ValueError(f"Expected to remove exactly one Crimea part, removed {len(parts) - len(keep)}")
    return MultiPolygon(keep)


def _points(df: pd.DataFrame, lat: str = "latitude", lon: str = "longitude") -> gpd.GeoSeries:
    return gpd.GeoSeries(gpd.points_from_xy(df[lon].astype(float), df[lat].astype(float)),
                         crs="EPSG:4326", index=df.index).to_crs(EQUAL_AREA_CRS)  # fmt: skip


def distance_to_geometry_km(capitals: pd.DataFrame, geom) -> pd.Series:
    target = gpd.GeoSeries([geom], crs="EPSG:4326").to_crs(EQUAL_AREA_CRS).iloc[0]
    return _points(capitals).distance(target) / 1000


def distance_to_events_km(capitals: pd.DataFrame, events: pd.DataFrame) -> pd.Series:
    """Distance from each capital to the nearest event location."""
    ev = events.dropna(subset=["latitude", "longitude"])
    ev_pts = gpd.GeoDataFrame(geometry=_points(ev).values, crs=EQUAL_AREA_CRS)
    caps = gpd.GeoDataFrame(capitals[["iso3"]], geometry=_points(capitals).values, crs=EQUAL_AREA_CRS)
    joined = gpd.sjoin_nearest(caps, ev_pts, how="left", distance_col="d")
    return joined.groupby(level=0)["d"].min().reindex(capitals.index) / 1000


def front_events(ucdp: pd.DataFrame) -> pd.DataFrame:
    """Precisely located UCDP Russia-Ukraine events, 2022-2025."""
    m = (
        (ucdp["conflict_name"] == "Russia - Ukraine")
        & (ucdp["event_date"].dt.year.between(2022, 2025))
        & ucdp["location_precise"].astype("boolean").fillna(False)
    )
    return ucdp.loc[m]


def nato_accession() -> pd.DataFrame:
    return pd.read_csv(NATO_CSV)[["iso3", "accession_year"]]


def build_exposure(ucdp: pd.DataFrame | None, places: Path = PLACES_ZIP) -> pd.DataFrame:
    caps = load_capitals(places)
    caps["country"] = caps["iso3"].map(countries.display_name)
    caps["dist_russia_km"] = distance_to_geometry_km(caps, russia_without_crimea())
    if ucdp is not None and len(ucdp):
        caps["dist_front_km"] = distance_to_events_km(caps, front_events(ucdp))
    else:
        caps["dist_front_km"] = pd.NA
    caps = caps.merge(nato_accession(), on="iso3", how="left")
    caps["nato_accession_year"] = caps.pop("accession_year").astype("Int64")
    return caps.sort_values("dist_russia_km", ignore_index=True)
