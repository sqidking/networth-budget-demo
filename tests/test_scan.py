import pytest

from stmtrecon import store
from stmtrecon.csv_import import parse_csv
from stmtrecon.sample_text import CARD, CARD_STATEMENT_CSV, CHECKING
from stmtrecon.scan import State, import_found, scan


@pytest.fixture
def conn():
    c = store.connect()
    yield c
    c.close()


@pytest.fixture
def accts(conn):
    return (store.add_bank_account(conn, "Example Card", "credit_card", "1234"),
            store.add_bank_account(conn, "Checking", "checking", "5678"))


def _folder(path, files):
    """Statement 'PDFs' holding plain text; the scan is given a reader that just reads it back."""
    for name, text in files.items():
        (path / name).write_text(text)
    return path


def _read(path):
    return path.read_text()


def _import_all(conn, folder):
    return [import_found(conn, f) for f in scan(conn, folder, read=_read) if f.ready]


def _count(conn):
    return conn.execute("SELECT count(*) FROM transactions").fetchone()[0]


def test_scan_imports_once_per_file(conn, accts, tmp_path):
    card, chk = accts
    folder = _folder(tmp_path, {"20260104-statements-1234-.pdf": CARD, "20260116-statements-5678-.pdf": CHECKING})
    found = scan(conn, folder, read=_read)
    assert [(f.status, f.bank_account_id, f.new_rows) for f in found] == [("Ready", chk, 7), ("Ready", card, 8)]
    assert [r.added for r in _import_all(conn, folder)] == [7, 8]
    again = scan(conn, folder, read=lambda p: pytest.fail("re-read"))
    assert {(f.state, f.status) for f in again} == {(State.IMPORTED, "Already imported")}
    imp = conn.execute("SELECT format, date_from, date_to FROM imports "
                       "WHERE filename = '20260104-statements-1234-.pdf'").fetchone()
    assert tuple(imp) == ("example_card_pdf", "2025-12-05", "2026-01-04")


def test_scan_finds_uppercase_pdf_extension(conn, accts, tmp_path):
    folder = _folder(tmp_path, {"20260104-statements-1234-.PDF": CARD, "notes.txt": "not a statement"})
    assert [(f.path.name, f.status) for f in scan(conn, folder, read=_read)] == [
        ("20260104-statements-1234-.PDF", "Ready")]


def test_database_file_is_private(tmp_path):
    db = tmp_path / "t.db"
    store.connect(str(db)).close()
    assert db.stat().st_mode & 0o777 == 0o600
    db.chmod(0o644)                                  # an older, readable database is tightened on open
    store.connect(str(db)).close()
    assert db.stat().st_mode & 0o777 == 0o600


def test_scan_reports_what_blocks_a_file(conn, accts, tmp_path):
    folder = _folder(tmp_path, {"a-statements-1234-.pdf": CARD.replace("121.20", "112.20"),
                                "b-statements-0000-.pdf": CARD, "c-statements-5678-.pdf": CARD,
                                "d-statements-1234-.pdf": "garbage"})
    status = {f.path.name[0]: f.status for f in scan(conn, folder, read=_read)}
    assert status == {"a": "Doesn't add up", "b": "No bank account ending in 0000",
                      "c": "Account ending in 5678 isn't a credit card",
                      "d": "Can't read: Not a recognized checking or credit card statement."}
    with pytest.raises(ValueError):
        import_found(conn, scan(conn, folder, read=_read)[0])
    assert _count(conn) == 0


def test_statement_with_nothing_new_is_still_recorded(conn, accts, tmp_path):
    _import_all(conn, _folder(tmp_path, {"s-statements-1234-.pdf": CARD}))
    (tmp_path / "again").mkdir()
    copy = _folder(tmp_path / "again", {"s-statements-1234-.pdf": CARD + "\n"})   # a different file, same rows
    (r,) = _import_all(conn, copy)
    assert (r.added, r.skipped) == (0, 8) and r.import_id is not None
    assert scan(conn, copy, read=_read)[0].status == "Already imported"


def test_csv_then_statement_adds_nothing_twice(conn, accts, tmp_path):
    card, _ = accts
    assert store.import_transactions(conn, card, parse_csv(CARD_STATEMENT_CSV), "x.csv").added == 4
    (r,) = _import_all(conn, _folder(tmp_path, {"s-statements-1234-.pdf": CARD}))
    assert (r.added, r.skipped) == (5, 3)             # the groceries and both coffees were already in
    assert _count(conn) == 9


def test_statement_then_csv_adds_only_rows_after_it(conn, accts, tmp_path):
    card, _ = accts
    _import_all(conn, _folder(tmp_path, {"s-statements-1234-.pdf": CARD}))
    r = store.import_transactions(conn, card, parse_csv(CARD_STATEMENT_CSV), "x.csv")
    assert (r.added, r.skipped) == (1, 3)             # only the fuel purchase is new
