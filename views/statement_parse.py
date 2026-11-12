"""Statement Parse: scan or upload statements, import them, review uncategorized merchants, undo imports."""
from pathlib import Path

import streamlit as st

import webui
from stmtrecon import store
from stmtrecon.csv_import import parse_csv
from stmtrecon.models import ACCOUNT_TYPES
from stmtrecon.pdf_statements import pdf_text
from stmtrecon.scan import State, import_found, scan

conn = webui.conn()
BADGES = {State.READY: ":green-badge[:material/check_circle: Ready]",
          State.IMPORTED: ":gray-badge[:material/done_all: Already imported]",
          State.BLOCKED: ":orange-badge[:material/block: Can't import]"}


@st.cache_data(show_spinner=False, max_entries=200)
def _pdf_text(path: str, modified: int, size: int) -> str:
    return pdf_text(Path(path))


def read_pdf(path: Path) -> str:
    """PDF text, extracted once per file version instead of on every click."""
    info = path.stat()
    return _pdf_text(str(path), info.st_mtime_ns, info.st_size)


def statements_section() -> None:
    st.subheader("PDF statements")
    st.caption("A statement is imported only if its rows add up to its own printed totals, to the cent.")
    uploaded = st.file_uploader("Upload PDF statements", type="pdf", accept_multiple_files=True)
    for f in uploaded or []:
        webui.save_upload(f.name, f.getvalue())
    default = webui.UPLOADS if uploaded else webui.SAMPLES / "statements"
    folder = webui.scan_folder(st.text_input("Folder to scan", str(default.relative_to(webui.ROOT)),
                                             help="Relative to the project folder, or a full path"))
    if folder is None:
        st.error("Only folders inside the project can be scanned when the app is reachable from other computers.")

    found = scan(conn, folder, read=read_pdf) if folder else []
    if folder and not found:
        st.info("No PDFs here yet. Click **Load sample data** in the sidebar, or upload statements.")
    for f in found:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            detail = (f"{f.new_rows} new of {webui.plural(len(f.statement.parsed.rows), 'row')}" if f.ready
                      else webui.md(f.reason))
            c1.markdown(f"**{webui.md(f.path.name)}**  \n{BADGES[f.state]} {detail}")
            if f.statement and f.statement.parsed.period:
                lo, hi = f.statement.parsed.period
                c2.caption(f"{f.statement.parsed.format.label}  \n{lo:%b %d, %Y} – {hi:%b %d, %Y}")
            for p in f.statement.problems if f.statement else []:
                st.error(webui.md(p))
            if f.statement and f.statement.parsed.rows:
                with st.expander(f"Parsed rows ({len(f.statement.parsed.rows)})"):
                    st.dataframe([{"date": r.posted_date, "description": r.description, "amount": r.amount,
                                   "type": r.bank_type} for r in f.statement.parsed.rows],
                                 hide_index=True, width="stretch")
    ready = [f for f in found if f.ready]
    if ready and st.button(f"Import {webui.plural(len(ready), 'ready statement')}", type="primary"):
        for f in ready:
            import_found(conn, f)
        st.rerun()


def csv_section() -> None:
    st.subheader("CSV exports")
    accts = store.bank_accounts(conn)
    if not accts:
        st.caption("Add an account on the **Accounts** tab first.")
        return
    csv_file = st.file_uploader("Upload a CSV export", type="csv")
    acct = st.selectbox("Into account", accts, format_func=lambda a: f"{a['name']} (ending {a['last4']})")
    if csv_file and st.button("Import CSV"):
        try:
            r = store.import_transactions(conn, acct["id"], parse_csv(csv_file.getvalue()), csv_file.name)
            st.success(f"{r.added} added, {r.skipped} already stored")
        except ValueError as e:
            st.error(webui.md(e))


def transactions_section() -> None:
    rows = [{**r, "category": r["category"] or "", "why": r["why"] or "needs review"}
            for r in store.transactions(conn)]
    if not rows:
        st.info("No transactions yet. Import a statement or CSV first.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Transactions", f"{len(rows):,}", border=True)
    c2.metric("Accounts", len({r["account"] for r in rows}), border=True)
    c3.metric("Need review", sum(1 for r in rows if not r["category"]), border=True)
    st.dataframe(rows, hide_index=True, width="stretch",
                 column_config={"date": "Date", "account": "Account", "description": "Description",
                                "amount": st.column_config.NumberColumn("Amount", format="dollar"),
                                "category": "Category", "why": "Categorized by", "source": "Source file"})


def review_section() -> None:
    st.caption("Transactions no rule matched. Pick a category to save a rule for that merchant; it applies to "
               "every matching transaction now and on future imports.")
    pending = store.pending_merchants(conn)
    if not pending:
        st.success("Nothing to review.")
    cats = store.category_names(conn)
    for i, p in enumerate(pending):
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 1], vertical_alignment="center")
            total = webui.money(p["total"], cents=True)
            c1.markdown(f"**{webui.md(p['merchant']) if p['merchant'] else '(no merchant)'}**  \n"
                        f"{webui.plural(p['n'], 'transaction')} · {total}")
            choice = c2.selectbox("Category", [*cats, "New category..."], index=None, key=f"cat{i}",
                                  placeholder="Pick a category", label_visibility="collapsed")
            if choice == "New category...":
                choice = c2.text_input("New category", key=f"new{i}", label_visibility="collapsed",
                                       placeholder="New category name")
            if c3.button("Save rule", key=f"save{i}", disabled=not choice or not p["merchant"], width="stretch"):
                store.add_rule(conn, p["merchant"], choice)
                st.rerun()


def imports_section() -> None:
    imports = store.imports(conn)
    if not imports:
        st.info("No imports yet.")
    for imp in imports:
        with st.container(border=True):
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            c1.markdown(f"**{webui.md(imp['filename'])}** → {webui.md(imp['account'])}  \n"
                        f"{imp['date_from']} to {imp['date_to']} · {imp['rows_added']} added, "
                        f"{imp['rows_skipped']} already stored · {imp['created_at']}")
            if c2.button("Undo", key=f"undo{imp['id']}", icon=":material/undo:", width="stretch"):
                store.undo_import(conn, imp["id"])
                st.rerun()


def accounts_section() -> None:
    st.caption("Bank accounts that statements and exports import into. Statements are matched to an account by "
               "the last four digits of its number.")
    rows = store.bank_accounts(conn)
    if rows:
        st.dataframe([{"name": a["name"], "type": ACCOUNT_TYPES[a["type"]], "ending": a["last4"]} for a in rows],
                     hide_index=True, width="stretch")
    with st.form("acct", clear_on_submit=True):
        st.markdown("**Add an account**")
        c1, c2, c3 = st.columns([3, 2, 1])
        name = c1.text_input("Name")
        kind = c2.selectbox("Type", list(ACCOUNT_TYPES), format_func=ACCOUNT_TYPES.get)
        last4 = c3.text_input("Last 4 digits", max_chars=4)
        if st.form_submit_button("Add") and name and len(last4) == 4 and last4.isdigit():
            store.add_bank_account(conn, name, kind, last4)
            st.rerun()


st.title("Statement Parse")
t1, t2, t3, t4, t5 = st.tabs(["Statements", "Transactions", "Review", "Imports", "Accounts"])
with t1:
    statements_section()
    csv_section()
with t2:
    transactions_section()
with t3:
    review_section()
with t4:
    imports_section()
with t5:
    accounts_section()
