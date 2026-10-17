import json

import pandas as pd
import pytest

from src.data.validation import (
    QualityReport,
    SchemaError,
    check_date_range,
    classify_coordinates,
    drop_duplicate_ids,
    parse_dates,
    require_columns,
    to_nullable_number,
)


def test_parse_dates_uses_explicit_formats_only():
    r = QualityReport("t", "f")
    s = pd.Series(["2024-01-05", "06 February 2024", "07/03/2024", "2024-13-40", None])
    out = parse_dates(s, r, ("%Y-%m-%d", "%d %B %Y", "%d/%m/%Y"))
    assert out[0] == pd.Timestamp("2024-01-05")
    assert out[1] == pd.Timestamp("2024-02-06")
    # Day-first: 07/03 is 7 March, never 3 July.
    assert out[2] == pd.Timestamp("2024-03-07")
    assert pd.isna(out[3]) and pd.isna(out[4])
    checks = {c.name: c for c in r.checks}
    assert checks["date_parse"].affected_rows == 2
    assert checks["date_format_consistency"].affected_rows == 2


def test_parse_dates_strips_time_component():
    out = parse_dates(pd.Series(["2022-03-01 00:00:00.000"]), QualityReport("t", "f"))
    assert out[0] == pd.Timestamp("2022-03-01")


def test_date_range_flags_future_and_too_early():
    r = QualityReport("t", "f")
    d = pd.Series(pd.to_datetime(["1980-01-01", "2020-01-01", "2999-01-01"]))
    bad = check_date_range(d, r, "1989-01-01")
    assert bad.tolist() == [True, False, True]


def test_classify_coordinates():
    lat = pd.Series([50.0, None, 95.0, 0.0, "abc"])
    lon = pd.Series([30.0, 30.0, 30.0, 0.0, 10.0])
    assert classify_coordinates(lat, lon).tolist() == [
        "valid", "missing", "out_of_range", "null_island", "missing",
    ]  # fmt: skip


def test_duplicate_ids_keep_first():
    r = QualityReport("t", "f")
    df = pd.DataFrame({"event_id": ["a", "b", "a"], "v": [1, 2, 3]})
    out = drop_duplicate_ids(df, "event_id", r)
    assert out["v"].tolist() == [1, 2]
    assert r.checks[0].affected_rows == 1


def test_blank_is_missing_not_zero():
    s = to_nullable_number(pd.Series(["3", "", "0", "n/a"]))
    assert s[0] == 3 and s[2] == 0
    assert pd.isna(s[1]) and pd.isna(s[3])


def test_require_columns_raises():
    r = QualityReport("t", "f")
    with pytest.raises(SchemaError):
        require_columns(pd.DataFrame({"a": [1]}), ["a", "b"], r)
    assert r.checks[0].status == "fail"


def test_report_is_machine_readable(tmp_path):
    r = QualityReport("demo", "in.csv", rows_in=10, rows_out=9)
    r.add("x", "warn", 1, 10, "detail")
    path = r.write(tmp_path)
    d = json.loads(path.read_text())
    assert d["summary"]["warn"] == 1
    assert d["checks"][0]["share"] == 0.1
