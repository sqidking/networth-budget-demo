from datetime import date

import pandas as pd
import pytest

from stmtrecon import networth, store
from stmtrecon.samples import networth_history


@pytest.fixture
def conn():
    c = store.connect()
    yield c
    c.close()


def test_balances_carry_forward_and_totals(conn):
    cash = networth.add_account(conn, "Cash", "asset", "Cash")
    loan = networth.add_account(conn, "Loan", "debt", "Loans")
    networth.set_balance(conn, cash, date(2026, 1, 15), 1000)          # any day: stored as the month
    networth.set_balance(conn, loan, date(2026, 1, 1), 400)
    networth.set_balance(conn, cash, date(2026, 3, 1), 1300)           # nothing recorded in February
    nw = networth.load(conn)
    wide = nw.balances
    assert [f"{m:%Y-%m}" for m in wide.index] == ["2026-01", "2026-02", "2026-03"]
    assert wide["Cash"].tolist() == [1000, 1000, 1300] and wide["Loan"].tolist() == [400, 400, 400]
    t = nw.totals
    assert t["Net worth"].tolist() == [600, 600, 900]
    assert nw.ago(0)["Net worth"] == 900 and nw.ago(2)["Net worth"] == 600 and nw.ago(3) is None
    assert nw.at(pd.Timestamp("2026-02-01")).to_dict() == {"Cash": 1000, "Loan": 400}      # carried forward
    assert nw.at(pd.Timestamp("2025-12-01")).empty


def test_empty_history(conn):
    networth.add_account(conn, "Cash", "asset")
    nw = networth.load(conn)
    assert nw.empty and nw.ago(0) is None and nw.at(pd.Timestamp("2026-01-01")).empty
    assert nw.accounts[0].group == "Other"


def test_set_balance_updates_and_removes(conn):
    cash = networth.add_account(conn, "Cash", "asset")
    networth.set_balance(conn, cash, date(2026, 1, 1), 10)
    networth.set_balance(conn, cash, date(2026, 1, 1), 20)
    assert networth.load(conn).balances["Cash"].tolist() == [20]
    networth.set_balance(conn, cash, date(2026, 1, 1), None)
    assert networth.load(conn).empty


def test_account_added_later_is_blank_before_its_first_balance(conn):
    a = networth.add_account(conn, "Old", "asset")
    b = networth.add_account(conn, "New", "asset")
    networth.set_balance(conn, a, date(2026, 1, 1), 5)
    networth.set_balance(conn, b, date(2026, 2, 1), 7)
    nw = networth.load(conn)
    assert nw.balances["New"].isna().tolist() == [True, False]
    assert nw.totals["Assets"].tolist() == [5, 12]


def test_sample_history_is_stable():
    h = networth_history()
    assert h == networth_history()
    assert all(len(rows) == 24 for _, _, _, rows in h)
    assert {kind for _, kind, _, _ in h} == {"asset", "debt"}
