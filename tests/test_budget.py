import pandas as pd
import pytest

from stmtrecon import budget, store
from stmtrecon.csv_import import parse_csv
from stmtrecon.samples import everyday_exports

CARD = """Transaction Date,Post Date,Description,Category,Type,Amount,Memo
01/03/2026,01/04/2026,GROCERY MART #0001,Groceries,Sale,-80.00,
01/09/2026,01/10/2026,GROCERY MART #0001,Groceries,Sale,-20.00,
01/12/2026,01/13/2026,COFFEE HOUSE 00001,Food & Drink,Sale,-6.50,
01/20/2026,01/20/2026,Payment Thank You-Mobile,,Payment,300.00,
02/02/2026,02/03/2026,GROCERY MART #0001,Groceries,Sale,-50.00,
02/05/2026,02/06/2026,GROCERY MART #0001,Groceries,Return,10.00,
02/07/2026,02/08/2026,UNKNOWN SHOP,,Sale,-9.00,
"""


@pytest.fixture
def conn():
    c = store.connect()
    card = store.add_bank_account(c, "Card", "credit_card", "1234")
    store.add_rule(c, "Groceries", "Groceries", source="bank")
    store.add_rule(c, "Food & Drink", "Dining", source="bank")
    store.add_rule(c, "payment thank you", "Card payments", kind="transfer")
    store.import_transactions(c, card, parse_csv(CARD), "card.csv")
    yield c
    c.close()


def test_spending_excludes_transfers_and_counts_refunds(conn):
    df = budget.spending(conn)
    jan = budget.by_category(df[df["month"] == pd.Timestamp("2026-01-01")])
    feb = budget.by_category(df[df["month"] == pd.Timestamp("2026-02-01")])
    assert jan.to_dict() == {"Groceries": 100.0, "Dining": 6.5}         # the card payment isn't spending
    assert feb.to_dict() == {"Groceries": 40.0}                          # the refund lowers groceries
    assert budget.uncategorized(conn) == (1, 9.0)


def test_budgets_set_update_remove(conn):
    budget.set_budget(conn, "Groceries", 400)
    budget.set_budget(conn, "Groceries", 450)
    budget.set_budget(conn, "Dining", 100)
    assert budget.budgets(conn).to_dict() == {"Groceries": 450.0, "Dining": 100.0}
    budget.set_budget(conn, "Dining", None)
    assert budget.budgets(conn).to_dict() == {"Groceries": 450.0}
    with pytest.raises(ValueError, match="No spending category"):
        budget.set_budget(conn, "Card payments", 50)                      # a transfer category has no budget


def test_categories_keep_creation_order(conn):
    assert budget.categories(conn) == ["Groceries", "Dining"]           # transfer categories left out


def test_fold_keeps_six_parts():
    s = pd.Series({c: v for c, v in zip("ABCDEFGH", [80, 70, 60, 50, 40, 30, 20, 10])})
    folded = budget.fold(s)
    assert list(folded.index) == ["A", "B", "C", "D", "E", "Other"] and folded["Other"] == 60
    assert list(budget.fold(s.iloc[:6]).index) == list("ABCDEF")


def test_year_table(conn):
    t = budget.year_table(budget.spending(conn), 2026)
    assert list(t.index) == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-02-01")]
    assert t.loc[pd.Timestamp("2026-02-01"), "Dining"] == 0


def test_everyday_exports_are_stable_and_parse():
    card, checking = everyday_exports()
    assert (card, checking) == everyday_exports()                       # same every run
    c, k = parse_csv(card), parse_csv(checking)
    assert c.format.key == "example_card" and k.format.key == "example_checking"
    assert len(c.rows) > 500 and len(k.rows) == 24 * 6 + 23            # six bills a month, 23 card payoffs
    assert min(r.posted_date for r in c.rows).year == 2024


def test_suggestions_average_recent_months_and_round_up(conn):
    avg, n = budget.recent_average(budget.spending(conn))
    assert n == 2 and avg.to_dict() == {"Dining": 3.25, "Groceries": 70.0}
    assert budget.round_up(pd.Series([0.0, 3.25, 70.0, 70.01])).tolist() == [0.0, 10.0, 70.0, 80.0]
