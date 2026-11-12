"""Smoke test of the web pages: each loads empty, the sample data imports, every page renders, and the main
actions work."""
import shutil
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["views/statement_parse.py", "views/budgets.py", "views/monthly_spending.py", "views/yearly_spending.py",
         "views/net_worth.py"]


@pytest.fixture
def app(tmp_path):
    for f in ("app.py", "webui.py"):
        shutil.copy(ROOT / f, tmp_path / f)
    shutil.copytree(ROOT / "views", tmp_path / "views", ignore=shutil.ignore_patterns("__pycache__"))
    return AppTest.from_file(str(tmp_path / "app.py"), default_timeout=60)


def _load(app):
    app.run()
    next(b for b in app.sidebar.button if b.label == "Load sample data").click().run()
    assert not app.exception


@pytest.mark.parametrize("page", PAGES)
def test_pages_render_empty(app, page):
    app.run()
    app.switch_page(page).run()
    assert not app.exception


@pytest.mark.parametrize("page", PAGES)
def test_pages_render_with_samples(app, page):
    _load(app)
    app.switch_page(page).run()
    assert not app.exception


def test_statements_import_and_review(app):
    _load(app)
    text = " ".join(m.value for m in app.markdown)
    assert "Doesn't add up" in text and text.count("Ready") >= 2
    assert any(r"off by \$9.00" in e.value for e in app.error)      # $ escaped so it isn't read as math
    next(b for b in app.button if b.label.startswith("Import 2 ready")).click().run()
    assert not app.exception
    app.selectbox(key="cat0").select("Dining").run()
    app.button(key="save0").click().run()
    assert not app.exception


def test_reset_needs_confirming(app):
    _load(app)
    assert not any(b.label == "Reset demo" for b in app.sidebar.button)   # behind a popover, not one click
    next(b for b in app.sidebar.button if b.label == "Delete everything").click().run()
    assert not app.exception
    app.switch_page("views/statement_parse.py").run()
    assert any("No transactions yet" in i.value for i in app.info)


@pytest.mark.parametrize(("address", "refused"), [("127.0.0.1", False), ("0.0.0.0", True)])
def test_outside_folder_refused_when_not_local(app, address, refused):
    from streamlit import config

    before = config.get_option("server.address")
    config.set_option("server.address", address)
    try:
        app.run()
        next(t for t in app.text_input if t.label == "Folder to scan").input("/etc").run()
    finally:
        config.set_option("server.address", before)
    assert any("Only folders inside the project" in e.value for e in app.error) == refused


def test_file_text_is_escaped(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    import webui

    assert webui.md("![x](u) <b>[a](u)</b> $5 *b* `c`") == r"\!\[x\](u) \<b\>\[a\](u)\</b\> \$5 \*b\* \`c\`"


def test_month_and_year_selectors(app):
    _load(app)
    app.switch_page("views/monthly_spending.py").run()
    month = next(s for s in app.selectbox if s.label == "Month")
    month.select(month.options[-1]).run()                      # oldest month: nothing before it
    assert not app.exception
    app.switch_page("views/yearly_spending.py").run()
    year = next(s for s in app.selectbox if s.label == "Year")
    year.select(year.options[-1]).run()
    assert not app.exception


def test_net_worth_numbers_and_save(app):
    _load(app)
    app.switch_page("views/net_worth.py").run()
    assert next(m for m in app.metric if m.label == "Net worth").value.startswith("$")
    next(b for b in app.button if b.label.startswith("Save ")).click().run()   # records next month's balances
    assert not app.exception
