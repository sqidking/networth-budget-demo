"""Budgets: a monthly budget per spending category, with a suggestion from recent spending."""
import pandas as pd
import streamlit as st

import webui
from stmtrecon import budget

conn = webui.conn()
s = webui.spending(conn)

st.title("Budgets")
st.caption("A monthly budget per spending category. The suggestion is the average of the last six months with "
           "spending, rounded up to the next $10. Clear a cell to remove that budget.")
cats = budget.categories(conn)
if not cats:
    st.info("No spending categories yet. Load the sample data, or create categories on **Statement Parse → "
            "Review**.")
    st.stop()

avg, n_months = budget.recent_average(s.df)
grid = pd.DataFrame({"Category": cats, "Budget": [float(s.budgets.get(c, float("nan"))) for c in cats],
                     "Average": [round(avg.get(c, 0.0), 2) for c in cats]})
grid["Suggested"] = budget.round_up(grid["Average"])

if s.budgets.sum():
    k1, k2, k3 = st.columns(3)
    k1.metric("Monthly budget", webui.money(s.budgets.sum()), border=True)
    k2.metric("Average spending", webui.money(avg.sum()), border=True,
              help=f"Over the last {webui.plural(n_months, 'month')} with spending")
    k3.metric("Room each month", webui.money(s.budgets.sum() - avg.sum()), border=True)

edited = st.data_editor(grid, hide_index=True, width="stretch", key="budget_grid",
                        disabled=["Category", "Average", "Suggested"],
                        column_config={"Budget": st.column_config.NumberColumn(format="dollar", min_value=0),
                                       "Average": st.column_config.NumberColumn(format="dollar"),
                                       "Suggested": st.column_config.NumberColumn(format="dollar")})
changed = edited[edited["Budget"].fillna(-1) != grid["Budget"].fillna(-1)]
buttons = st.container(horizontal=True)
if buttons.button(f"Save {webui.plural(len(changed), 'change')}", type="primary", disabled=changed.empty):
    for r in changed.itertuples():
        budget.set_budget(conn, r.Category, None if pd.isna(r.Budget) else float(r.Budget))
    st.rerun()
blanks = grid[grid["Budget"].isna() & (grid["Suggested"] > 0)]
if buttons.button(f"Fill {webui.plural(len(blanks), 'blank')} with suggestions", disabled=blanks.empty):
    for r in blanks.itertuples():
        budget.set_budget(conn, r.Category, float(r.Suggested))
    st.rerun()
