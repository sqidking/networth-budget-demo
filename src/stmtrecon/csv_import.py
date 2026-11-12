"""Parse bank transaction CSV exports (checking and credit card layouts)."""
from __future__ import annotations

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .models import BankFormat, ParsedFile, ParsedTxn
from .text import clean


@dataclass(frozen=True)
class CsvFormat(BankFormat):
    header: tuple[str, ...]
    parse_row: Callable[[dict[str, str]], ParsedTxn]


def _date(s: str) -> date:
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unrecognized date {s!r}")


def _amount(s: str) -> float:
    s = s.strip().replace("$", "").replace(",", "")
    if s.startswith("(") and s.endswith(")"):        # accounting-style negatives
        s = "-" + s[1:-1]
    return round(float(s), 2)


def _example_card(r: dict[str, str]) -> ParsedTxn:
    return ParsedTxn(posted_date=_date(r["post date"]), txn_date=_date(r["transaction date"]),
                     description=clean(r["description"]), amount=_amount(r["amount"]),
                     bank_category=clean(r["category"]), bank_type=clean(r["type"]), memo=clean(r.get("memo")))


def _example_checking(r: dict[str, str]) -> ParsedTxn:
    return ParsedTxn(posted_date=_date(r["posting date"]), description=clean(r["description"]),
                     amount=_amount(r["amount"]), bank_type=clean(r["type"]),
                     memo=clean(r.get("check or slip #")))


FORMATS: list[CsvFormat] = [
    CsvFormat("example_card", "Example Bank credit card", "credit_card",
              ("transaction date", "post date", "description", "category", "type", "amount", "memo"), _example_card),
    CsvFormat("example_checking", "Example Bank checking / savings", "checking",
              ("details", "posting date", "description", "amount", "type", "balance", "check or slip #"),
              _example_checking),
]


def detect_format(header: list[str]) -> CsvFormat:
    cols = tuple(h.strip().lower() for h in header if h.strip())
    for f in FORMATS:
        if cols == f.header:
            return f
    known = "; ".join(f"{f.label}: {', '.join(f.header)}" for f in FORMATS)
    raise ValueError(f"Unrecognized CSV columns ({', '.join(cols) or 'none'}). Supported formats: {known}.")


def parse_csv(source: bytes | str | Path) -> ParsedFile:
    if isinstance(source, Path):
        source = source.read_bytes()
    body = source.decode("utf-8-sig") if isinstance(source, bytes) else source.lstrip("﻿")
    reader = csv.reader(io.StringIO(body))
    header = next(reader, None)
    if header is None:
        raise ValueError("The file is empty.")
    fmt = detect_format(header)
    out = ParsedFile(fmt)
    width = len(fmt.header)
    for line_no, cells in enumerate(reader, start=2):
        # Checking rows end with a trailing comma (one more field than the header).
        while len(cells) > width and not cells[-1].strip():
            cells = cells[:-1]
        if not any(c.strip() for c in cells):
            continue
        if len(cells) != width:
            raise ValueError(f"Line {line_no}: expected {width} columns, found {len(cells)}.")
        try:
            out.rows.append(fmt.parse_row(dict(zip(fmt.header, cells))))
        except (ValueError, KeyError) as e:
            raise ValueError(f"Line {line_no}: {e}") from None
    return out
