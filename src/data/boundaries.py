"""Country boundaries and the point-in-country coordinate check.

Uses Natural Earth 1:50m admin-0 polygons (public domain). The check answers one
question: *does the event's coordinate fall inside the country the source says
it happened in?* It is a plausibility flag, not a correction. Natural Earth
draws Crimea as part of Russia (de facto control), whereas UCDP records events
there under Ukraine, so mismatches near contested areas are expected and are
reported rather than "fixed".
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.config import BOUNDARIES_ZIP

# Natural Earth ADM0_A3 codes that differ from the ISO3 codes we use.
_NE_TO_ISO3 = {"KOS": "XKX", "ALD": "FIN", "JEY": "GBR", "GGY": "GBR", "IMN": "GBR"}

EQUAL_AREA_CRS = "EPSG:3035"  # ETRS89 / LAEA Europe, metres
TOLERANCE_M = 10_000


@lru_cache(maxsize=2)
def load_boundaries(path: Path = BOUNDARIES_ZIP) -> gpd.GeoDataFrame | None:
    """Return country polygons with an ``iso3`` column, or None if the file is absent."""
    if not Path(path).exists():
        return None
    g = gpd.read_file(f"zip://{path}")[["ADM0_A3", "NAME", "geometry"]]
    g["iso3"] = g["ADM0_A3"].replace(_NE_TO_ISO3)
    g = g.dissolve(by="iso3", as_index=False)[["iso3", "geometry"]]
    return g.to_crs("EPSG:4326")


def check_points_in_country(
    df: pd.DataFrame, boundaries: gpd.GeoDataFrame | None = None
) -> pd.Series:
    """Classify each row as inside | within_10km | elsewhere | not_checked.

    Expects ``latitude``, ``longitude`` (NaN when invalid) and ``iso3`` columns.
    """
    if boundaries is None:
        boundaries = load_boundaries()
    result = pd.Series("not_checked", index=df.index, dtype="string")
    if boundaries is None:
        return result
    ok = df["latitude"].notna() & df["longitude"].notna() & df["iso3"].notna()
    if not ok.any():
        return result
    sub = df.loc[ok, ["latitude", "longitude", "iso3"]]
    pts = gpd.GeoDataFrame(
        sub[["iso3"]].rename(columns={"iso3": "stated"}),
        geometry=gpd.points_from_xy(sub["longitude"].astype(float), sub["latitude"].astype(float)),
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(pts, boundaries, how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    inside = joined["iso3"] == joined["stated"]
    result.loc[inside[inside].index] = "inside"

    # Points not inside the stated country: are they within 10 km of it?
    # (Coastal events, simplified 1:50m coastlines, border towns.)
    rest = joined.index[~inside]
    if len(rest):
        polys = boundaries.set_index("iso3").to_crs(EQUAL_AREA_CRS).geometry
        pts_m = pts.loc[rest].to_crs(EQUAL_AREA_CRS)
        near = pd.Series(False, index=rest)
        for iso, grp in pts_m.groupby("stated"):
            if iso in polys.index:
                near.loc[grp.index] = grp.geometry.distance(polys[iso]) <= TOLERANCE_M
        result.loc[near[near].index] = "within_10km"
        result.loc[near[~near].index] = "elsewhere"
    return result
