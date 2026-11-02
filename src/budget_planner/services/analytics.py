"""Analytics bundle service (T-R43, ADR-0056 §6).

Replaces the Plotly-backed ``/analytics`` endpoint with a pure-dict
projection shaped for the Rising Dough SVG charts (Phase 5). Four pieces:

- ``spend_by_category`` — month-scoped spend per expense category.
- ``twelve_month_averages`` — rolling 12-month mean per category.
- ``income_vs_expense_monthly`` — sorted series over the trailing 12 months.
- ``largest_items`` — top-N expense transactions over the period.

All amounts are minor units; template layer handles currency formatting.
"""

from __future__ import annotations

import calendar
import datetime as dt
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Literal

from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import TransactionFilter
from budget_planner.repositories import (
    categories as categories_repo,
    transactions as transactions_repo,
)

Period = Literal["month", "year", "trailing-12"]

_TRAILING_MONTHS = 12
_DEFAULT_LARGEST_LIMIT = 3  # manual-audit #48 — mockup caps the box at 3 rows.


@dataclass(frozen=True, slots=True)
class CategoryTotal:
    """One row of the spend-by-category panel."""

    category_id: int
    category_name: str
    amount_minor: int


@dataclass(frozen=True, slots=True)
class MonthlyFlow:
    """One (year-month, income, expense) point for the two-line panel."""

    year: int
    month: int
    income_minor: int
    expense_minor: int

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@dataclass(frozen=True, slots=True)
class LargestItem:
    """One entry in the "largest expenses" leaderboard."""

    transaction_id: int
    operation_date: dt.date
    category_name: str
    description: str
    amount_minor: int


@dataclass(frozen=True, slots=True)
class AnalyticsBundle:
    """ADR-0056 §6 — projection powering the Analytics tab + Phase 5 charts."""

    period: Period
    period_start: dt.date
    period_end: dt.date
    spend_by_category: tuple[CategoryTotal, ...]
    twelve_month_averages: tuple[CategoryTotal, ...]
    income_vs_expense_monthly: tuple[MonthlyFlow, ...]
    largest_items: tuple[LargestItem, ...]


def _month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    last_day = calendar.monthrange(year, month)[1]
    return dt.date(year, month, 1), dt.date(year, month, last_day)


def _trailing_12_months(today: dt.date) -> tuple[dt.date, dt.date]:
    end = _month_bounds(today.year, today.month)[1]
    start_month = today.month - (_TRAILING_MONTHS - 1)
    year = today.year
    while start_month <= 0:
        start_month += 12
        year -= 1
    return dt.date(year, start_month, 1), end


def _period_bounds(today: dt.date, period: Period) -> tuple[dt.date, dt.date]:
    if period == "month":
        return _month_bounds(today.year, today.month)
    if period == "year":
        return dt.date(today.year, 1, 1), dt.date(today.year, 12, 31)
    return _trailing_12_months(today)


def _spend_by_category(
    conn: sqlite3.Connection,
    start: dt.date,
    end: dt.date,
) -> tuple[CategoryTotal, ...]:
    cats = {c.id: c for c in categories_repo.list_all(conn, include_deleted=True)}
    txns = transactions_repo.list_filtered(
        conn,
        TransactionFilter(
            date_from=start,
            date_to=end,
            directions=(Direction.EXPENSE,),
        ),
    )
    totals: dict[int, int] = defaultdict(int)
    for t in txns:
        totals[t.category_id] += t.amount
    rows = [
        CategoryTotal(
            category_id=cat_id,
            category_name=cats[cat_id].name if cat_id in cats else "?",
            amount_minor=amount,
        )
        for cat_id, amount in totals.items()
    ]
    rows.sort(key=lambda r: (-r.amount_minor, r.category_name.casefold()))
    return tuple(rows)


def _mean_minor(total: int, months: int) -> int:
    if months <= 0:
        return 0
    quantised = (Decimal(total) / Decimal(months)).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
    return int(quantised)


