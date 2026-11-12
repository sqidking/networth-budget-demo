"""Net worth: accounts (assets and debts) with one balance per month.

Debts are stored as the positive amount owed. A month with no balance for an account carries its last known
balance forward, so updating only the accounts that changed is enough.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from functools import cached_property

import pandas as pd

from .budget import OTHER

SCHEMA = """
CREATE TABLE IF NOT EXISTS nw_accounts (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    kind    TEXT NOT NULL CHECK (kind IN ('asset', 'debt')),
    grp     TEXT NOT NULL DEFAULT '',
    active  INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS nw_balances (
    account_id  INTEGER NOT NULL REFERENCES nw_accounts(id) ON DELETE CASCADE,
    as_of       TEXT NOT NULL,                  -- first day of the month
    balance     REAL NOT NULL,
    PRIMARY KEY (account_id, as_of)
);
"""


@dataclass(frozen=True)
class Account:
    id: int
    name: str
    kind: str                # asset | debt
    group: str               # "Other" when none was given


def add_account(conn: sqlite3.Connection, name: str, kind: str, group: str = "") -> int:
    with conn:
        return conn.execute("INSERT INTO nw_accounts (name, kind, grp) VALUES (?, ?, ?)",
                            (name, kind, group)).lastrowid


def accounts(conn: sqlite3.Connection) -> list[Account]:
    """Active accounts, assets first, each kind in the order they were added."""
    return [Account(r["id"], r["name"], r["kind"], r["grp"] or OTHER)
            for r in conn.execute("SELECT id, name, kind, grp FROM nw_accounts WHERE active = 1 ORDER BY kind, id")]


def _month(d: date) -> str:
    return date(d.year, d.month, 1).isoformat()


def set_balance(conn: sqlite3.Connection, account_id: int, as_of: date, balance: float | None) -> None:
    """Record an account's balance for the month containing ``as_of``; None removes that month's entry."""
    with conn:
        if balance is None:
            conn.execute("DELETE FROM nw_balances WHERE account_id = ? AND as_of = ?", (account_id, _month(as_of)))
        else:
            conn.execute("INSERT INTO nw_balances (account_id, as_of, balance) VALUES (?, ?, ?) "
                         "ON CONFLICT (account_id, as_of) DO UPDATE SET balance = excluded.balance",
                         (account_id, _month(as_of), round(balance, 2)))


def recorded(conn: sqlite3.Connection, as_of: date) -> dict[str, float]:
    """Balances entered for the month containing ``as_of`` (not carried forward), by account name."""
    return dict(conn.execute("SELECT a.name, b.balance FROM nw_balances b JOIN nw_accounts a ON a.id = b.account_id "
                             "WHERE b.as_of = ?", (_month(as_of),)).fetchall())


@dataclass
class NetWorth:
    """Active accounts and their balances: every month from the first balance to the last as rows, accounts as
    columns, last known balance carried forward (blank before an account's first balance). Debts are positive
    here; ``totals`` subtracts them."""
    accounts: list[Account]
    balances: pd.DataFrame

    @property
    def empty(self) -> bool:
        return self.balances.empty

    def names(self, kind: str) -> list[str]:
        """Accounts of one kind (asset | debt) that have a balance, in account order."""
        return [a.name for a in self.accounts if a.kind == kind and a.name in self.balances.columns]

    @cached_property
    def totals(self) -> pd.DataFrame:
        """Assets, debts and net worth by month."""
        assets = self.balances[self.names("asset")].sum(axis=1)
        debts = self.balances[self.names("debt")].sum(axis=1)
        return pd.DataFrame({"Assets": assets, "Debts": debts, "Net worth": assets - debts})

    def ago(self, months: int) -> pd.Series | None:
        """The totals ``months`` before the latest month (0 = the latest), or None when the history is shorter."""
        return self.totals.iloc[-1 - months] if len(self.totals) > months else None

    def at(self, month: pd.Timestamp) -> pd.Series:
        """Each account's balance as of ``month``, carried forward; empty before the first balance."""
        before = self.balances.loc[:month]
        return before.iloc[-1] if not before.empty else pd.Series(dtype=float)

    def latest(self, kind: str) -> pd.Series:
        """The latest month's balance per account of one kind, leaving out accounts with none yet."""
        return self.balances.iloc[-1][self.names(kind)].dropna()

    @property
    def asset_groups(self) -> list[str]:
        """Asset groups in a fixed order (by account creation), so each keeps its chart color."""
        return list(dict.fromkeys(a.group for a in self.accounts if a.kind == "asset"))

    def assets_by_group(self) -> pd.Series:
        """The latest assets summed by group, largest first."""
        group = {a.name: a.group for a in self.accounts}
        return self.latest("asset").groupby(group).sum().sort_values(ascending=False)


def load(conn: sqlite3.Connection) -> NetWorth:
    accts = accounts(conn)
    df = pd.read_sql_query("SELECT b.as_of, a.name, b.balance FROM nw_balances b "
                           "JOIN nw_accounts a ON a.id = b.account_id WHERE a.active = 1", conn)
    if df.empty:
        return NetWorth(accts, pd.DataFrame(index=pd.DatetimeIndex([])))
    df["as_of"] = pd.to_datetime(df["as_of"])
    wide = df.pivot_table(index="as_of", columns="name", values="balance", aggfunc="last")
    months = pd.date_range(wide.index.min(), wide.index.max(), freq="MS")
    order = [a.name for a in accts if a.name in wide.columns]
    return NetWorth(accts, wide.reindex(months).ffill()[order])
