"""End to end through an actual PDF file: generate one, extract its text with pdfplumber, parse and reconcile."""
import pytest

from stmtrecon import store
from stmtrecon.pdf_statements import parse_statement, pdf_text
from stmtrecon.sample_text import CARD, CHECKING
from stmtrecon.samples import write_pdf
from stmtrecon.scan import import_found, scan


@pytest.mark.parametrize("text, rows", [(CARD, 8), (CHECKING, 7)])
def test_generated_pdf_round_trips(tmp_path, text, rows):
    path = tmp_path / "s.pdf"
    write_pdf(text, path)
    st = parse_statement(pdf_text(path))
    assert st.ok, st.problems
    assert len(st.parsed.rows) == rows


def test_scan_generated_pdfs(tmp_path):
    conn = store.connect()
    store.add_bank_account(conn, "Example Card", "credit_card", "1234")
    write_pdf(CARD, tmp_path / "20260104-statements-1234-.pdf")
    write_pdf(CARD.replace("121.20", "112.20"), tmp_path / "20260204-statements-1234-.pdf")
    found = scan(conn, tmp_path)
    assert [f.status for f in found] == ["Doesn't add up", "Ready"]
    assert import_found(conn, found[1]).added == 8
