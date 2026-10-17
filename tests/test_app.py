"""Smoke tests: every dashboard page renders without exceptions.

Uses the project database (built from the bundled synthetic data if absent).
"""

import pytest
from streamlit.testing.v1 import AppTest

from src.config import ROOT


def _page(name, root):
    import importlib
    import sys

    sys.path.insert(0, root)
    importlib.import_module(f"src.ui.page_{name}").render()


@pytest.mark.parametrize("page", ["overview", "conflict", "defence", "research", "quality"])
def test_page_renders(page):
    at = AppTest.from_function(_page, args=(page, str(ROOT)), default_timeout=180)
    at.run()
    assert not at.exception, [e.message for e in at.exception]


def test_synthetic_source_shows_banner():
    at = AppTest.from_function(_page, args=("conflict", str(ROOT)), default_timeout=180)
    at.run()
    at.sidebar.selectbox(key="conflict_source").set_value("synthetic_events").run()
    assert not at.exception
    assert any("SYNTHETIC" in e.value for e in at.error)


def test_main_app_runs():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.run()
    assert not at.exception


def test_stale_project_modules_are_reloaded():
    """If the loaded modules came from another commit, the next run re-imports them."""
    import sys

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.run()
    common = sys.modules["src.ui.common"]
    common._stale_marker = True
    sys.modules["src"].LOADED_FOR = "some-older-commit"
    at.run()
    assert not at.exception
    assert not hasattr(sys.modules["src.ui.common"], "_stale_marker")
    assert sys.modules["src"].LOADED_FOR != "some-older-commit"
