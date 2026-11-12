"""Monthly spending: one month by category, against budgets and the month before."""
import html

import pandas as pd
import streamlit as st

import webui
from stmtrecon import budget, charts

conn, P = webui.conn(), webui.palette()
money = webui.money


def budget_meters(spent: pd.Series, limits: pd.Series) -> None:
    """One labeled bar per budget, filled by how much of it is spent; red with "over by" text once over."""
    rows = []
    for cat in limits.sort_values(ascending=False).index:
        s, b = float(spent.get(cat, 0.0)), float(limits[cat])
        share = min(s / b, 1) if b > 0 else 1
        over = s > b
        note = f"<b>over by {money(s - b)}</b>" if over else f"{money(b - s)} left"
        fill = P.bad if over else P.series[0]
        rows.append(f'<div class="bud-row"><span>{html.escape(cat)}</span><span>{money(s)} of {money(b)} '
                    f'<span class="muted">· {note}</span></span></div><div class="bud-track">'
                    f'<div class="bud-fill" style="width:{share * 100:.1f}%;background:{fill}"></div></div>')
    st.markdown(f"""<style>
.bud-row {{ display:flex; justify-content:space-between; gap:12px; font-size:0.95rem; margin-top:10px; }}
.bud-row .muted {{ color:{P.muted}; }}
.bud-track {{ position:relative; height:10px; border-radius:5px; background:{P.grid}; margin-top:4px; }}
.bud-fill {{ height:10px; border-radius:5px; }}
.bud-meters {{ padding-bottom:calc(1rem + 6px); }}   /* offsets the markdown block's -1rem bottom margin */
</style><div class="bud-meters">""" + "".join(rows) + "</div>", unsafe_allow_html=True)


st.title("Monthly spending")
s = webui.require_spending(conn)
month = st.selectbox("Month", budget.months(s.df), format_func=lambda m: f"{m:%B %Y}", width=240)
this = budget.by_category(s.df[s.df["month"] == month])
prev_month = month - pd.offsets.MonthBegin(1)
prev = budget.by_category(s.df[s.df["month"] == prev_month])
total, total_b = this.sum(), s.budgets.sum()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Spent", money(total), border=True, height="stretch")
k2.metric("Budgeted", money(total_b), border=True, height="stretch")
webui.left_metric(k3, total_b, total)
k4.metric(f"vs {prev_month:%B}", money(total - prev.sum()) if not prev.empty else "–", border=True, height="stretch",
          delta=f"{(total / prev.sum() - 1):+.0%}" if prev.sum() else None, delta_color="inverse")

c1, c2 = st.columns([1, 1])
with c1, st.container(border=True, height="stretch"):
    st.markdown("**Where it went**")
    st.plotly_chart(charts.donut(budget.fold(this), s.colors, P, money(total)), config=webui.CHART, theme=None)
with c2, st.container(border=True, height="stretch"):
    st.markdown("**Budgets**")
    if s.budgets.empty:
        st.caption("No budgets yet. Set them on the **Budgets** page.")
    else:
        budget_meters(this, s.budgets)
    unbudgeted = this[~this.index.isin(s.budgets.index)].sum()
    if unbudgeted > 0:
        st.caption(f"Also spent {money(unbudgeted)} in categories with no budget.")

webui.table_view(pd.DataFrame({"Spent": this, "Budget": s.budgets, f"{prev_month:%B}": prev})
                 .fillna(0).sort_values("Spent", ascending=False).map(money))
