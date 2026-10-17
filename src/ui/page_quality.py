"""Data quality and provenance page."""

from __future__ import annotations

import json

import streamlit as st

from src.analysis import quality as QA
from src.config import QUALITY_DIR
from src.ui import common as U

ICON = {"pass": "✅ pass", "warn": "⚠️ warn", "fail": "❌ fail", "info": "ℹ️ info", "not_run": "⏸ not run"}


def render() -> None:
    v = U.db_version()
    U.page_header("Data integrity", "Data quality & provenance",
                  "Every check run on every dataset, what it found, and what was done about it.")  # fmt: skip
    reg = U.registry(v)
    labels = dict(zip(reg["source"], reg.apply(U.source_label, axis=1)))
    source = st.selectbox("Dataset", reg["source"].tolist(), format_func=labels.get, key="qa_source")
    row = reg.set_index("source").loc[source].rename(source)
    U.status_banner(row)

    a, b, c, d = st.columns(4)
    a.metric("Rows in", U.fmt_int(row["rows_in"]))
    b.metric("Rows out", U.fmt_int(row["rows_out"]))
    chk = U.checks(v, source)
    b_ = chk["status"].value_counts()
    c.metric("Warnings", int(b_.get("warn", 0)))
    d.metric("Failures", int(b_.get("fail", 0)),
             help="'fail' means the check found rows that had to be dropped or corrected.")  # fmt: skip

    st.markdown("##### Validation checks")
    show = chk.assign(status=chk["status"].map(ICON))
    st.dataframe(show[["status", "check_name", "affected_rows", "total_rows", "share", "detail", "action"]],
                 hide_index=True, width="stretch",
                 column_config={"share": st.column_config.NumberColumn(format="percent"),
                                "detail": st.column_config.TextColumn(width="large")})  # fmt: skip

    left, right = st.columns(2)
    with left:
        st.markdown("##### Provenance")
        st.markdown(
            f"""
| | |
|---|---|
| Publisher | {row['publisher']} |
| Source URL | {row['url'] or '—'} |
| Input file | `{row['input_file']}` |
| Retrieval | {row['retrieval_method']} · {row['retrieved_at_utc']} |
| SHA-256 (prefix) | `{row['sha256']}` |
| Licence | [{row['licence']}]({row['licence_url']}) |
| Redistribution | {row['redistribution']} |
| Processed | {row['processed_at_utc']} |
"""
        )
        st.markdown(U.md(f"**Citation:** {row['citation']}"))
    with right:
        st.markdown("##### Transformations applied")
        for t in row["transformations"] or []:
            st.markdown(U.md(f"- {t}"))
        for n in row["notes"] or []:
            st.markdown(U.md(f"- *Note:* {n}"))

    if row["domain"] == "conflict":
        st.markdown("##### Column missingness (all rows of this dataset)")
        opts = U.event_options(v, source)
        ev = U.events(v, source, opts["date_min"], opts["date_max"], (), ())
        st.dataframe(QA.missingness(ev, source), hide_index=True, width="stretch",
                     column_config={"share_missing": st.column_config.ProgressColumn(
                         "share missing", format="percent", min_value=0, max_value=1)})  # fmt: skip

    with st.expander("Database diagnostics"):
        st.json(diagnostics())

    path = QUALITY_DIR / f"{source}.json"
    if path.exists():
        st.download_button("Download machine-readable quality report (JSON)", path.read_bytes(),
                           file_name=path.name, mime="application/json")  # fmt: skip
        with st.expander("View JSON"):
            st.json(json.loads(path.read_text()), expanded=False)


def diagnostics() -> dict:
    """Facts about the database file the app is actually using (for maintenance)."""
    from datetime import datetime, timezone

    from src.config import DB_PATH, PROCESSED_DIR, SOURCES
    from src.database.db import SCHEMA_VERSION, schema_version

    out = {
        "code_version": U.code_version(),
        "modules_loaded_for": str(getattr(__import__("src"), "LOADED_FOR", "n/a"))[:7],
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "schema_version_expected": SCHEMA_VERSION,
        "schema_version_found": schema_version(DB_PATH),
        "sipri_raw_present": any(SOURCES["sipri_milex"].raw_dir.glob("SIPRI-Milex-data-*.xlsx")),
        "processed_dir": sorted(p.name for p in PROCESSED_DIR.iterdir()) if PROCESSED_DIR.exists() else [],
    }
    out["rebuild_log"] = list(U.rebuild_log())
    if DB_PATH.exists():
        out["db_modified_utc"] = datetime.fromtimestamp(DB_PATH.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        out["tables"] = sorted(r[0] for r in U.cursor().execute("SHOW TABLES").fetchall())
    return out
