"""Parse bank PDF statements (checking and credit card) and reconcile them against their own totals.

A statement is only accepted when its rows add up to the statement's printed totals, to the cent: card
statements from previous balance to new balance, checking from beginning to ending balance, and each section
to its subtotal. Anything that doesn't add up is reported with the section and the size of the difference,
so a parsing gap can never silently drop or invent a transaction.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .models import BankFormat, ParsedFile, ParsedTxn
from .text import clean

CARD = BankFormat("example_card_pdf", "Example Bank credit card statement", "credit_card")
CHECKING = BankFormat("example_checking_pdf", "Example Bank checking statement", "checking")

# Card activity sections -> the account summary line they add up to, and the CSV-style type their rows get.
CARD_SECTIONS = {
    "PAYMENTS AND OTHER CREDITS": ("Payment, Credits", "Return"),
    "RETURNS AND OTHER CREDITS": ("Payment, Credits", "Return"),
    "PURCHASE": ("Purchases", "Sale"),
    "PURCHASES": ("Purchases", "Sale"),
    "CASH ADVANCE": ("Cash Advances", "Sale"),
    "CASH ADVANCES": ("Cash Advances", "Sale"),
    "BALANCE TRANSFER": ("Balance Transfers", "Sale"),
    "BALANCE TRANSFERS": ("Balance Transfers", "Sale"),
    "FEES CHARGED": ("Fees Charged", "Fee"),
    "INTEREST CHARGED": ("Interest Charged", "Fee"),
}
# Checking sections -> sign of their rows and a CSV-style type.
CHECKING_SECTIONS = {
    "DEPOSITS AND ADDITIONS": (1, "ACH_CREDIT"),
    "CHECKS PAID": (-1, "CHECK_PAID"),
    "ATM & DEBIT CARD WITHDRAWALS": (-1, "DEBIT_CARD"),
    "ELECTRONIC WITHDRAWALS": (-1, "ACH_DEBIT"),
    "OTHER WITHDRAWALS": (-1, "ACH_DEBIT"),
    "FEES": (-1, "FEE_TRANSACTION"),
}

_AMOUNT = r"[-+]?\$?-?[\d,]*\.\d{2}"            # statements print 99 cents as ".99"
_ROW = re.compile(rf"^(\d{{2}})/(\d{{2}})\s+(.*\S)\s+({_AMOUNT})$")
_CHECK_ROW = re.compile(rf"^(\d+)\s*\^?\s*(.*?)\s*(\d{{2}})/(\d{{2}})\s+({_AMOUNT})$")
# A summary line can run into the text column beside it ("Previous Balance $57.22 Cardmembers earn...").
_SUMMARY = re.compile(rf"^([A-Za-z][A-Za-z&,' ]*?)\s+({_AMOUNT})(?:\s|$)")


# --------------------------------------------------------------------------- reading

def _visible(obj: dict) -> bool:
    """Checking statements carry tiny white marker text (``*start*summary``) that would break up lines."""
    c = obj.get("non_stroking_color")
    return not (obj.get("object_type") == "char" and isinstance(c, (tuple, list)) and c and all(v == 1 for v in c))


def pdf_text(source: bytes | Path) -> str:
    import pdfplumber

    with pdfplumber.open(source if isinstance(source, Path) else io.BytesIO(source)) as pdf:
        return "\n".join(page.filter(_visible).extract_text() or "" for page in pdf.pages)


def _plain(line: str) -> str:
    """Bold headings come out of pdfplumber with every letter doubled (``AACCCCOOUUNNTT``)."""
    words = [w[::2] if len(w) % 2 == 0 and len(w) > 1 and w[::2] == w[1::2] else w for w in line.split()]
    return " ".join(words)


def _cents(s: str) -> int:
    """An amount as whole cents, so totals add up exactly. ``_AMOUNT`` always has two decimals."""
    v = int(re.sub(r"\D", "", s))
    return -v if "-" in s else v


def _in_period(month: int, day: int, end: date) -> date:
    """A statement's MM/DD in the right year: after the closing day's month and day means the year before."""
    year = end.year if (month, day) <= (end.month, end.day) else end.year - 1
    return date(year, month, day)


# --------------------------------------------------------------------------- parsing

@dataclass
class Statement:
    parsed: ParsedFile
    last4: str | None = None
    problems: list[str] = field(default_factory=list)   # empty when it adds up

    @property
    def ok(self) -> bool:
        return not self.problems


def _reconcile(problems: list[str], label: str, rows: int, says: int) -> None:
    """Note it when the rows (in cents) don't add up to what the statement says."""
    if rows != says:
        problems.append(f"{label}: rows add up to ${rows / 100:,.2f}, statement says ${says / 100:,.2f} "
                        f"(off by ${abs(rows - says) / 100:,.2f})")


