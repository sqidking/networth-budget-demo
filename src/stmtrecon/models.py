"""The shapes every importer produces, whatever the source (PDF statement or CSV export)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

ACCOUNT_TYPES = {"checking": "checking", "credit_card": "credit card"}     # stored value -> how it reads


@dataclass
class ParsedTxn:
    posted_date: date
    description: str
    amount: float                      # negative = money out
    txn_date: date | None = None
    bank_category: str = ""
    bank_type: str = ""
    memo: str = ""

    @property
    def match_date(self) -> date:
        """The date duplicates are matched on: card statements give only the purchase date."""
        return self.txn_date or self.posted_date


@dataclass(frozen=True)
class BankFormat:
    key: str
    label: str
    account_type: str                  # a key of ACCOUNT_TYPES


@dataclass
class ParsedFile:
    format: BankFormat
    rows: list[ParsedTxn] = field(default_factory=list)
    period: tuple[date, date] | None = None   # a statement's own dates, which can include days with no rows

    @property
    def date_range(self) -> tuple[date, date] | None:
        if not self.rows:
            return None
        ds = [r.posted_date for r in self.rows]
        return min(ds), max(ds)
