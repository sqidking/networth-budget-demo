"""Invented sample data for the demo: PDF statements, CSV exports, accounts, rules, budgets and net worth.

    uv run python -m stmtrecon.samples [folder]      # write the sample files (default: ./samples)

Writes <folder>/statements/*.pdf (one card and one checking statement, plus a card statement with a misread
amount that the reconciler should refuse) and <folder>/exports/*.csv: the small exports that overlap the
statements, plus two years of invented everyday spending for a second card and checking account, so the month
and year views have something to show. Every merchant, amount and account number is made up.
"""
from __future__ import annotations

import calendar
import random
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

from . import budget, networth, sample_text, store
from .csv_import import parse_csv
from .text import last4_from_filename


def _undouble(text: str) -> str:
    """sample_text mimics pdfplumber's doubled bold letters; a generated PDF should print them once."""
    return re.sub(r"\b(?:([A-Z])\1)+\b", lambda m: m.group(0)[::2], text)


def write_pdf(text: str, path: Path) -> None:
    from fpdf import FPDF

    pdf = FPDF(format="letter")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    for line in _undouble(text).splitlines():
        pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


# --------------------------------------------------------------------------- two years of everyday spending

# Everyday card spending: (bank category, merchants, purchases per month (low, high), amount range).
CARD_HABITS = [
    ("Groceries", ["GROCERY MART #0001", "FRESH FOODS MARKET 0002"], (4, 6), (38, 125)),
    ("Food & Drink", ["COFFEE HOUSE 00001"], (5, 10), (4.25, 7.80)),
    ("Food & Drink", ["PIZZA PLACE 0006", "NOODLE BAR 0007"], (1, 4), (14, 42)),
    ("Gas", ["FUEL STOP 0001"], (2, 4), (28, 58)),
    ("Shopping", ["BOOKSHOP ONLINE*EX", "HOME GOODS STORE 0003"], (1, 3), (9, 95)),
    ("Entertainment", ["MOVIE THEATER 0004"], (0, 2), (12, 30)),
    ("Health & Wellness", ["PHARMACY EXAMPLE 0005"], (0, 2), (8, 40)),
]
CARD_HEADER = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
CHECKING_HEADER = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"


def _months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def everyday_exports(start: date = date(2024, 11, 1), end: date = date(2026, 10, 31),
                     seed: int = 7) -> tuple[str, str]:
    """Two years of invented card and checking activity as CSV exports, the same every run."""
    rng = random.Random(seed)
    card, checking = [], []
    balance, card_last_month = 6000.00, 0.0
    for y, m in _months(start, end):
        days = calendar.monthrange(y, m)[1]
        spent = 0.0
        for bank_cat, merchants, (lo, hi), (amin, amax) in CARD_HABITS:
            n = rng.randint(lo, hi) + (2 if bank_cat == "Shopping" and m in (11, 12) else 0)   # holiday shopping
            for _ in range(n):
                d = date(y, m, rng.randint(1, days))
                desc = rng.choice(merchants)
                if desc.endswith("*EX"):
                    desc += "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
                amt = round(rng.uniform(amin, amax), 2)
                spent += amt
                card.append((d, d + timedelta(days=1), desc, bank_cat, "Sale", -amt))
        d = date(y, m, 3)
        card.append((d, d + timedelta(days=1), "STREAMING EXAMPLE", "Entertainment", "Sale", -15.49))
        spent += 15.49
        if card_last_month:
            d = date(y, m, 20)
            card.append((d, d, "Payment Thank You-Mobile", "", "Payment", round(card_last_month, 2)))
            checking.append(("DEBIT", d, f"Payment to Example Bank card ending in 2468 {d:%m/%d}", -round(card_last_month, 2),
                             "LOAN_PMT"))
        card_last_month = spent

        power = round(70 + 75 * abs(m - 6.5) / 5.5 * rng.uniform(0.85, 1.15), 2)       # higher in winter
        checking += [
            ("CREDIT", date(y, m, 1), "EXAMPLE EMPLOYER PAYROLL PPD ID: 0000000002", 2500.00, "ACH_CREDIT"),
            ("DEBIT", date(y, m, 1), "EXAMPLE PROPERTY MGMT PPD ID: 0000000003", -1450.00, "ACH_DEBIT"),
            ("DEBIT", date(y, m, 5), "EXAMPLE POWER CO PPD ID: 0000000004", -power, "ACH_DEBIT"),
            ("DEBIT", date(y, m, 10), "EXAMPLE WATER UTILITY PPD ID: 0000000005", -round(rng.uniform(32, 55), 2),
             "ACH_DEBIT"),
            ("DEBIT", date(y, m, 12), "EXAMPLE INTERNET CO PPD ID: 0000000006", -65.00, "ACH_DEBIT"),
            ("CREDIT", date(y, m, 15), "EXAMPLE EMPLOYER PAYROLL PPD ID: 0000000002", 2500.00, "ACH_CREDIT"),
        ]

    card.sort()
    card_csv = CARD_HEADER + "".join(f"{t:%m/%d/%Y},{p:%m/%d/%Y},{desc},{cat},{kind},{amt:.2f},\n"
                                     for t, p, desc, cat, kind, amt in card)
    rows = []
    for details, d, desc, amt, kind in sorted(checking, key=lambda r: r[1]):
        balance = round(balance + amt, 2)
        rows.append(f'{details},{d:%m/%d/%Y},"{desc}",{amt:.2f},{kind},{balance:.2f},,\n')
    return card_csv, CHECKING_HEADER + "".join(reversed(rows))          # the bank lists newest first


# --------------------------------------------------------------------------- two years of net worth

