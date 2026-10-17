"""Database round-trip, SQL vs pandas consistency, synthetic data, ACLED fetch."""

import json

import pandas as pd
import pytest

from src.analysis import conflict as C
from src.config import SYNTHETIC_EVENTS_CSV, SYNTHETIC_MILEX_CSV
from src.data import fetch as F
from src.data.acled import load_acled_csv
from src.data.sipri import load_milex_csv
from src.database import queries as Q
from src.database.db import build_database, connect, resolve, schema_version

# scripts/ is not a package; import the generator by path.
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "gen", Path(__file__).resolve().parents[1] / "scripts" / "generate_synthetic_data.py"
)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


@pytest.fixture(scope="module")
def synthetic():
    ev, ev_rep = load_acled_csv(SYNTHETIC_EVENTS_CSV, source="synthetic_events")
    mx, mx_rep = load_milex_csv(SYNTHETIC_MILEX_CSV)
    return ev, ev_rep, mx, mx_rep


@pytest.fixture(scope="module")
def db(tmp_path_factory, synthetic):
    ev, ev_rep, mx, _ = synthetic
    path = tmp_path_factory.mktemp("db") / "test.duckdb"
    other = ev.head(50).assign(source="acled", data_status="real")
    reg = [{"source": "synthetic_events", "domain": "conflict", "name": "syn", "data_status": "synthetic",
            "coverage": ev_rep.coverage, "transformations": ["t"], "notes": []}]  # fmt: skip
    build_database([ev, other], [mx], reg, [], path=path)
    con = connect(path)
    yield con
    con.close()


def test_synthetic_defects_are_all_caught(synthetic):
    _, rep, _, _ = synthetic
    d = gen.INJECTED_DEFECTS
    c = {k.name: k.affected_rows for k in rep.checks}
    assert c["duplicate_event_ids"] == d["duplicate_ids"]
    assert c["date_parse"] == d["unparseable_dates"]
    assert c["date_format_consistency"] == d["long_format_dates"] + d["dayfirst_slash_dates"]
    assert c["fatalities_non_negative"] == d["negative_fatalities"]
    assert c["country_harmonisation"] == d["unknown_country"]
    assert c["coordinates_out_of_range"] == d["out_of_range_coordinates"]
    assert c["coordinates_null_island"] == d["null_island"]
    assert c["coordinates_missing"] >= d["missing_coordinates"]
    assert c["missing_fatalities"] >= d["blank_fatalities"] + d["negative_fatalities"]


def test_synthetic_rows_are_labelled(synthetic):
    ev, _, mx, _ = synthetic
    assert (ev["data_status"] == "synthetic").all() and (ev["source"] == "synthetic_events").all()
    assert (mx["data_status"] == "synthetic").all()
    raw = pd.read_csv(SYNTHETIC_EVENTS_CSV)
    assert raw["notes"].str.startswith("SYNTHETIC").all()


def test_generator_is_deterministic():
    import numpy as np

    a = gen.make_events(np.random.default_rng(gen.SEED))
    b = gen.make_events(np.random.default_rng(gen.SEED))
    pd.testing.assert_frame_equal(a, b)


def test_sql_monthly_counts_match_pandas(db, synthetic):
    ev = synthetic[0]
    sql = Q.monthly_counts(db, "synthetic_events")
    pdf = C.temporal_counts(ev, "Month")
    pdf = pdf[pdf["events"] > 0].reset_index(drop=True)  # SQL returns only non-empty months
    assert sql["events"].tolist() == pdf["events"].tolist()
    assert sql["events_with_fatality_data"].tolist() == pdf["events_with_fatality_data"].tolist()
    assert sql["fatalities"].astype(float).tolist() == pytest.approx(pdf["fatalities"].astype(float).tolist())


def test_queries_isolate_sources(db):
    syn = Q.events(db, "synthetic_events")
    acl = Q.events(db, "acled")
    assert set(syn["source"]) == {"synthetic_events"} and len(acl) == 50


def test_query_filters_are_parameterised(db):
    sneaky = ["Ukraine') OR 1=1 --"]
    assert Q.events(db, "synthetic_events", countries=sneaky).empty
    ua = Q.events(db, "synthetic_events", start=pd.Timestamp("2023-01-01").date(),
                  end=pd.Timestamp("2023-12-31").date(), countries=["Ukraine"])  # fmt: skip
    assert set(ua["country"]) == {"Ukraine"}
    assert ua["event_date"].between("2023-01-01", "2023-12-31").all()


def test_registry_round_trip(db):
    reg = Q.datasets(db)
    assert reg.loc[0, "coverage"]["events"] > 0
    assert reg.loc[0, "transformations"] == ["t"]


