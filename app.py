"""European Conflict & Security Intelligence - Streamlit entry point.

    streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


def _git_head(root: Path) -> str:
    """Commit of the files on disk (read from .git; this file is re-executed on every run)."""
    try:
        head = (root / ".git" / "HEAD").read_text().strip()
        if not head.startswith("ref:"):
            return head
        ref = head.split(" ", 1)[1]
        loose = root / ".git" / ref
        if loose.exists():
            return loose.read_text().strip()
        for line in (root / ".git" / "packed-refs").read_text().splitlines():
            if line.endswith(ref):
                return line.split()[0]
    except OSError:
        pass
    return "unknown"


# Hosting platforms can update the files of a running server while keeping the
# project modules already imported in memory, so new code would not take effect.
# When the commit on disk differs from the one the loaded modules came from,
# drop every project module so the imports below re-execute the current code.
_HEAD = _git_head(Path(__file__).resolve().parent)
if "src" in sys.modules and getattr(sys.modules["src"], "LOADED_FOR", None) != _HEAD:
    for _name in [m for m in sys.modules if m == "src" or m.startswith("src.")]:
        del sys.modules[_name]

import src  # noqa: E402

src.LOADED_FOR = _HEAD

from src.config import ROOT  # noqa: E402
from src.ui import common as U  # noqa: E402
from src.ui import page_conflict, page_defence, page_overview, page_quality, page_research  # noqa: E402

st.set_page_config(
    page_title="European Conflict & Security Intelligence",
    page_icon=":material/public:",
    layout="wide",
)
st.markdown(U.CSS, unsafe_allow_html=True)


def methodology() -> None:
    U.page_header("Documentation", "Methodology & limitations",
                  "Definitions, denominators, transformations and caveats for every metric.")  # fmt: skip
    st.markdown(U.md((ROOT / "docs" / "METHODOLOGY.md").read_text().split("\n", 1)[1]))


pages = st.navigation(
    [
        st.Page(page_overview.render, title="Overview", icon=":material/dashboard:", url_path="overview", default=True),
        st.Page(page_conflict.render, title="Conflict patterns", icon=":material/location_on:", url_path="conflict"),
        st.Page(page_defence.render, title="Defence trends", icon=":material/account_balance:", url_path="defence"),
        st.Page(page_research.render, title="Research", icon=":material/science:", url_path="research"),
        st.Page(page_quality.render, title="Data quality", icon=":material/fact_check:", url_path="quality"),
        st.Page(methodology, title="Methodology", icon=":material/menu_book:", url_path="methodology"),
    ]
)  # fmt: skip

with st.sidebar:
    reg = U.registry(U.db_version())
    st.caption(
        "Data last processed: "
        + max(str(x) for x in reg["processed_at_utc"])[:16].replace("T", " ")
        + f" UTC · code {U.code_version()}"
    )

pages.run()

st.sidebar.divider()
st.sidebar.caption(
    "Public-data descriptive analytics. Not an operational targeting system, not an "
    "authoritative intelligence product, not a prediction model."
)