def _summary(lines: list[str], first: str, last: str) -> tuple[int, int, dict[str, int]]:
    """Opening balance, closing balance and the lines between them (in cents), from an account summary block."""
    opening = closing = None
    items: dict[str, int] = {}
    for line in lines:
        m = _SUMMARY.match(line.strip())
        if not m:
            continue
        label, amt = m.group(1).strip(), _cents(m.group(2))
        if label == first and opening is None:
            opening = amt
        elif label == last and opening is not None:
            closing = amt
            break
        elif opening is not None:
            items[label] = items.get(label, 0) + amt
    if opening is None or closing is None:
        raise ValueError(f"No account summary ({first} ... {last}) found.")
    return opening, closing, items


def parse_card(raw: str) -> Statement:
    lines = [_plain(line).strip() for line in raw.splitlines()]
    m = re.search(r"Opening/Closing Date\s+(\d{2}/\d{2}/\d{2})\s*-\s*(\d{2}/\d{2}/\d{2})", raw)
    if not m:
        raise ValueError("No opening/closing date found.")
    start, end = (datetime.strptime(x, "%m/%d/%y").date() for x in m.groups())
    previous, new, items = _summary(lines, "Previous Balance", "New Balance")
    acct = re.search(r"Account Number:\s*(?:X+\s*)+(\d{4})", raw)
    out = Statement(ParsedFile(CARD, period=(start, end)), acct.group(1) if acct else None)

    # Statement signs: purchases +, payments and credits -. Stored rows use negative = money out.
    totals: dict[str, int] = {}
    section, active = None, False
    for line in lines:
        if line == "ACCOUNT ACTIVITY":
            active = True
            continue
        if not active:
            continue
        if line.endswith("Totals Year-to-Date") or line in ("INTEREST CHARGES", "SHOP WITH POINTS ACTIVITY"):
            break
        if line in CARD_SECTIONS:
            section = line
            continue
        row = _ROW.match(line)
        if row and section:
            mm, dd, desc, amt = row.groups()
            desc = re.sub(r"^&\s*", "", desc)        # some statements mark rows with a leading "&"
            amount = _cents(amt)
            label, kind = CARD_SECTIONS[section]
            if kind == "Return" and desc.upper().startswith(("PAYMENT", "AUTOMATIC PAYMENT")):
                kind = "Payment"
            d = _in_period(int(mm), int(dd), end)
            out.parsed.rows.append(ParsedTxn(posted_date=d, txn_date=d, description=clean(desc),
                                             amount=-amount / 100, bank_type=kind))
            totals[label] = totals.get(label, 0) + amount
        elif line.startswith("Order Number") and out.parsed.rows:
            out.parsed.rows[-1].memo = clean(line)

    _reconcile(out.problems, "Account summary", previous + sum(items.values()), new)
    for label in sorted(set(items) | set(totals)):
        _reconcile(out.problems, label, totals.get(label, 0), items.get(label, 0))
    return out


def parse_checking(raw: str) -> Statement:
    lines = [_plain(line).strip() for line in raw.splitlines()]
    m = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})\s*through\s*([A-Z][a-z]+ \d{1,2}, \d{4})", raw)
    if not m:
        raise ValueError("No statement period found.")
    start, end = (datetime.strptime(x, "%B %d, %Y").date() for x in m.groups())
    beginning, ending, items = _summary(lines, "Beginning Balance", "Ending Balance")
    out = Statement(ParsedFile(CHECKING, period=(start, end)))

    sums: dict[str, int] = {}
    net = 0
    section = None
    for line in lines:
        if line in CHECKING_SECTIONS:
            section = line
            continue
        if section is None:
            continue
        if line.startswith(("Total", "TOTAL")):
            m = re.search(rf"({_AMOUNT})$", line)
            if m:
                _reconcile(out.problems, section.title(), sums.get(section, 0), _cents(m.group(1)))
            section = None
            continue
        sign, kind = CHECKING_SECTIONS[section]
        memo = ""
        if section == "CHECKS PAID":
            row = _CHECK_ROW.match(line)
            if not row:
                continue
            no, desc, mm, dd, amt = row.groups()
            desc, memo = f"CHECK {no}" + (f" {desc}" if desc else ""), no
        else:
            row = _ROW.match(line)
            if not row:
                continue
            mm, dd, desc, amt = row.groups()
            if "ONLINE TRANSFER" in desc.upper():
                kind = "ACCT_XFER"
        amount = sign * abs(_cents(amt))
        out.parsed.rows.append(ParsedTxn(posted_date=_in_period(int(mm), int(dd), end), description=clean(desc),
                                         amount=amount / 100, bank_type=kind, memo=memo))
        sums[section] = sums.get(section, 0) + abs(amount)
        net += amount

    _reconcile(out.problems, "Account summary", beginning + sum(items.values()), ending)
    _reconcile(out.problems, "All rows", net, ending - beginning)
    return out


def parse_statement(raw: str) -> Statement:
    if "CHECKING SUMMARY" in _plain(raw):
        return parse_checking(raw)
    if "Opening/Closing Date" in raw:          # a month with no activity has no ACCOUNT ACTIVITY section
        return parse_card(raw)
    raise ValueError("Not a recognized checking or credit card statement.")
