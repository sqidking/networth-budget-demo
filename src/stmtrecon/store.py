"""SQLite storage: accounts, imports, transactions and categorizing rules.

Neither PDF statements nor CSV exports carry a transaction ID, so re-imports are de-duplicated by counting:
rows match when they're in the same account with the same date (the purchase date when there is one) and
amount, and their descriptions agree loosely (``same_description``), because a statement and a CSV word the
same purchase differently. If a row appears n times in the file and m times in the database, only n - m copies
are added. Overlapping downloads add nothing, and two identical purchases on the same day are both kept.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import networth
from .models import ACCOUNT_TYPES, ParsedFile, ParsedTxn
from .text import merchant_name, normalize

# The date duplicates are matched on and spending is dated by: the purchase date when there is one.
MATCH_DATE = "match_date TEXT GENERATED ALWAYS AS (COALESCE(txn_date, posted_date)) VIRTUAL"
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS bank_accounts (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    type    TEXT NOT NULL CHECK (type IN ('checking', 'credit_card')),
    last4   TEXT,
    active  INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS categories (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE,
    kind  TEXT NOT NULL DEFAULT 'spending' CHECK (kind IN ('spending', 'income', 'transfer'))
);
CREATE TABLE IF NOT EXISTS budgets (
    category_id  INTEGER PRIMARY KEY REFERENCES categories(id) ON DELETE CASCADE,
    monthly      REAL NOT NULL CHECK (monthly >= 0)
);
CREATE TABLE IF NOT EXISTS category_rules (
    id               INTEGER PRIMARY KEY,
    source           TEXT NOT NULL CHECK (source IN ('merchant', 'bank')),
    match_text       TEXT NOT NULL,
    category_id      INTEGER NOT NULL REFERENCES categories(id),
    bank_account_id  INTEGER REFERENCES bank_accounts(id),
    priority         INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS imports (
    id               INTEGER PRIMARY KEY,
    created_at       TEXT NOT NULL,
    filename         TEXT NOT NULL,
    bank_account_id  INTEGER NOT NULL REFERENCES bank_accounts(id),
    format           TEXT NOT NULL,
    date_from        TEXT,
    date_to          TEXT,
    file_hash        TEXT UNIQUE,
    rows_added       INTEGER NOT NULL DEFAULT 0,
    rows_skipped     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS transactions (
    id               INTEGER PRIMARY KEY,
    bank_account_id  INTEGER NOT NULL REFERENCES bank_accounts(id),
    posted_date      TEXT NOT NULL,
    txn_date         TEXT,
    description      TEXT NOT NULL,
    merchant         TEXT NOT NULL,
    amount           REAL NOT NULL,
    bank_category    TEXT NOT NULL DEFAULT '',
    bank_type        TEXT NOT NULL DEFAULT '',
    memo             TEXT NOT NULL DEFAULT '',
    category_id      INTEGER REFERENCES categories(id),
    category_source  TEXT,
    import_id        INTEGER NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
    {MATCH_DATE}
);
"""
INDEXES = """
DROP INDEX IF EXISTS idx_txn_match;
CREATE INDEX IF NOT EXISTS idx_txn_match_date ON transactions(bank_account_id, match_date, amount);
"""


def connect(path: str = ":memory:") -> sqlite3.Connection:
    """Open (or create) the database. A database file is made readable by its owner only (0600), since it holds
    bank transactions; SQLite gives its journal files the same permissions."""
    if path != ":memory:" and not path.startswith("file:"):
        db = Path(path)
        db.touch(mode=0o600, exist_ok=True)
        db.chmod(0o600)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA + networth.SCHEMA)
    if "match_date" not in {r["name"] for r in conn.execute("PRAGMA table_xinfo(transactions)")}:
        conn.execute(f"ALTER TABLE transactions ADD COLUMN {MATCH_DATE}")      # a database from before it existed
    conn.executescript(INDEXES)
    return conn


def add_bank_account(conn: sqlite3.Connection, name: str, type: str, last4: str | None = None) -> int:
    with conn:
        return conn.execute("INSERT INTO bank_accounts (name, type, last4) VALUES (?, ?, ?)",
                            (name, type, last4)).lastrowid


