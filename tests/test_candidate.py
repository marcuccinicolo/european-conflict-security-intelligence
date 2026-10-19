"""UCDP Candidate (provisional) releases: naming, discovery, de-duplication, year rule."""

from pathlib import Path

import pandas as pd

from src.data import fetch as F
from src.data.ucdp import load_candidate

COLS = ["id", "relid", "year", "type_of_violence", "conflict_name", "where_prec", "adm_1", "latitude",
        "longitude", "country", "region", "date_prec", "date_start", "date_end", "best", "low", "high",
        "number_of_sources", "code_status"]  # fmt: skip


def release(path: Path, rows: list[list]) -> Path:
    pd.DataFrame(rows, columns=COLS).to_csv(path, index=False)
    return path


def row(i, start, end, best=1, status="Clear", region="Europe", country="Ukraine"):
    return [i, f"r{i}", int(start[:4]), 1, "Russia - Ukraine", 1, "Kharkiv", 49.99, 36.23, country, region,
            1, f"{start} 00:00:00.000", f"{end} 00:00:00.000", best, best, best, 1, status]  # fmt: skip


def test_release_order_and_names():
    names = ["GEDEvent_v26_0_8.csv", "GEDEvent_v26_01_26_06.csv", "GEDEvent_v26_0_7.csv"]
    ordered = [p.name for p in sorted(map(Path, names), key=F.release_sort_key)]
    assert ordered == ["GEDEvent_v26_01_26_06.csv", "GEDEvent_v26_0_7.csv", "GEDEvent_v26_0_8.csv"]
    quarterly, monthly = F.candidate_release_names(2026)
    assert quarterly[0] == "GEDEvent_v26_01_26_12.csv" and monthly[0] == "GEDEvent_v26_0_1.csv"


def test_discovery_takes_latest_quarter_then_consecutive_months():
    published = {"GEDEvent_v26_01_26_03.csv", "GEDEvent_v26_01_26_06.csv", "GEDEvent_v26_0_7.csv",
                 "GEDEvent_v26_0_8.csv", "GEDEvent_v26_0_10.csv"}  # 9 missing: 10 must not be used  # fmt: skip

    class Session:
        def head(self, url, **kw):
            return type("R", (), {"status_code": 200 if url.rsplit("/", 1)[1] in published else 404})()

    assert F.discover_candidate(2026, Session()) == [
        "GEDEvent_v26_01_26_06.csv", "GEDEvent_v26_0_7.csv", "GEDEvent_v26_0_8.csv"]  # fmt: skip


def test_overlapping_releases_keep_latest_revision(tmp_path):
    q = release(tmp_path / "GEDEvent_v26_01_26_06.csv", [
        row(1, "2026-06-29", "2026-07-02", best=3),        # spans June-July, revised later
        row(2, "2026-03-01", "2026-03-01", status="Check deaths"),
        row(3, "2025-12-30", "2026-01-02"),                # started in 2025: covered by GED
        row(4, "2026-02-01", "2026-02-01", region="Middle East", country="Syria"),
    ])  # fmt: skip
    m = release(tmp_path / "GEDEvent_v26_0_7.csv", [row(1, "2026-06-29", "2026-07-02", best=5)])
    df, rep = load_candidate([q, m], year=2026, check_boundaries=False)
    by = df.set_index("event_id")
    assert set(by.index) == {"ucdpc-1", "ucdpc-2"}
    assert by.loc["ucdpc-1", "fatalities"] == 5  # the July release's revision wins
    assert by.loc["ucdpc-2", "code_status"] == "Check deaths"
    assert (df["source"] == "ucdp_candidate").all()
    checks = {c.name: c.affected_rows for c in rep.checks}
    assert checks["duplicate_ids_across_releases"] == 1
    assert checks["outside_candidate_year"] == 1
    assert any("not comparable with UCDP GED" in t for t in rep.transformations)


def test_refresh_skips_when_release_files_unchanged(monkeypatch, tmp_path):
    """No new UCDP release -> no rebuild and no pull request (changed=false)."""
    import src.pipeline as P

    f = tmp_path / "GEDEvent_v26_0_8.csv"
    f.write_text("same bytes")
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(P, "_candidate_state", lambda: {"release_sha256": [F.sha256(f)]})
    monkeypatch.setattr(P.fetch_mod, "fetch_sipri", lambda: None)
    monkeypatch.setattr(P.fetch_mod, "fetch_candidate", lambda year: [f])
    monkeypatch.setattr(P, "cmd_build", lambda: (_ for _ in ()).throw(AssertionError("must not rebuild")))
    assert P.cmd_refresh() is None
    assert out.read_text().strip() == "changed=false"
