"""Text cleanup shared by every source: statement and export descriptions, merchant names, file names."""
from __future__ import annotations

import re


def clean(s: str | None) -> str:
    """Whitespace collapsed to single spaces."""
    return " ".join((s or "").split())


def normalize(s: str | None) -> str:
    """Upper case, letters and digits (and ``&'``) only. Rule text and merchant names share this shape."""
    return " ".join(re.sub(r"[^A-Z0-9&' ]+", " ", (s or "").upper()).split())


def merchant_name(description: str) -> str:
    """Description cleaned for matching: no store numbers, card digits, dates or reference IDs."""
    s = description.upper()
    s = re.sub(r"^(POS |DEBIT CARD |ACH )?(PURCHASE|DEBIT|CREDIT)\s+", "", s)
    s = re.sub(r"\b\d{2}/\d{2}(/\d{2,4})?\b", " ", s)           # dates
    s = re.sub(r"#\s*\w+", " ", s)                               # store / reference numbers
    s = re.sub(r"\b(PPD|WEB|CCD|TEL) ID:?\s*\S+", " ", s)         # ACH company IDs
    s = re.sub(r"\b\w*\d{4,}\w*\b", " ", s)                     # long digit runs (card, account, txn IDs)
    return normalize(s)


def last4_from_filename(name: str) -> str | None:
    """The bank names downloads like ``ExampleBank1234_Activity20260128.CSV`` and statements like
    ``20260104-statements-1234-.pdf``."""
    m = re.search(r"examplebank(\d{4})|statements-(\d{4})\b", name, re.IGNORECASE)
    return (m.group(1) or m.group(2)) if m else None