# Invented net worth accounts: (name, asset | debt, group, opening balance, monthly change, monthly noise).
NETWORTH_ACCOUNTS = [
    ("Example Checking", "asset", "Cash", 3200.00, 25.00, 400.00),
    ("Example Savings", "asset", "Cash", 8500.00, 260.00, 40.00),
    ("Example Brokerage", "asset", "Investments", 14200.00, 180.00, 0.035),
    ("Example Retirement", "asset", "Investments", 41800.00, 520.00, 0.03),
    ("Example Car", "asset", "Property", 17600.00, -190.00, 0.0),
    ("Example Car Loan", "debt", "Loans", 12900.00, -330.00, 0.0),
    ("Example Card Balance", "debt", "Cards", 1150.00, 0.0, 450.00),
]


def networth_history(start: date = date(2024, 11, 1), end: date = date(2026, 10, 1), seed: int = 11):
    """Two years of invented month-start balances per account, the same every run. Investment accounts move
    with a random market return (noise is a fraction); cash and cards wander by a dollar amount."""
    rng = random.Random(seed)
    out = []
    for name, kind, group, opening, step, noise in NETWORTH_ACCOUNTS:
        bal, rows = opening, []
        for y, m in _months(start, end):
            rows.append((date(y, m, 1), round(max(bal, 0.0), 2)))
            if noise and noise < 1:
                bal = bal * (1 + rng.gauss(0.006, noise)) + step
            else:
                bal = bal + step + (rng.uniform(-noise, noise) if noise else 0.0)
        out.append((name, kind, group, rows))
    return out


# --------------------------------------------------------------------------- files and database

BANK_ACCOUNTS = [("Example Card", "credit_card", "1234"), ("Checking", "checking", "5678"),
                 ("Everyday Card", "credit_card", "2468"), ("Everyday Checking", "checking", "1357")]
RULES = [  # (match text, category, source, kind, priority)
    ("Groceries", "Groceries", "bank", "spending", 0),
    ("Food & Drink", "Dining", "bank", "spending", 0),
    ("Gas", "Gas", "bank", "spending", 0),
    ("Shopping", "Shopping", "bank", "spending", 0),
    ("Entertainment", "Entertainment", "bank", "spending", 0),
    ("Health & Wellness", "Health", "bank", "spending", 0),
    ("example property mgmt", "Housing", "merchant", "spending", 0),
    ("example power co", "Utilities", "merchant", "spending", 0),
    ("example water utility", "Utilities", "merchant", "spending", 0),
    ("example internet co", "Utilities", "merchant", "spending", 0),
    ("example employer", "Income", "merchant", "income", 10),
    ("payment to example bank card", "Card payments", "merchant", "transfer", 10),
    ("payment thank you", "Card payments", "merchant", "transfer", 10),
]
BUDGETS = {"Housing": 1450, "Groceries": 420, "Dining": 150, "Utilities": 260, "Gas": 130,
           "Shopping": 120, "Entertainment": 50, "Health": 30}
EVERYDAY_FILES = ("ExampleBank2468_Activity20261031.CSV", "ExampleBank1357_Activity20261031.CSV")


def write_files(out: Path) -> None:
    """The sample statements and exports, written under ``out``."""
    statements, exports = out / "statements", out / "exports"
    statements.mkdir(parents=True, exist_ok=True)
    exports.mkdir(parents=True, exist_ok=True)
    write_pdf(sample_text.CARD, statements / "20260104-statements-1234-.pdf")
    write_pdf(sample_text.CHECKING, statements / "20260116-statements-5678-.pdf")
    write_pdf(sample_text.CARD.replace("121.20", "112.20").replace("12/05/25 - 01/04/26", "01/05/26 - 02/04/26"),
              statements / "20260204-statements-1234-.pdf")
    (exports / "ExampleBank1234_Activity20260228.CSV").write_text(sample_text.CARD_CSV)
    (exports / "ExampleBank5678_Activity20260228.CSV").write_text(sample_text.CHECKING_CSV.lstrip("﻿"))
    for name, text in zip(EVERYDAY_FILES, everyday_exports()):
        (exports / name).write_text(text)


def seed(conn: sqlite3.Connection, out: Path) -> None:
    """Write the sample files under ``out``, then add whatever sample data the database is missing: bank
    accounts (by last four digits), rules, budgets, the two years of everyday spending, and net worth accounts
    with their history. Running it again adds nothing; it never changes what's already there. The sample PDF
    statements are left for you to scan and import."""
    write_files(out)
    ids = {a["last4"]: a["id"] for a in store.bank_accounts(conn)}
    for name, type_, last4 in BANK_ACCOUNTS:
        if last4 not in ids:
            ids[last4] = store.add_bank_account(conn, name, type_, last4)
    have_rules = {tuple(r) for r in conn.execute("SELECT source, match_text FROM category_rules")}
    for text, cat, source, kind, prio in RULES:
        if (source, text) not in have_rules:
            store.add_rule(conn, text, cat, source=source, kind=kind, priority=prio)
    have_budgets = budget.budgets(conn)
    for cat, amount in BUDGETS.items():
        if cat not in have_budgets:
            budget.set_budget(conn, cat, amount)
    for name in EVERYDAY_FILES:
        store.import_transactions(conn, ids[last4_from_filename(name)], parse_csv(out / "exports" / name), name)
    have_nw = {a.name for a in networth.accounts(conn)}
    for name, kind, group, rows in networth_history():
        if name not in have_nw:
            acct = networth.add_account(conn, name, kind, group)
            for as_of, balance in rows:
                networth.set_balance(conn, acct, as_of, balance)


if __name__ == "__main__":
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "samples")
    write_files(folder)
    print(f"Wrote samples to {folder / 'statements'} and {folder / 'exports'}")
