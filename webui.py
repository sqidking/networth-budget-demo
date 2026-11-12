"""Shared pieces of the web pages: the database connection, palette, formatting and spending data."""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from stmtrecon import budget, charts, store

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get("DEMO_DB") or ROOT / "demo.db")    # DEMO_DB=real.db keeps real data apart from the demo
UPLOADS = ROOT / "uploads"
SAMPLES = ROOT / "samples"
CHART = {"displayModeBar": False}
_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>#!|~$])")      # links, images, HTML, emphasis, code, tables, math


def md(text: object) -> str:
    """Text from a file (names, merchants, PDF labels), escaped so markdown shows it as plain text: no links,
    remote images or formatting."""
    return _MD_SPECIAL.sub(r"\\\1", str(text))


def scan_folder(typed: str) -> Path | None:
    """The folder to scan, relative to the project unless it's a full path. None for a folder outside the project
    while the app is reachable from other computers, so visitors can't read PDFs from anywhere on this one."""
    folder = (ROOT / typed).resolve()                    # a full path replaces ROOT
    local_only = (st.get_option("server.address") or "") in ("127.0.0.1", "localhost", "::1")   # see config.toml
    return folder if local_only or folder.is_relative_to(ROOT) else None


def save_upload(name: str, data: bytes) -> None:
    """Save an uploaded statement in uploads/, readable by its owner only."""
    name = Path(name).name                  # drop any folder parts, so nothing lands outside uploads/
    if not name.lower().endswith(".pdf"):
        return
    UPLOADS.mkdir(mode=0o700, exist_ok=True)
    UPLOADS.chmod(0o700)
    dest = UPLOADS / name
    if dest.exists() and dest.read_bytes() == data:
        return
    dest.touch(mode=0o600, exist_ok=True)
    dest.chmod(0o600)
    dest.write_bytes(data)


def connect() -> sqlite3.Connection:
    """Open the database for this run of this browser session. Kept in the session, not in a module global: every
    session shares this module, and runs on its own thread, and a SQLite connection works only on its own."""
    st.session_state["conn"] = conn = store.connect(str(DB))
    return conn


def conn() -> sqlite3.Connection:
    """This session's connection, opened by app.py on every run."""
    return st.session_state["conn"]


def palette() -> charts.Palette:
    """The chart palette for this browser's light or dark theme."""
    return charts.palette(st.context.theme.type or "light")


def plural(n: int, word: str, many: str | None = None) -> str:
    """"1 transaction", "3 transactions"; ``many`` for irregular plurals."""
    return f"{n:,} {word if n == 1 else many or word + 's'}"


def page_style() -> None:
    """A little CSS on top of the theme in .streamlit/config.toml: less empty space above each page's title."""
    st.html("<style>[data-testid='stMainBlockContainer'] { padding-top: 3rem; }</style>")


def money(v: float, cents: bool = False) -> str:
    s = f"${abs(v):,.2f}" if cents else f"${abs(v):,.0f}"
    return f"-{s}" if v < 0 else s


def table_view(df: pd.DataFrame, label: str = "Show as a table") -> None:
    with st.expander(label):
        st.dataframe(df, width="stretch")


def left_metric(col, budgeted: float, spent: float) -> None:
    """A metric card with what's left of a budget, or how far over it the spending went."""
    col.metric("Left" if spent <= budgeted else "Over by", money(abs(budgeted - spent)), border=True, height="stretch")


@dataclass(frozen=True)
class Spending:
    df: pd.DataFrame                # see budget.spending
    colors: dict[str, str]          # category -> chart color
    budgets: pd.Series              # monthly budget by category


def spending(conn: sqlite3.Connection) -> Spending:
    return Spending(budget.spending(conn), charts.colors(budget.categories(conn), palette()),
                    budget.budgets(conn))


def require_spending(conn: sqlite3.Connection) -> Spending:
    """The spending data for a chart page. With none yet, says how to get some and stops the page."""
    s = spending(conn)
    if s.df.empty:
        st.info("No categorized spending yet. Click **Load sample data** in the sidebar, or import transactions on "
                "**Statement Parse** and give them categories on its **Review** tab.")
        st.stop()
    n, total = budget.uncategorized(conn)
    if n:
        st.caption(f"{plural(n, 'uncategorized transaction')} ({money(total)}) not included. Categorize them on "
                   "**Statement Parse → Review**.")
    return s


def reset(conn: sqlite3.Connection) -> None:
    conn.close()
    DB.unlink(missing_ok=True)
    shutil.rmtree(UPLOADS, ignore_errors=True)
