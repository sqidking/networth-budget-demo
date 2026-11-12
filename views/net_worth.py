"""Net worth: assets and debts with a balance per month."""
from datetime import date

import pandas as pd
import streamlit as st

import webui
from stmtrecon import budget, charts, networth

conn, P = webui.conn(), webui.palette()
money = webui.money

st.title("Net worth")
nw = networth.load(conn)

if nw.empty:
    st.info("No balances yet. Click **Load sample data** in the sidebar, or add accounts below and record a "
            "balance for each.")
else:
    tot = nw.totals
    now, prev, year_ago = nw.ago(0), nw.ago(1), nw.ago(12)

    st.caption(f"As of {now.name:%B %Y}. Months without a new balance carry the last one forward.")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Net worth", money(now["Net worth"]), border=True, height="stretch",
              delta=money(now["Net worth"] - prev["Net worth"]) + " this month" if prev is not None else None)
    k2.metric("Assets", money(now["Assets"]), border=True, height="stretch")
    k3.metric("Debts", money(now["Debts"]), border=True, height="stretch",
              delta=money(now["Debts"] - prev["Debts"]) if prev is not None else None, delta_color="inverse")
    k4.metric("Past 12 months", money(now["Net worth"] - year_ago["Net worth"]) if year_ago is not None else "–",
              border=True, height="stretch",
              delta=f"{now['Net worth'] / year_ago['Net worth'] - 1:+.1%}"
              if year_ago is not None and year_ago["Net worth"] > 0 else None)

    with st.container(border=True):
        st.markdown("**Net worth over time**")
        st.plotly_chart(charts.net_worth(tot, P), config=webui.CHART, theme=None)

    debts = nw.latest("debt")
    c1, c2 = st.columns([1, 1])
    with c1, st.container(border=True, height="stretch"):
        st.markdown("**Where your assets are**")
        st.plotly_chart(charts.donut(budget.fold(nw.assets_by_group()), charts.colors(nw.asset_groups, P), P,
                                     money(nw.latest("asset").sum())), config=webui.CHART, theme=None)
    with c2, st.container(border=True, height="stretch"):
        st.markdown("**What you owe**")
        with st.container(height="stretch", vertical_alignment="center"):   # level with the donut beside it
            if debts.sum() > 0:
                st.plotly_chart(charts.ranked_bars(debts[debts > 0], P.series[6], P), config=webui.CHART,
                                theme=None)
            else:
                st.success("No debts.")

    shown = nw.balances.iloc[::-1]
    months = [f"{m:%b %Y}" for m in shown.index]
    webui.table_view(pd.concat([tot.iloc[::-1], shown], axis=1).set_axis(months)
                     .map(lambda v: "" if pd.isna(v) else money(v)), "Show balances by month")

st.subheader("Update balances")
if nw.accounts:
    last = nw.balances.index[-1] if not nw.empty else pd.Timestamp(date.today().replace(day=1))
    options = [last + pd.offsets.MonthBegin(1), *[last - pd.offsets.MonthBegin(i) for i in range(12)]]
    month = st.selectbox("Month", options, index=0, format_func=lambda m: f"{m:%B %Y}", width=240)
    stored, carried = networth.recorded(conn, month.date()), nw.at(month)
    grid = pd.DataFrame({
        "Account": [a.name for a in nw.accounts],
        "Type": [a.kind.title() for a in nw.accounts],
        "Balance": [stored.get(a.name, carried.get(a.name, float("nan"))) for a in nw.accounts]})
    st.caption("Balances shown for a month without its own entries are carried from the month before; saving "
               "records them for this month. Enter debts as the amount owed.")
    edited = st.data_editor(grid, hide_index=True, width="stretch", disabled=["Account", "Type"],
                            key=f"nw_{month:%Y%m}",
                            column_config={"Balance": st.column_config.NumberColumn(format="dollar", min_value=0)})
    if st.button(f"Save {month:%B %Y} balances", type="primary"):
        for a, bal in zip(nw.accounts, edited["Balance"]):
            networth.set_balance(conn, a.id, month.date(), None if pd.isna(bal) else float(bal))
        st.rerun()

with st.expander("Add an account"), st.form("nw_acct", clear_on_submit=True):
    c1, c2, c3 = st.columns([3, 1, 2])
    name = c1.text_input("Name")
    kind = c2.selectbox("Type", ["asset", "debt"], format_func=str.title)
    group = c3.text_input("Group", placeholder="Cash, Investments, Loans...")
    if st.form_submit_button("Add") and name.strip():
        if any(a.name == name.strip() for a in nw.accounts):
            st.error("An account with that name already exists.")
        else:
            networth.add_account(conn, name.strip(), kind, group.strip())
            st.rerun()