def _twelve_month_averages(
    conn: sqlite3.Connection,
    today: dt.date,
) -> tuple[CategoryTotal, ...]:
    """Mean monthly spend per category over the trailing 12 months.

    Divides the trailing-12 sum by 12 regardless of how many months had
    activity — matches the Plan · Analytics "avg/mo" convention.
    """
    start, end = _trailing_12_months(today)
    cats = {c.id: c for c in categories_repo.list_all(conn, include_deleted=True)}
    txns = transactions_repo.list_filtered(
        conn,
        TransactionFilter(
            date_from=start,
            date_to=end,
            directions=(Direction.EXPENSE,),
        ),
    )
    sums: dict[int, int] = defaultdict(int)
    for t in txns:
        sums[t.category_id] += t.amount
    rows = [
        CategoryTotal(
            category_id=cat_id,
            category_name=cats[cat_id].name if cat_id in cats else "?",
            amount_minor=_mean_minor(amount, _TRAILING_MONTHS),
        )
        for cat_id, amount in sums.items()
    ]
    rows.sort(key=lambda r: (-r.amount_minor, r.category_name.casefold()))
    return tuple(rows)


def _income_vs_expense_monthly(
    conn: sqlite3.Connection,
    today: dt.date,
) -> tuple[MonthlyFlow, ...]:
    """Trailing-12 (year, month) → income + expense totals."""
    start, end = _trailing_12_months(today)
    cats = {c.id: c for c in categories_repo.list_all(conn, include_deleted=True)}
    txns = transactions_repo.list_filtered(
        conn,
        TransactionFilter(date_from=start, date_to=end),
    )
    monthly: dict[tuple[int, int], dict[str, int]] = defaultdict(
        lambda: {"income": 0, "expense": 0}
    )
    for t in txns:
        cat = cats.get(t.category_id)
        if cat is None:
            continue
        key = (t.operation_date.year, t.operation_date.month)
        if cat.direction is Direction.INCOME:
            monthly[key]["income"] += t.amount
        elif cat.direction is Direction.EXPENSE:
            monthly[key]["expense"] += t.amount
    out = [
        MonthlyFlow(
            year=year,
            month=month,
            income_minor=values["income"],
            expense_minor=values["expense"],
        )
        for (year, month), values in monthly.items()
    ]
    out.sort(key=lambda m: (m.year, m.month))
    return tuple(out)


def _largest_items(
    conn: sqlite3.Connection,
    start: dt.date,
    end: dt.date,
    limit: int,
) -> tuple[LargestItem, ...]:
    cats = {c.id: c for c in categories_repo.list_all(conn, include_deleted=True)}
    txns = transactions_repo.list_filtered(
        conn,
        TransactionFilter(
            date_from=start,
            date_to=end,
            directions=(Direction.EXPENSE,),
        ),
    )
    ranked = sorted(txns, key=lambda t: (-t.amount, t.operation_date))
    return tuple(
        LargestItem(
            transaction_id=t.id,
            operation_date=t.operation_date,
            category_name=cats[t.category_id].name if t.category_id in cats else "?",
            description=t.description,
            amount_minor=t.amount,
        )
        for t in ranked[:limit]
    )


def bundle(
    conn: sqlite3.Connection,
    *,
    today: dt.date,
    period: Period = "month",
    largest_limit: int = _DEFAULT_LARGEST_LIMIT,
) -> AnalyticsBundle:
    """Return the four-panel analytics bundle for ``period``.

    ``today`` is injected (ADR-0007). ``period`` picks the spend-by-category
    + largest-items window; the twelve-month averages + flow trend always
    span the trailing 12 months regardless (that's the whole point of
    those two panels).
    """
    start, end = _period_bounds(today, period)
    return AnalyticsBundle(
        period=period,
        period_start=start,
        period_end=end,
        spend_by_category=_spend_by_category(conn, start, end),
        twelve_month_averages=_twelve_month_averages(conn, today),
        income_vs_expense_monthly=_income_vs_expense_monthly(conn, today),
        largest_items=_largest_items(conn, start, end, largest_limit),
    )


__all__ = [
    "AnalyticsBundle",
    "CategoryTotal",
    "LargestItem",
    "MonthlyFlow",
    "Period",
    "bundle",
]
