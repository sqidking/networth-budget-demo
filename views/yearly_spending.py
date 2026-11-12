"""Yearly spending: a year by month and category, against budgets."""
import streamlit as st

import webui
from stmtrecon import budget, charts

conn, P = webui.conn(), webui.palette()
money = webui.money

st.title("Yearly spending")
s = webui.require_spending(conn)
years = sorted({m.year for m in budget.months(s.df)}, reverse=True)
year = st.selectbox("Year", years, width=240)
table = budget.year_table(s.df, year)
table = table[[cat for cat in s.colors if cat in table.columns]]
n_months = len(table)
totals = table.sum().sort_values(ascending=False)
year_budget = s.budgets.sum() * n_months

k1, k2, k3, k4 = st.columns(4)
months = webui.plural(n_months, "month")
k1.metric(f"Spent in {year}", money(totals.sum()), border=True, help=f"{months} with spending")
k2.metric("Monthly average", money(totals.sum() / n_months), border=True)
k3.metric("Budgeted", money(year_budget), border=True, help=f"Monthly budgets × {months}")
webui.left_metric(k4, year_budget, totals.sum())

with st.container(border=True):
    st.markdown("**Spending by month**")
    st.plotly_chart(charts.stacked_months(table, s.colors, P, s.budgets.sum() or None), config=webui.CHART,
                    theme=None)
c1, c2 = st.columns([1, 1])
with c1, st.container(border=True, height="stretch"):
    st.markdown(f"**{year} by category**")
    st.plotly_chart(charts.donut(budget.fold(totals), s.colors, P, money(totals.sum())), config=webui.CHART,
                    theme=None)
with c2, st.container(border=True, height="stretch"):
    st.markdown(f"**Spent vs budget, {months}**")
    st.plotly_chart(charts.budget_vs_actual(totals, s.budgets * n_months, P), config=webui.CHART, theme=None)

shown = table.copy()
shown.index = [f"{m:%b}" for m in shown.index]
shown["Total"] = shown.sum(axis=1)
webui.table_view(shown.map(money))
