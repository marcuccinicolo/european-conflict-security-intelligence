"""Source adapters: ACLED CSV, UCDP GED, SIPRI workbook."""

import pandas as pd
import pytest

from src.data.acled import load_acled_csv
from src.data.boundaries import load_boundaries
from src.data.sipri import _flag_from_font, load_sipri
from src.data.ucdp import load_ucdp

HAVE_BOUNDARIES = load_boundaries() is not None


# ----------------------------------------------------------------------- ACLED


def test_acled_cleaning(acled_csv):
    df, rep = load_acled_csv(acled_csv)
    checks = {c.name: c for c in rep.checks}
    assert checks["duplicate_event_ids"].affected_rows == 1
    assert checks["date_parse"].affected_rows == 1  # 2024-13-40
    assert checks["country_harmonisation"].affected_rows == 1  # Narnia
    assert set(df["event_id"]) == {"A1", "A2", "A3", "A5", "A6"}
    by = df.set_index("event_id")
    # Negative fatalities -> missing; blank -> missing; zero stays zero.
    assert pd.isna(by.loc["A5", "fatalities"])
    assert pd.isna(by.loc["A3", "fatalities"])
    assert by.loc["A2", "fatalities"] == 0
    # Invalid coordinates are nulled but the event still counts.
    assert by.loc["A6", "coord_status"] == "out_of_range" and pd.isna(by.loc["A6", "latitude"])
    assert by.loc["A5", "coord_status"] == "missing"
    assert (df["fatalities_kind"] == "reported").all()
    assert (df["data_status"] == "real").all()


def test_synthetic_file_must_be_labelled(acled_csv):
    with pytest.raises(ValueError, match="SYNTHETIC"):
        load_acled_csv(acled_csv, source="synthetic_events")


# ------------------------------------------------------------------------ UCDP


def test_ucdp_europe_only_and_mappings(ucdp_csv):
    df, rep = load_ucdp(ucdp_csv)
    assert len(df) == 3  # Syria excluded by region
    by = df.set_index("event_id")
    assert by.loc["ucdp-2", "country"] == "Russia"  # 'Russia (Soviet Union)'
    assert by.loc["ucdp-4", "iso3"] == "SRB"
    assert bool(by.loc["ucdp-2", "date_uncertain"]) is True  # date_prec 3
    assert bool(by.loc["ucdp-2", "location_precise"]) is False  # where_prec 4
    assert pd.isna(by.loc["ucdp-2", "n_sources"])  # -1 -> unknown
    assert by.loc["ucdp-1", "event_type"] == "State-based conflict"
    assert (df["fatalities_kind"] == "estimate").all()
    checks = {c.name: c for c in rep.checks}
    assert checks["fatality_bounds_ordered"].affected_rows == 1  # low 5 > best 3


@pytest.mark.skipif(not HAVE_BOUNDARIES, reason="Natural Earth boundaries not downloaded")
def test_ucdp_point_in_country(ucdp_csv):
    df, _ = load_ucdp(ucdp_csv)
    by = df.set_index("event_id")
    assert by.loc["ucdp-1", "coord_check"] == "inside"  # Kharkiv in Ukraine
    # A Kosovo location coded 'Serbia (Yugoslavia)' is outside present-day Serbia.
    assert by.loc["ucdp-4", "coord_check"] == "elsewhere"


# ----------------------------------------------------------------------- SIPRI


def test_sipri_parsing(sipri_xlsx):
    df, rep = load_sipri(sipri_xlsx)
    assert "Israel" not in set(df["country"])  # outside Europe
    c = df[df["indicator"] == "milex_constant_usd_m"].set_index(["country", "year"])
    assert c.loc[("Germany", 2024), "value"] == 60000
    assert c.loc[("Germany", 2024), "value_flag"] == "estimate"  # blue font
    assert c.loc[("France", 2024), "value_flag"] == "highly_uncertain"  # red font
    assert pd.isna(c.loc[("France", 2022), "value"])
    assert c.loc[("France", 2022), "value_flag"] == "unavailable"  # '...'
    assert c.loc[("USSR", 2023), "value_flag"] == "not_independent"  # 'xxx'
    assert c.loc[("USSR", 2023), "entity_type"] == "historical"
    assert c.loc[("European Union", 2022), "entity_type"] == "aggregate"
    assert c.loc[("Germany", 2022), "subregion"] == "Western Europe"
    assert c.loc[("Ukraine", 2022), "subregion"] == "Eastern Europe"
    assert set(c["price_basis"]) == {"constant 2024 prices and exchange rates"}


def test_sipri_share_converted_to_percent(sipri_xlsx):
    df, _ = load_sipri(sipri_xlsx)
    g = df[df["indicator"] == "share_gdp_pct"].set_index(["country", "year"])
    assert g.loc[("Germany", 2022), "value"] == pytest.approx(5.0)
    assert set(g["unit"]) == {"% of GDP"}


def test_sipri_missing_sheets_reported(sipri_xlsx):
    _, rep = load_sipri(sipri_xlsx)
    missing = [c.name for c in rep.checks if c.name.startswith("sheet_present") and c.status == "fail"]
    assert "sheet_present[per_capita_current_usd]" in missing


def test_indexed_font_colours():
    class Color:
        def __init__(self, indexed):
            self.type, self.indexed, self.rgb = "indexed", indexed, None

    class Cell:
        def __init__(self, idx):
            self.font = type("F", (), {"color": Color(idx)})()

    assert _flag_from_font(Cell(12)) == "estimate"
    assert _flag_from_font(Cell(10)) == "highly_uncertain"
    assert _flag_from_font(Cell(8)) == "reported"
