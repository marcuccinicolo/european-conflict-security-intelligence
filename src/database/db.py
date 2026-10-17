"""DuckDB analytical store.

The pipeline writes one database file containing four tables:

* ``conflict_events``  canonical events from every available source (``source`` column)
* ``milex``            long-format expenditure indicators (``source`` column)
* ``datasets``         registry: provenance, licence, coverage, transformations
* ``quality_checks``   every validation check from every source

The file is built under a temporary name and swapped in atomically, so a
running dashboard never reads a half-written database.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb
import pandas as pd

from src.config import DB_PATH

# Bump whenever the set of tables or their meaning changes: an app finding an older
# database (e.g. a persisted file on a hosting platform) rebuilds it automatically.
SCHEMA_VERSION = 2

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
    tmp = path.with_suffix(".building.duckdb")
    tmp.unlink(missing_ok=True)
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
    finally:
        con.close()
    os.replace(tmp, path)
    return path


def schema_version(path: Path = DB_PATH) -> int | None:
    """Schema version of an existing database file; None if absent, unreadable or pre-versioning."""
    if not Path(path).exists():
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
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Database not found at {path}. Run `python -m src.pipeline build` first."
        )
    return duckdb.connect(str(path), read_only=read_only)
