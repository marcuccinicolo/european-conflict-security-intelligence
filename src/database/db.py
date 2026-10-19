"""DuckDB analytical store.

The pipeline writes one database file containing four tables:

* ``conflict_events``  canonical events from every available source (``source`` column)
* ``milex``            long-format expenditure indicators (``source`` column)
* ``datasets``         registry: provenance, licence, coverage, transformations
* ``quality_checks``   every validation check from every source

Every build writes a NEW file (``security-<timestamp>-<id>.duckdb``) and then
atomically updates a small pointer file (``security.current``) naming it.
Readers resolve the pointer. Swapping a file under the *same* name does not work
with DuckDB: a process that already has that path open keeps receiving the old
database from DuckDB's per-path instance cache, so a running app would never see
the rebuild. A new name always opens fresh.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from src.config import DB_PATH

# Bump whenever the set of tables or their meaning changes: an app finding an older
# database (e.g. a persisted file on a hosting platform) rebuilds it automatically.
SCHEMA_VERSION = 3  # 3: conflict_events.code_status; ucdp_candidate source

DDL = """
CREATE TABLE datasets (
    source VARCHAR PRIMARY KEY,
    domain VARCHAR,               -- conflict | defence
    name VARCHAR,
    publisher VARCHAR,
    data_status VARCHAR,          -- real | synthetic
    licence VARCHAR,
    licence_url VARCHAR,
    url VARCHAR,
    citation VARCHAR,
    redistribution VARCHAR,
    exportable BOOLEAN,
    input_file VARCHAR,
    retrieved_at_utc VARCHAR,
    retrieval_method VARCHAR,
    sha256 VARCHAR,
    rows_in BIGINT,
    rows_out BIGINT,
    coverage JSON,
    transformations JSON,
    notes JSON,
    processed_at_utc VARCHAR
);
CREATE TABLE quality_checks (
    source VARCHAR,
    check_name VARCHAR,
    status VARCHAR,
    affected_rows BIGINT,
    total_rows BIGINT,
    share DOUBLE,
    detail VARCHAR,
    action VARCHAR
);
"""


def build_database(
    events: list[pd.DataFrame],
    milex: list[pd.DataFrame],
    registry: list[dict],
    checks: list[dict],
    path: Path = DB_PATH,
    extra_tables: dict[str, pd.DataFrame] | None = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    tmp = path.with_name(f"{path.stem}-{stamp}-{uuid.uuid4().hex[:8]}.duckdb")
    con = duckdb.connect(str(tmp))
    try:
        con.execute(DDL)
        con.execute(f"CREATE TABLE meta AS SELECT {SCHEMA_VERSION} AS schema_version")
        ev = pd.concat(events, ignore_index=True) if events else None
        mx = pd.concat(milex, ignore_index=True) if milex else None
        con.register("ev_df", ev)
        con.execute("CREATE TABLE conflict_events AS SELECT * FROM ev_df")
        con.execute("ALTER TABLE conflict_events ALTER event_date TYPE DATE")
        con.register("mx_df", mx)
        con.execute("CREATE TABLE milex AS SELECT * FROM mx_df")
        for r in registry:
            r = {k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()}
            cols = ", ".join(r)
            con.execute(
                f"INSERT INTO datasets ({cols}) VALUES ({', '.join('?' * len(r))})",
                list(r.values()),
            )
        if checks:
            con.register("qc_df", pd.DataFrame(checks))
            con.execute("INSERT INTO quality_checks BY NAME SELECT * FROM qc_df")
        for name, frame in (extra_tables or {}).items():
            con.register(f"{name}_df", frame)
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM {name}_df")
        con.execute("CREATE INDEX idx_ev_source ON conflict_events(source, event_date)")
        con.execute("CREATE INDEX idx_mx ON milex(source, indicator, iso3)")
    except BaseException:
        con.close()
        tmp.unlink(missing_ok=True)
        Path(f"{tmp}.wal").unlink(missing_ok=True)
        raise
    con.close()
    Path(f"{tmp}.wal").unlink(missing_ok=True)
    _point_to(path, tmp)
    _cleanup(path, keep={tmp.name})
    return tmp


def _pointer(path: Path) -> Path:
    return Path(path).with_suffix(".current")


def _point_to(path: Path, target: Path) -> None:
    ptr = _pointer(path)
    staging = ptr.with_name(f".{ptr.name}.{uuid.uuid4().hex[:8]}")
    staging.write_text(target.name)
    os.replace(staging, ptr)  # atomic: readers see either the old or the new name


def _cleanup(path: Path, keep: set[str], retain: int = 2, min_age_s: int = 300) -> None:
    """Delete superseded versioned files.

    Only files older than ``min_age_s`` are removed, so a build still being written
    by another session is never touched; open connections on POSIX keep working.
    """
    import time

    current = resolve(path).name
    versions = sorted(Path(path).parent.glob(f"{Path(path).stem}-*.duckdb"), key=lambda p: p.stat().st_mtime)
    now = time.time()
    for old in versions[:-retain]:
        if old.name in keep or old.name == current or now - old.stat().st_mtime < min_age_s:
            continue
        old.unlink(missing_ok=True)
        Path(f"{old}.wal").unlink(missing_ok=True)
    for legacy in (Path(path), Path(path).with_suffix(".building.duckdb")):  # pre-pointer layouts
        if legacy.exists():
            legacy.unlink(missing_ok=True)
            Path(f"{legacy}.wal").unlink(missing_ok=True)


def resolve(path: Path = DB_PATH) -> Path:
    """The database file currently in use (pointer target, else the legacy fixed name)."""
    ptr = _pointer(path)
    if ptr.exists():
        target = Path(path).with_name(ptr.read_text().strip())
        if target.exists():
            return target
    return Path(path)


def schema_version(path: Path = DB_PATH) -> int | None:
    """Schema version of an existing database file; None if absent, unreadable or pre-versioning."""
    path = resolve(path)
    if not path.exists():
        return None
    try:
        con = duckdb.connect(str(path), read_only=True)
        try:
            return int(con.execute("SELECT schema_version FROM meta").fetchone()[0])
        finally:
            con.close()
    except Exception:
        return None


def connect(path: Path = DB_PATH, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    path = resolve(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Database not found at {path}. Run `python -m src.pipeline build` first."
        )
    return duckdb.connect(str(path), read_only=read_only)
