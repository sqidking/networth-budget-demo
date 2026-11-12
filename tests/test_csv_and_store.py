import sqlite3
from datetime import date

import pytest

from stmtrecon import store
from stmtrecon.csv_import import parse_csv
from stmtrecon.sample_text import CARD_CSV, CHECKING_CSV
from stmtrecon.text import last4_from_filename, merchant_name


@pytest.fixture
def conn():
    c = store.connect()
    yield c
    c.close()


@pytest.fixture
def accts(conn):
    return (store.add_bank_account(conn, "Example Card", "credit_card", "1234"),
            store.add_bank_account(conn, "Checking", "checking", "5678"))


def _import(conn, acct, text, name="file.csv"):
    return store.import_transactions(conn, acct, parse_csv(text), name)


def _count(conn, where="1"):
    return conn.execute(f"SELECT count(*) FROM transactions WHERE {where}").fetchone()[0]


def test_parses_card_format():
    p = parse_csv(CARD_CSV)
    assert p.format.key == "example_card" and len(p.rows) == 5
    r = p.rows[0]
    assert (r.posted_date, r.txn_date, r.amount, r.bank_category, r.bank_type) == (
        date(2026, 2, 3), date(2026, 2, 2), -98.40, "Groceries", "Sale")
    assert p.date_range == (date(2026, 2, 3), date(2026, 2, 20))


def test_parses_checking_with_bom_and_trailing_comma():
    p = parse_csv(CHECKING_CSV.encode("utf-8"))
    assert p.format.key == "example_checking"
    assert [r.amount for r in p.rows] == [-500.00, -410.00, 2500.00, -75.00]
    assert p.rows[3].memo == "3002" and p.rows[0].txn_date is None


def test_unknown_header_and_bad_rows_are_rejected():
    with pytest.raises(ValueError, match="Unrecognized CSV columns"):
        parse_csv("Date,Payee,Amount\n02/01/2026,X,-1\n")
    lines = CARD_CSV.splitlines()
    with pytest.raises(ValueError, match="Line 3"):
        parse_csv(f"{lines[0]}\n{lines[1]}\n02/02/2026,bad,X,,Sale,-1,\n")


def test_last4_and_merchant_name():
    assert last4_from_filename("ExampleBank1234_Activity20260228.CSV") == "1234"
    assert last4_from_filename("20260104-statements-4321-.pdf") == "4321"
    assert last4_from_filename("export.csv") is None
    assert merchant_name("GROCERY MART #0001") == "GROCERY MART"
    assert merchant_name("COFFEE HOUSE 00001") == "COFFEE HOUSE"
    assert merchant_name("EXAMPLE LOAN SVC PPD ID: 0000000001") == "EXAMPLE LOAN SVC"


def test_same_description_is_loose_but_not_too_loose():
    assert store.same_description("BOOKSHOP ONLINE*AB12CD34 example.com WA", "BOOKSHOP ONLINE*AB12CD34")
    assert store.same_description("02/18 Payment To Example Bank Card Ending IN 1234",
                                  "Payment to Example Bank card ending in 1234 02/18")
    assert not store.same_description("COFFEE HOUSE 00001", "FUEL STOP 0001")


def test_reimport_adds_nothing_and_keeps_same_day_duplicates(conn, accts):
    card, _ = accts
    assert (_import(conn, card, CARD_CSV).added, _count(conn)) == (5, 5)
    again = _import(conn, card, CARD_CSV)
    assert (again.added, again.skipped, again.import_id) == (0, 5, None)
    assert _count(conn, "description LIKE 'COFFEE%'") == 2                # two real coffees, same day


def test_overlapping_download_adds_only_new_rows(conn, accts):
    card, _ = accts
    _import(conn, card, CARD_CSV)
    later = CARD_CSV + "02/25/2026,02/26/2026,FUEL STOP 0001,Gas,Sale,-44.05,\n"
    later += "02/02/2026,02/03/2026,COFFEE HOUSE 00001,Food & Drink,Sale,-6.50,\n"   # a third coffee
    r = _import(conn, card, later)
    assert (r.added, r.skipped) == (2, 5)


def test_same_rows_in_another_account_are_not_duplicates(conn, accts):
    card, _ = accts
    card2 = store.add_bank_account(conn, "Second Card", "credit_card", "9999")
    _import(conn, card, CARD_CSV)
    assert _import(conn, card2, CARD_CSV).added == 5


def test_account_type_must_match_file(conn, accts):
    _, chk = accts
    with pytest.raises(ValueError, match="credit card file"):
        _import(conn, chk, CARD_CSV)
    assert _count(conn) == 0


def test_rules_categorize_on_import(conn, accts):
    card, chk = accts
    store.add_rule(conn, "coffee house", "Coffee")
    store.add_rule(conn, "Groceries", "Food at home", source="bank")
    store.add_rule(conn, "example employer", "Income", priority=10)
    _import(conn, card, CARD_CSV)
    _import(conn, chk, CHECKING_CSV)
    got = dict(conn.execute("SELECT t.merchant, c.name FROM transactions t "
                            "LEFT JOIN categories c ON c.id = t.category_id"))
    assert got["COFFEE HOUSE"] == "Coffee"
    assert got["GROCERY MART"] == "Food at home"            # from the bank's own category
    assert got["EXAMPLE EMPLOYER PAYROLL"] == "Income"
    assert got["CHECK"] is None                              # no rule: left for review


def test_undo_import_removes_its_rows(conn, accts):
    card, chk = accts
    _import(conn, chk, CHECKING_CSV)
    r = _import(conn, card, CARD_CSV)
    assert store.undo_import(conn, r.import_id) == 5
    assert _count(conn) == 4
    assert conn.execute("SELECT count(*) FROM imports").fetchone()[0] == 1


def test_new_rule_categorizes_existing_rows(conn, accts):
    card, _ = accts
    _import(conn, card, CARD_CSV)
    assert _count(conn, "category_id IS NULL") == 5
    store.add_rule(conn, "coffee house", "Coffee")
    assert _count(conn, "category_source = 'Rule: coffee house'") == 2


def test_older_database_gets_match_date_and_its_index(tmp_path):
    db = tmp_path / "old.db"
    old = sqlite3.connect(db)                        # the transactions table as it was before match_date
    old.executescript("CREATE TABLE transactions (id INTEGER PRIMARY KEY, bank_account_id INTEGER NOT NULL, "
                      "posted_date TEXT NOT NULL, txn_date TEXT, amount REAL NOT NULL);"
                      "CREATE INDEX idx_txn_match ON transactions(bank_account_id, posted_date, amount);"
                      "INSERT INTO transactions VALUES (1, 1, '2026-02-03', '2026-02-02', -5), (2, 1, '2026-02-04', "
                      "NULL, -6);")
    old.close()
    conn = store.connect(str(db))
    assert [r[0] for r in conn.execute("SELECT match_date FROM transactions ORDER BY id")] == [
        "2026-02-02", "2026-02-04"]
    plan = " ".join(r["detail"] for r in conn.execute(
        "EXPLAIN QUERY PLAN SELECT amount FROM transactions WHERE bank_account_id = 1 AND match_date BETWEEN ? AND ?",
        ("2026-02-01", "2026-02-28")))
    assert "idx_txn_match_date (bank_account_id=? AND match_date>" in plan     # the date range uses it too
    conn.close()