def test_milex_query_single_indicator(db):
    d = Q.milex(db, "synthetic_milex", "share_gdp_pct", iso3=["DEU"])
    assert set(d["indicator"]) == {"share_gdp_pct"} and set(d["iso3"]) == {"DEU"}


# --------------------------------------------------------------------- fetch


def test_acled_requires_credentials(monkeypatch):
    monkeypatch.delenv("ACLED_USERNAME", raising=False)
    monkeypatch.delenv("ACLED_PASSWORD", raising=False)
    monkeypatch.setattr(F, "acled_credentials", lambda: None)
    with pytest.raises(RuntimeError, match="credentials"):
        F.fetch_acled()


def test_acled_fetch_paginates_and_records_provenance(monkeypatch, tmp_path):
    monkeypatch.setattr(F, "acled_credentials", lambda: ("user@example.org", "pw"))
    monkeypatch.setitem(F.SOURCES, "acled", F.SOURCES["acled"].__class__(
        **{**F.SOURCES["acled"].__dict__, "raw_dir": tmp_path}))  # fmt: skip

    class Resp:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    class Session:
        headers = {}
        calls = []

        def post(self, url, data, timeout):
            assert data["grant_type"] == "password" and "password" in data
            return Resp({"access_token": "tok"})

        def get(self, url, params, headers, timeout):
            self.calls.append(params["page"])
            assert headers["Authorization"] == "Bearer tok"
            n = 2 if params["page"] == 1 else 1
            return Resp({"data": [{"event_id_cnty": f"X{params['page']}{i}"} for i in range(n)]})

    monkeypatch.setattr(F.time, "sleep", lambda s: None)
    s = Session()
    path = F.fetch_acled(start="2024-01-01", end="2024-02-01", page_size=2, session=s)
    assert s.calls == [1, 2]
    assert len(pd.read_csv(path)) == 3
    prov = json.loads(Path(f"{path}.provenance.json").read_text())
    assert prov["sha256"] and "ACLED API" in prov["method"]
    assert "pw" not in path.read_text() and "pw" not in json.dumps(prov)


def test_public_ucdp_subset_round_trip(monkeypatch, tmp_path, ucdp_csv):
    """The committed CC BY subset reloads with identical rows, checks and lineage."""
    import src.pipeline as P
    from src.data.ucdp import load_ucdp

    monkeypatch.setattr(P, "UCDP_PUBLIC_PARQUET", tmp_path / "u.parquet")
    monkeypatch.setattr(P, "UCDP_PUBLIC_META", tmp_path / "u.meta.json")
    df, rep = load_ucdp(ucdp_csv)
    P.export_public_ucdp(df, rep, ucdp_csv)
    df2, rep2, prov = P.load_public_ucdp()
    pd.testing.assert_frame_equal(df, df2)
    assert [c.name for c in rep2.checks] == [c.name for c in rep.checks]
    assert prov[0]["sha256"] == F.sha256(ucdp_csv)
    assert "committed subset" in prov[0]["method"]


def test_database_records_schema_version(db, tmp_path):
    from src.database.db import SCHEMA_VERSION, schema_version

    assert db.execute("SELECT schema_version FROM meta").fetchone()[0] == SCHEMA_VERSION
    assert schema_version(tmp_path / "missing.duckdb") is None
    import duckdb

    old = tmp_path / "old.duckdb"
    duckdb.connect(str(old)).close()  # a pre-versioning database has no meta table
    assert schema_version(old) is None


def test_concurrent_builds_do_not_collide(tmp_path, synthetic):
    """Two sessions rebuilding at once must both succeed (regression: TransactionException)."""
    import threading

    ev, ev_rep, mx, _ = synthetic
    path = tmp_path / "shared.duckdb"
    errors = []

    def build():
        try:
            build_database([ev], [mx], [], [], path=path)
        except Exception as exc:  # pragma: no cover - the failure being tested
            errors.append(exc)

    threads = [threading.Thread(target=build) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert connect(path).execute("SELECT count(*) FROM conflict_events").fetchone()[0] == len(ev)
    assert resolve(path).exists()


def test_rebuild_is_visible_to_a_process_holding_the_old_database(tmp_path, synthetic):
    """Regression: DuckDB caches open databases per path, so swapping a file under the
    same name left a running app reading the old database forever."""
    import duckdb

    ev, _, mx, _ = synthetic
    path = tmp_path / "app.duckdb"
    legacy = duckdb.connect(str(path))  # a pre-versioning database at the fixed name
    legacy.execute("CREATE TABLE old_only (x INT)")
    legacy.close()
    held = duckdb.connect(str(path), read_only=True)  # the app's cached connection
    try:
        build_database([ev], [mx], [], [], path=path)
        assert schema_version(path) == 2
        assert connect(path).execute("SELECT count(*) FROM conflict_events").fetchone()[0] == len(ev)
    finally:
        held.close()
