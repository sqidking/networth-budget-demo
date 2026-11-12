from datetime import date

import pytest

from stmtrecon import pdf_statements as ps
from stmtrecon.sample_text import CARD, CHECKING


def test_card_statement_parses_and_adds_up():
    st = ps.parse_statement(CARD)
    assert st.ok, st.problems
    p = st.parsed
    assert p.format.key == "example_card_pdf" and st.last4 == "1234"
    assert p.period == (date(2025, 12, 5), date(2026, 1, 4))
    assert len(p.rows) == 8                                   # points-activity rows aren't account activity
    payment, refund, book = p.rows[:3]
    assert (payment.amount, payment.bank_type) == (850.0, "Payment")
    assert (refund.amount, refund.bank_type) == (13.85, "Return")
    assert (book.txn_date, book.amount) == (date(2025, 12, 4), -27.18)   # before the opening date: prior year
    assert book.memo == "Order Number 000-0000000-0000001"
    assert p.rows[4].txn_date == date(2026, 1, 2)             # January rows land in the closing year
    assert p.rows[6].amount == -0.99                          # ".99" with no leading zero
    assert (p.rows[7].amount, p.rows[7].bank_type) == (-39.0, "Fee")


def test_checking_statement_parses_and_adds_up():
    st = ps.parse_statement(CHECKING)
    assert st.ok, st.problems
    rows = st.parsed.rows
    assert [r.amount for r in rows] == [2500.0, -75.0, -6.5, -850.0, -410.0, -200.0, -2.95]
    assert rows[0].posted_date == date(2025, 12, 19) and rows[0].txn_date is None
    assert (rows[1].description, rows[1].memo, rows[1].bank_type) == ("CHECK 3001", "3001", "CHECK_PAID")
    assert rows[5].bank_type == "ACCT_XFER"
    assert rows[6].bank_type == "FEE_TRANSACTION"


def test_card_with_no_activity_parses():
    text = CARD.split("AACCCCOOUUNNTT AACCTTIIVVIITTYY")[0]
    for amount in ("$850.00", "-$863.85", "+$162.37", "+$39.00", "$187.52"):
        text = text.replace(amount, "$0.00")
    st = ps.parse_statement(text)
    assert st.ok and st.parsed.rows == []


def test_statement_that_doesnt_add_up_is_flagged():
    st = ps.parse_statement(CARD.replace("121.20", "112.20"))       # a misread digit
    assert not st.ok
    assert any(p.startswith("Purchases: ") and "off by $9.00" in p for p in st.problems)
    st = ps.parse_statement(CHECKING.replace("410.00", "401.00"))
    assert any(p.startswith("Electronic Withdrawals: ") for p in st.problems)


def test_dropped_row_is_flagged():
    st = ps.parse_statement(CARD.replace("01/03 CLOUD STORAGE *Example example.com CA .99\n", ""))
    assert any("off by $0.99" in p for p in st.problems)


def test_unknown_text_is_rejected():
    with pytest.raises(ValueError, match="Not a recognized"):
        ps.parse_statement("Hello")
