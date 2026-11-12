from stmtrecon import budget, samples, store

TABLES = ("bank_accounts", "category_rules", "budgets", "transactions", "nw_accounts", "nw_balances")


def _counts(conn):
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}


def test_seed_fills_in_around_existing_data_and_repeats_safely(tmp_path):
    conn = store.connect()
    store.add_bank_account(conn, "My Card", "credit_card", "9999")      # the user's own account comes first
    store.add_rule(conn, "my diner", "Dining")
    budget.set_budget(conn, "Dining", 999)
    samples.seed(conn, tmp_path)
    first = _counts(conn)
    assert first["bank_accounts"] == 5 and first["transactions"] > 500 and first["nw_accounts"] == 7
    assert conn.execute("SELECT b.monthly FROM budgets b JOIN categories c ON c.id = b.category_id "
                        "WHERE c.name = 'Dining'").fetchone()[0] == 999          # never overwritten
    assert len(list((tmp_path / "statements").glob("*.pdf"))) == 3
    samples.seed(conn, tmp_path)
    assert _counts(conn) == first