def add_rule(conn: sqlite3.Connection, match_text: str, category: str, source: str = "merchant",
             bank_account_id: int | None = None, priority: int = 0, kind: str = "spending") -> int:
    """Add a categorizing rule, creating its category if needed, and apply it to every transaction that has no
    category yet, all in one database transaction. ``kind`` (spending | income | transfer) applies to a new
    category: only spending categories count toward spending and budgets, so card payoffs and pay aren't."""
    with conn:
        conn.execute("INSERT OR IGNORE INTO categories (name, kind) VALUES (?, ?)", (category, kind))
        cid = conn.execute("SELECT id FROM categories WHERE name = ?", (category,)).fetchone()[0]
        rule_id = conn.execute(
            "INSERT INTO category_rules (source, match_text, category_id, bank_account_id, priority) "
            "VALUES (?, ?, ?, ?, ?)", (source, match_text, cid, bank_account_id, priority)).lastrowid
        _apply_rules(conn)
    return rule_id


# --------------------------------------------------------------------------- reading

def bank_accounts(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT id, name, type, last4, active FROM bank_accounts ORDER BY id")]


def category_names(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT name FROM categories ORDER BY name")]


def transactions(conn: sqlite3.Connection) -> list[dict]:
    """Every stored transaction, newest first. ``category`` and ``why`` are None until a rule matches."""
    return [dict(r) for r in conn.execute(
        "SELECT t.posted_date AS date, a.name AS account, t.description, t.amount, c.name AS category, "
        "t.category_source AS why, i.filename AS source FROM transactions t "
        "JOIN bank_accounts a ON a.id = t.bank_account_id JOIN imports i ON i.id = t.import_id "
        "LEFT JOIN categories c ON c.id = t.category_id ORDER BY t.posted_date DESC, t.id DESC")]


def pending_merchants(conn: sqlite3.Connection) -> list[dict]:
    """Merchants with uncategorized transactions: how many and their total, most frequent first."""
    return [dict(r) for r in conn.execute(
        "SELECT merchant, count(*) AS n, sum(amount) AS total FROM transactions WHERE category_id IS NULL "
        "GROUP BY merchant ORDER BY n DESC, merchant")]


def imports(conn: sqlite3.Connection) -> list[dict]:
    """Every import, newest first, with the account it went into."""
    return [dict(r) for r in conn.execute(
        "SELECT i.id, i.created_at, i.filename, a.name AS account, i.date_from, i.date_to, i.rows_added, "
        "i.rows_skipped FROM imports i JOIN bank_accounts a ON a.id = i.bank_account_id ORDER BY i.id DESC")]


# --------------------------------------------------------------------------- categorizing

@dataclass
class Match:
    category_id: int
    why: str


class Categorizer:
    """The current rules, compiled once. Merchant rules match whole words of the cleaned merchant name;
    the highest priority wins, then the longest (most specific) text. Bank rules match the bank's own
    category, then its transaction type, exactly (ignoring case)."""

    def __init__(self, conn: sqlite3.Connection):
        rows = [dict(r) for r in conn.execute("SELECT * FROM category_rules ORDER BY id")]
        merchant = [r for r in rows if r["source"] == "merchant" and normalize(r["match_text"])]
        merchant.sort(key=lambda r: (-r["priority"], -len(normalize(r["match_text"]))))
        self._merchant = [(re.compile(rf"(?<![A-Z0-9]){re.escape(normalize(r['match_text']))}(?![A-Z0-9])"), r)
                          for r in merchant]
        self._bank: dict[str, dict] = {}
        for r in sorted((r for r in rows if r["source"] == "bank"), key=lambda r: -r["priority"]):
            self._bank.setdefault(r["match_text"].strip().lower(), r)

    def match(self, bank_account_id: int, merchant: str, bank_category: str, bank_type: str) -> Match | None:
        for pat, r in self._merchant:
            if r["bank_account_id"] in (None, bank_account_id) and pat.search(merchant):
                return Match(r["category_id"], f"Rule: {r['match_text']}")
        for key in (bank_category, bank_type):
            r = self._bank.get(key.strip().lower()) if key else None
            if r:
                return Match(r["category_id"], f"Bank: {key}")
        return None


def _apply_rules(conn: sqlite3.Connection, import_id: int | None = None) -> None:
    """Give each uncategorized transaction (of one import, or all of them) the category of the rule it matches.
    Runs inside the caller's database transaction."""
    rules = Categorizer(conn)
    rows = conn.execute("SELECT id, bank_account_id, merchant, bank_category, bank_type FROM transactions "
                        "WHERE category_id IS NULL AND (? IS NULL OR import_id = ?)", (import_id, import_id))
    for r in rows.fetchall():
        m = rules.match(r["bank_account_id"], r["merchant"], r["bank_category"], r["bank_type"])
        if m:
            conn.execute("UPDATE transactions SET category_id = ?, category_source = ? WHERE id = ?",
                         (m.category_id, m.why, r["id"]))


# --------------------------------------------------------------------------- de-duplication & import

DESCRIPTION_MATCH_CHARS = 12


def _loose(description: str) -> str:
    return merchant_name(description).replace(" ", "")[:DESCRIPTION_MATCH_CHARS]


def same_description(a: str, b: str) -> bool:
    """Whether two descriptions could be the same transaction: the first 12 letters and digits of the cleaned
    merchant names agree, or all of the shorter one. A statement's ``BOOKSHOP ONLINE*AB12CD34 example.com WA``
    is the CSV's ``BOOKSHOP ONLINE*AB12CD34``."""
    a, b = _loose(a), _loose(b)
    n = min(len(a), len(b))
    return a[:n] == b[:n]


def mark_new(conn: sqlite3.Connection, bank_account_id: int, rows: list[ParsedTxn]) -> list[bool]:
    """For each row, whether it's new (True) or already stored (False). Each stored row can only account
    for one row of the file."""
    if not rows:
        return []
    lo, hi = min(r.match_date for r in rows).isoformat(), max(r.match_date for r in rows).isoformat()
    found = conn.execute("SELECT match_date, amount, description FROM transactions "
                         "WHERE bank_account_id = ? AND match_date BETWEEN ? AND ?", (bank_account_id, lo, hi))
    remaining: dict[tuple[str, float], list[str]] = {}
    for d, a, desc in found:
        remaining.setdefault((d, round(a, 2)), []).append(desc)
    flags = []
    for r in rows:
        stored = remaining.get((r.match_date.isoformat(), round(r.amount, 2)), [])
        hit = next((i for i, desc in enumerate(stored) if same_description(desc, r.description)), None)
        if hit is not None:
            stored.pop(hit)
        flags.append(hit is None)
    return flags


@dataclass
class ImportResult:
    added: int
    skipped: int
    import_id: int | None


def import_transactions(conn: sqlite3.Connection, bank_account_id: int, parsed: ParsedFile,
                        filename: str = "", file_hash: str | None = None) -> ImportResult:
    """Add the file's new rows in one database transaction. A file with a hash (a PDF statement) is recorded
    even when it adds nothing, so a folder scan knows it's done."""
    acct = conn.execute("SELECT type FROM bank_accounts WHERE id = ?", (bank_account_id,)).fetchone()
    if acct is None:
        raise ValueError("Pick an account for this file.")
    if acct["type"] != parsed.format.account_type:
        raise ValueError(f"This is a {parsed.format.label} file, but the chosen account is a "
                         f"{ACCOUNT_TYPES[acct['type']]} account.")
    flags = mark_new(conn, bank_account_id, parsed.rows)
    new_rows = [r for r, new in zip(parsed.rows, flags) if new]
    skipped = len(parsed.rows) - len(new_rows)
    if not new_rows and file_hash is None:
        return ImportResult(0, skipped, None)
    lo, hi = parsed.period or parsed.date_range or (None, None)
    with conn:
        import_id = conn.execute(
            "INSERT INTO imports (created_at, filename, bank_account_id, format, date_from, date_to, file_hash, "
            "rows_added, rows_skipped) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), filename, bank_account_id, parsed.format.key,
             lo.isoformat() if lo else None, hi.isoformat() if hi else None, file_hash,
             len(new_rows), skipped)).lastrowid
        conn.executemany(
            "INSERT INTO transactions (bank_account_id, posted_date, txn_date, description, merchant, amount, "
            "bank_category, bank_type, memo, import_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(bank_account_id, r.posted_date.isoformat(), r.txn_date.isoformat() if r.txn_date else None,
              r.description, merchant_name(r.description), r.amount, r.bank_category, r.bank_type, r.memo, import_id)
             for r in new_rows])
        _apply_rules(conn, import_id)
    return ImportResult(len(new_rows), skipped, import_id)


def undo_import(conn: sqlite3.Connection, import_id: int) -> int:
    """Remove one import and every transaction it added. Returns how many transactions were removed."""
    with conn:
        n = conn.execute("SELECT count(*) FROM transactions WHERE import_id = ?", (import_id,)).fetchone()[0]
        conn.execute("DELETE FROM imports WHERE id = ?", (import_id,))
    return n
