"""European Conflict & Security Intelligence - Streamlit entry point.

    streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from src.config import ROOT
from src.ui import common as U
from src.ui import page_conflict, page_defence, page_overview, page_quality, page_research

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
