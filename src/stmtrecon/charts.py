"""Plotly figures with one validated categorical palette, stepped separately for light and dark mode."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go

from .budget import OTHER


@dataclass(frozen=True)
class Palette:
    surface: str
    ink: str
    ink2: str
    muted: str
    grid: str
    axis: str
    good: str
    bad: str
    other: str
    series: tuple[str, ...]      # categorical hues, assigned by a category's fixed position


LIGHT = Palette(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781", grid="#e1e0d9", axis="#c3c2b7",
                good="#006300", bad="#d03b3b", other="#b5b3ab",
                series=("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"))
DARK = Palette(surface="#1a1a19", ink="#f0efec", ink2="#c3c2b7", muted="#898781", grid="#2c2c2a", axis="#383835",
               good="#0ca30c", bad="#e66767", other="#5f5e59",
               series=("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"))
FONT = "system-ui, -apple-system, Segoe UI, sans-serif"


def palette(theme: str) -> Palette:
    return DARK if theme == "dark" else LIGHT


def colors(categories: list[str], p: Palette) -> dict[str, str]:
    """Category -> color by its fixed position, so a category's color never depends on what else is shown.
    Past eight categories, the rest share the "Other" gray rather than inventing new hues."""
    out = {c: p.series[i] if i < len(p.series) else p.other for i, c in enumerate(categories)}
    out[OTHER] = p.other
    return out


def _layout(fig: go.Figure, p: Palette, height: int, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(family=FONT, size=13, color=p.ink2), showlegend=legend,
        hoverlabel=dict(bgcolor=p.surface, bordercolor=p.grid, font=dict(family=FONT, color=p.ink)),
        legend=dict(orientation="h", y=-0.12, x=0, font=dict(color=p.ink2), bgcolor="rgba(0,0,0,0)"))
    fig.update_xaxes(showgrid=False, linecolor=p.axis, tickfont=dict(color=p.muted), zeroline=False)
    fig.update_yaxes(gridcolor=p.grid, zerolinecolor=p.axis, tickfont=dict(color=p.muted), automargin=True)
    return fig


def _hbars(fig: go.Figure, p: Palette, labels: list, height: int, right: int, legend: bool = True) -> go.Figure:
    """Shared look of the ranked horizontal bar charts: labels on the left sized to fit, largest bar on top,
    no value axis (amounts are printed at the bar ends instead)."""
    _layout(fig, p, height, legend)
    left = min(max(8 * max((len(str(c)) for c in labels), default=4) + 12, 60), 200)
    fig.update_layout(margin=dict(l=left, r=right, t=8, b=8), hovermode="closest")
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)", tickfont=dict(color=p.ink2))
    fig.update_xaxes(showticklabels=False)
    return fig


def donut(totals: pd.Series, cmap: dict[str, str], p: Palette, center: str) -> go.Figure:
    """Part-to-whole at a glance: at most six parts (see budget.fold), 2px surface gaps between slices."""
    fig = go.Figure(go.Pie(
        labels=list(totals.index), values=list(totals.values), hole=0.66, sort=False, direction="clockwise",
        marker=dict(colors=[cmap.get(c, p.other) for c in totals.index], line=dict(color=p.surface, width=2)),
        textinfo="none", hovertemplate="%{label}<br>$%{value:,.2f} · %{percent}<extra></extra>"))
    _layout(fig, p, 300)
    fig.update_layout(legend=dict(orientation="v", y=0.5, yanchor="middle", x=1.0),
                      annotations=[dict(text=center, showarrow=False, font=dict(size=20, color=p.ink))])
    return fig


def stacked_months(table: pd.DataFrame, cmap: dict[str, str], p: Palette, budget_total: float | None) -> go.Figure:
    """Monthly spending stacked by category, with the total monthly budget as a dashed reference line."""
    fig = go.Figure()
    x = [m.strftime("%b") for m in table.index]
    for cat in table.columns:
        fig.add_trace(go.Bar(x=x, y=table[cat], name=cat, marker=dict(color=cmap.get(cat, p.other),
                                                                      line=dict(color=p.surface, width=2)),
                             hovertemplate=f"{cat}<br>%{{x}}: $%{{y:,.2f}}<extra></extra>"))
    if budget_total:
        fig.add_trace(go.Scatter(x=x, y=[budget_total] * len(x), name="Monthly budget", mode="lines",
                                 line=dict(color=p.ink2, width=2, dash="dash"),
                                 hovertemplate="Budget: $%{y:,.0f}<extra></extra>"))
    _layout(fig, p, 380)
    fig.update_layout(barmode="stack", barcornerradius=4, bargap=0.35, hovermode="closest")
    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    return fig


def budget_vs_actual(actual: pd.Series, budget: pd.Series, p: Palette) -> go.Figure:
    """Ranked horizontal bars of spending (one hue) with each category's budget as a marker on the same axis."""
    cats = list(actual.sort_values(ascending=False).index)
    a, b = actual.reindex(cats).fillna(0), budget.reindex(cats)
    labels = [f"${v:,.0f}" + (f" of ${bv:,.0f}" if pd.notna(bv) else "") for v, bv in zip(a, b)]
    fig = go.Figure(go.Bar(y=cats, x=a, orientation="h", name="Spent", width=0.55,
                           marker=dict(color=p.series[0], cornerradius=4),
                           hovertemplate="%{y}<br>Spent $%{x:,.2f}<extra></extra>"))
    if b.notna().any():
        fig.add_trace(go.Scatter(y=cats, x=b, mode="markers", name="Budget",
                                 marker=dict(symbol="line-ns", size=22, line=dict(color=p.ink, width=3)),
                                 hovertemplate="%{y}<br>Budget $%{x:,.0f}<extra></extra>"))
    # Labels sit past whichever is further out, the bar or its budget marker, so they never overlap either.
    ends = [max(v, bv) if pd.notna(bv) else v for v, bv in zip(a, b)]
    fig.add_trace(go.Scatter(y=cats, x=ends, mode="text", text=["  " + t for t in labels], textposition="middle right",
                             textfont=dict(color=p.ink2), showlegend=False, hoverinfo="skip", cliponaxis=False))
    return _hbars(fig, p, cats, max(220, 44 * len(cats)), right=150)


