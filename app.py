"""Local web interface: ``uv run streamlit run app.py``.

Pages (left sidebar): Statement Parse, Budgets, Monthly spending, Yearly spending, Net worth. Uses demo.db
next to this file (git-ignored).
"""
from __future__ import annotations

import streamlit as st

import webui
from stmtrecon import samples

st.set_page_config(page_title="Net Worth & Budget Tracking Demo", page_icon=":material/account_balance_wallet:",
                   layout="wide")
conn = webui.connect()
webui.page_style()

page = st.navigation([
    st.Page("views/statement_parse.py", title="Statement Parse", icon=":material/receipt_long:", default=True),
    st.Page("views/budgets.py", title="Budgets", icon=":material/savings:"),
    st.Page("views/monthly_spending.py", title="Monthly spending", icon=":material/calendar_month:"),
    st.Page("views/yearly_spending.py", title="Yearly spending", icon=":material/bar_chart:"),
    st.Page("views/net_worth.py", title="Net worth", icon=":material/account_balance:"),
])

with st.sidebar:
    st.markdown("**Net Worth & Budget Tracking Demo**")
    st.caption("Bank statements and exports in, verified records, budgets and net worth out. Everything runs "
               "locally.")
    if st.button("Load sample data", type="primary", width="stretch"):
        samples.seed(conn, webui.SAMPLES)
        st.rerun()
    with st.popover("Reset demo", width="stretch"):
        st.caption(f"Deletes **{webui.md(webui.DB.name)}** and every uploaded statement. This can't be undone.")
        if st.button("Delete everything", type="primary", width="stretch"):
            webui.reset(conn)
            st.rerun()

page.run()
