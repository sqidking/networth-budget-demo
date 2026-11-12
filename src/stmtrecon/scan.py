"""Scan a folder of PDF statements: what importing each one would do, and why a file can't be imported."""
from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from . import store
from .models import ACCOUNT_TYPES
from .pdf_statements import Statement, parse_statement, pdf_text
from .text import last4_from_filename


class State(Enum):
    READY = "Ready"
    IMPORTED = "Already imported"
    BLOCKED = "Can't import"


@dataclass(frozen=True)
class Found:
    path: Path
    file_hash: str
    state: State
    reason: str = ""                     # why a BLOCKED file can't be imported
    statement: Statement | None = None   # None when already imported or unreadable
    bank_account_id: int | None = None   # set when READY
    new_rows: int = 0

    @property
    def ready(self) -> bool:
        return self.state is State.READY

    @property
    def status(self) -> str:
        """One line for people: the state, or for a blocked file the reason."""
        return self.reason if self.state is State.BLOCKED else self.state.value


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assess(conn: sqlite3.Connection, path: Path, done: set[str], banks: list[dict],
            read: Callable[[Path], str]) -> Found:
    """What importing one file would do: which account it goes into, or why it can't be imported."""
    h = file_hash(path)
    if h in done:
        return Found(path, h, State.IMPORTED)
    try:
        st = parse_statement(read(path))
    except Exception as e:  # noqa: BLE001 - one unreadable PDF shouldn't stop the rest of the scan
        return Found(path, h, State.BLOCKED, f"Can't read: {e}")
    last4 = last4_from_filename(path.name) or st.last4
    acct = next((b for b in banks if last4 and b["last4"] == last4), None)
    if acct is None:
        reason = f"No bank account ending in {last4}" if last4 else "Can't tell which account"
    elif acct["type"] != st.parsed.format.account_type:
        reason = f"Account ending in {last4} isn't a {ACCOUNT_TYPES[st.parsed.format.account_type]}"
    elif not st.ok:
        reason = "Doesn't add up"
    else:
        return Found(path, h, State.READY, statement=st, bank_account_id=acct["id"],
                     new_rows=sum(store.mark_new(conn, acct["id"], st.parsed.rows)))
    return Found(path, h, State.BLOCKED, reason, st)


def scan(conn: sqlite3.Connection, folder: Path, read: Callable[[Path], str] = pdf_text) -> list[Found]:
    """Every PDF in the folder, newest statement first. Files already imported (by SHA-256) aren't read again."""
    done = {r[0] for r in conn.execute("SELECT file_hash FROM imports WHERE file_hash IS NOT NULL")}
    banks = [b for b in store.bank_accounts(conn) if b["active"]]
    pdfs = [p for p in folder.iterdir() if p.suffix.lower() == ".pdf" and p.is_file()] if folder.is_dir() else []
    return [_assess(conn, p, done, banks, read) for p in sorted(pdfs, key=lambda p: p.name, reverse=True)]


def import_found(conn: sqlite3.Connection, f: Found) -> store.ImportResult:
    if not f.ready:
        raise ValueError(f"{f.path.name}: {f.status}")
    return store.import_transactions(conn, f.bank_account_id, f.statement.parsed, f.path.name, f.file_hash)
