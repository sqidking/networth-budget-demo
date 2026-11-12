"""Spending and budget figures for the month and year views, and the monthly budgets themselves."""
from __future__ import annotations

import sqlite3

import pandas as pd

OTHER = "Other"


def spending(conn: sqlite3.Connection) -> pd.DataFrame:
    """One row per transaction in a spending category: date (the purchase date when there is one), month,
    category and spent (positive = money out; a refund is negative and lowers its category's total)."""
    df = pd.read_sql_query(
        "SELECT t.match_date AS date, c.name AS category, -t.amount AS spent "
        "FROM transactions t JOIN categories c ON c.id = t.category_id WHERE c.kind = 'spending'", conn)
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    return df


def uncategorized(conn: sqlite3.Connection) -> tuple[int, float]:
    """How many money-out transactions have no category yet, and their total. They aren't in any chart."""
    n, total = conn.execute("SELECT count(*), COALESCE(-sum(amount), 0) FROM transactions "
                            "WHERE category_id IS NULL AND amount < 0").fetchone()
    return n, total


def categories(conn: sqlite3.Connection) -> list[str]:
    """Spending categories in a fixed order (by creation), so each keeps the same color in every chart."""
    return [r[0] for r in conn.execute("SELECT name FROM categories WHERE kind = 'spending' ORDER BY id")]


def budgets(conn: sqlite3.Connection) -> pd.Series:
    """Monthly budget by category name."""
    rows = conn.execute("SELECT c.name, b.monthly FROM budgets b JOIN categories c ON c.id = b.category_id "
                        "WHERE c.kind = 'spending'").fetchall()
    return pd.Series({r[0]: r[1] for r in rows}, dtype=float)


def set_budget(conn: sqlite3.Connection, category: str, monthly: float | None) -> None:
    """Set a spending category's monthly budget, or remove it with None."""
    row = conn.execute("SELECT id FROM categories WHERE name = ? AND kind = 'spending'", (category,)).fetchone()
    if row is None:
        raise ValueError(f"No spending category named {category!r}.")
    with conn:
        if monthly is None:
            conn.execute("DELETE FROM budgets WHERE category_id = ?", (row[0],))
        else:
            conn.execute("INSERT INTO budgets (category_id, monthly) VALUES (?, ?) "
                         "ON CONFLICT (category_id) DO UPDATE SET monthly = excluded.monthly", (row[0], monthly))


def months(df: pd.DataFrame) -> list[pd.Timestamp]:
    return sorted(df["month"].unique(), reverse=True)


def recent_average(df: pd.DataFrame, n: int = 6) -> tuple[pd.Series, int]:
    """Average monthly spending per category over the last ``n`` months with spending, and how many months
    that turned out to be."""
    recent = months(df)[:n]
    total = df[df["month"].isin(recent)].groupby("category")["spent"].sum()
    return total / max(len(recent), 1), len(recent)


def round_up(values: pd.Series, step: int = 10) -> pd.Series:
    """Each value rounded up to the next multiple of ``step`` (a budget suggestion)."""
    return (-(-values // step) * step).astype(float)


def by_category(df: pd.DataFrame) -> pd.Series:
    """Total spent per category, largest first."""
    return df.groupby("category")["spent"].sum().sort_values(ascending=False)


def fold(totals: pd.Series, keep: int = 5) -> pd.Series:
    """The largest ``keep`` parts, with the rest summed into "Other" (charts stay readable at six parts)."""
    totals = totals[totals > 0]
    if len(totals) <= keep + 1:
        return totals
    return pd.concat([totals.iloc[:keep], pd.Series({OTHER: totals.iloc[keep:].sum()})])


def year_table(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Months of one year as rows, spending categories as columns."""
    y = df[df["month"].dt.year == year]
    return y.pivot_table(index="month", columns="category", values="spent", aggfunc="sum", fill_value=0.0)
