"""Parameterised SQL used by the dashboard and the report.

All user-controlled values are passed as bound parameters - never formatted
into SQL strings. Every query is restricted to ONE source, so sources are never
mixed in a single result.
"""

from __future__ import annotations

import json
from datetime import date

import duckdb
import pandas as pd


def _in_clause(column: str, values: list | None, params: list) -> str:
    if not values:
        return ""
    params.extend(values)
    return f" AND {column} IN ({', '.join('?' * len(values))})"


def datasets(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    df = con.execute("SELECT * FROM datasets ORDER BY domain, data_status, source").df()
    for col in ("coverage", "transformations", "notes"):
        df[col] = df[col].map(lambda v: json.loads(v) if isinstance(v, str) else v)
    return df


def quality_checks(con, source: str) -> pd.DataFrame:
    return con.execute(
        "SELECT * FROM quality_checks WHERE source = ? ORDER BY "
        "CASE status WHEN 'fail' THEN 0 WHEN 'warn' THEN 1 WHEN 'not_run' THEN 2 "
        "WHEN 'info' THEN 3 ELSE 4 END, check_name",
        [source],
    ).df()


def event_filter_options(con, source: str) -> dict:
    row = con.execute(
        "SELECT min(event_date), max(event_date) FROM conflict_events WHERE source = ?", [source]
    ).fetchone()
    countries = con.execute(
        "SELECT country, count(*) n FROM conflict_events WHERE source = ? "
        "GROUP BY country ORDER BY n DESC",
        [source],
    ).df()
    types = con.execute(
        "SELECT DISTINCT event_type FROM conflict_events WHERE source = ? ORDER BY 1", [source]
    ).df()["event_type"]
    return {
        "date_min": row[0],
        "date_max": row[1],
        "countries": countries["country"].tolist(),
        "event_types": types.tolist(),
    }


def events(
    con,
    source: str,
    start: date | None = None,
    end: date | None = None,
    countries: list[str] | None = None,
    event_types: list[str] | None = None,
) -> pd.DataFrame:
    params: list = [source]
    sql = "SELECT * FROM conflict_events WHERE source = ?"
    if start:
        sql += " AND event_date >= ?"
        params.append(start)
    if end:
        sql += " AND event_date <= ?"
        params.append(end)
    sql += _in_clause("country", countries, params)
    sql += _in_clause("event_type", event_types, params)
    df = con.execute(sql + " ORDER BY event_date, event_id", params).df()
    df["event_date"] = pd.to_datetime(df["event_date"])
    return df


def monthly_counts(
    con, source: str, start=None, end=None, countries=None, event_types=None
) -> pd.DataFrame:
    """Monthly event counts and fatality sums computed in SQL.

    Fatality sums ignore NULLs, and ``events_with_fatality_data`` is returned so
    the caller can see the denominator. Used by the report and cross-checked
    against the pandas implementation in the tests.
    """
    params: list = [source]
    where = "source = ?"
    if start:
        where += " AND event_date >= ?"
        params.append(start)
    if end:
        where += " AND event_date <= ?"
        params.append(end)
    where += _in_clause("country", countries, params)
    where += _in_clause("event_type", event_types, params)
    sql = f"""
        SELECT date_trunc('month', event_date)::DATE AS period,
               count(*)                               AS events,
               sum(fatalities)                        AS fatalities,
               count(fatalities)                      AS events_with_fatality_data
        FROM conflict_events
        WHERE {where}
        GROUP BY 1 ORDER BY 1
    """
    df = con.execute(sql, params).df()
    df["period"] = pd.to_datetime(df["period"])
    return df


def milex_sources(con) -> list[str]:
    return [r[0] for r in con.execute("SELECT DISTINCT source FROM milex ORDER BY 1").fetchall()]


def milex(
    con,
    source: str,
    indicator: str,
    iso3: list[str] | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    entity_types: tuple[str, ...] = ("country",),
) -> pd.DataFrame:
    params: list = [source, indicator]
    sql = "SELECT * FROM milex WHERE source = ? AND indicator = ?"
    sql += _in_clause("entity_type", list(entity_types), params)
    sql += _in_clause("iso3", iso3, params)
    if year_min is not None:
        sql += " AND year >= ?"
        params.append(year_min)
    if year_max is not None:
        sql += " AND year <= ?"
        params.append(year_max)
    return con.execute(sql + " ORDER BY country, year", params).df()


def milex_indicators(con, source: str) -> list[str]:
    return [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT indicator FROM milex WHERE source = ? AND value IS NOT NULL ORDER BY 1",
            [source],
        ).fetchall()
    ]


def milex_countries(con, source: str) -> pd.DataFrame:
    return con.execute(
        "SELECT DISTINCT iso3, country, subregion FROM milex "
        "WHERE source = ? AND entity_type = 'country' ORDER BY country",
        [source],
    ).df()