def net_worth(totals: pd.DataFrame, p: Palette) -> go.Figure:
    """Net worth with assets and debts on one dollar axis; net worth is the heaviest line."""
    fig = go.Figure()
    styles = {"Assets": (p.series[2], 2), "Debts": (p.series[6], 2), "Net worth": (p.series[0], 3)}
    for col, (colr, width) in styles.items():
        fig.add_trace(go.Scatter(x=totals.index, y=totals[col], name=col, mode="lines",
                                 line=dict(color=colr, width=width), hovertemplate=f"{col}: $%{{y:,.0f}}<extra></extra>"))
        last = totals[col].iloc[-1]
        fig.add_annotation(x=totals.index[-1], y=last, text=f"  {col} ${last:,.0f}", showarrow=False,
                           xanchor="left", font=dict(color=p.ink2, size=12))
    _layout(fig, p, 380)
    fig.update_layout(hovermode="x unified", margin=dict(l=8, r=150, t=8, b=8))
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1, spikecolor=p.axis, spikedash="solid")
    fig.update_yaxes(tickprefix="$", tickformat="~s")
    return fig


def ranked_bars(values: pd.Series, color: str, p: Palette) -> go.Figure:
    """One hue, largest first, the amount printed at the end of each bar."""
    v = values.sort_values(ascending=False)
    fig = go.Figure(go.Bar(y=list(v.index), x=list(v.values), orientation="h", width=0.55,
                           marker=dict(color=color, cornerradius=4), text=[f"${x:,.0f}" for x in v.values],
                           textposition="outside", textfont=dict(color=p.ink2), cliponaxis=False,
                           hovertemplate="%{y}<br>$%{x:,.0f}<extra></extra>"))
    return _hbars(fig, p, list(v.index), max(160, 48 * len(v)), right=90, legend=False)
