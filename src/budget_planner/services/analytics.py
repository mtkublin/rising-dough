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

import datetime as dt
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from budget_planner.domain.enums import Direction
from budget_planner.domain.periods import month_bounds
from budget_planner.domain.transactions import Transaction, TransactionFilter
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.services import fx as fx_svc
from budget_planner.services.aggregates import mean_minor, sum_by_category

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


def _trailing_12_months(today: dt.date) -> tuple[dt.date, dt.date]:
    end = month_bounds(today.year, today.month)[1]
    start_month = today.month - (_TRAILING_MONTHS - 1)
    year = today.year
    while start_month <= 0:
        start_month += 12
        year -= 1
    return dt.date(year, start_month, 1), end


def _period_bounds(today: dt.date, period: Period) -> tuple[dt.date, dt.date]:
    if period == "month":
        return month_bounds(today.year, today.month)
    if period == "year":
        return dt.date(today.year, 1, 1), dt.date(today.year, 12, 31)
    return _trailing_12_months(today)


def _base_of(
    conn: sqlite3.Connection, user_id: int, converter: fx_svc.FxConverter
) -> Callable[[Transaction], int]:
    """``txn -> base minor`` at the txn's own date (ADR-0006, ADR-0139; Q-008)."""
    ccy = {a.id: a.currency for a in accounts_repo.list_all(conn, user_id, include_deleted=True)}
    return fx_svc.txn_base_of(converter, ccy)


def _spend_by_category(
    conn: sqlite3.Connection,
    user_id: int,
    start: dt.date,
    end: dt.date,
    converter: fx_svc.FxConverter,
) -> tuple[CategoryTotal, ...]:
    cats = {c.id: c for c in categories_repo.list_all(conn, user_id, include_deleted=True)}
    txns = transactions_repo.list_filtered(
        conn,
        user_id,
        TransactionFilter(
            date_from=start,
            date_to=end,
            directions=(Direction.EXPENSE,),
        ),
    )
    base_of = _base_of(conn, user_id, converter)
    totals = sum_by_category(txns, base_of)
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


def _twelve_month_averages(
    conn: sqlite3.Connection,
    user_id: int,
    today: dt.date,
    converter: fx_svc.FxConverter,
) -> tuple[CategoryTotal, ...]:
    """Mean monthly spend per category over the trailing 12 months.

    Divides the trailing-12 sum by 12 regardless of how many months had
    activity — matches the Plan · Analytics "avg/mo" convention.
    """
    start, end = _trailing_12_months(today)
    cats = {c.id: c for c in categories_repo.list_all(conn, user_id, include_deleted=True)}
    txns = transactions_repo.list_filtered(
        conn,
        user_id,
        TransactionFilter(
            date_from=start,
            date_to=end,
            directions=(Direction.EXPENSE,),
        ),
    )
    base_of = _base_of(conn, user_id, converter)
    sums = sum_by_category(txns, base_of)
    rows = [
        CategoryTotal(
            category_id=cat_id,
            category_name=cats[cat_id].name if cat_id in cats else "?",
            amount_minor=mean_minor(amount, _TRAILING_MONTHS),
        )
        for cat_id, amount in sums.items()
    ]
    rows.sort(key=lambda r: (-r.amount_minor, r.category_name.casefold()))
    return tuple(rows)


def _income_vs_expense_monthly(
    conn: sqlite3.Connection,
    user_id: int,
    today: dt.date,
    converter: fx_svc.FxConverter,
) -> tuple[MonthlyFlow, ...]:
    """Trailing-12 (year, month) → income + expense totals."""
    start, end = _trailing_12_months(today)
    cats = {c.id: c for c in categories_repo.list_all(conn, user_id, include_deleted=True)}
    txns = transactions_repo.list_filtered(
        conn,
        user_id,
        TransactionFilter(date_from=start, date_to=end),
    )
    monthly: dict[tuple[int, int], dict[str, int]] = defaultdict(
        lambda: {"income": 0, "expense": 0}
    )
    base_of = _base_of(conn, user_id, converter)
    for t in txns:
        cat = cats.get(t.category_id)
        if cat is None:
            continue
        key = (t.operation_date.year, t.operation_date.month)
        if cat.direction is Direction.INCOME:
            monthly[key]["income"] += base_of(t)
        elif cat.direction is Direction.EXPENSE:
            monthly[key]["expense"] += base_of(t)
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
    user_id: int,
    start: dt.date,
    end: dt.date,
    limit: int,
    *,
    converter: fx_svc.FxConverter,
) -> tuple[LargestItem, ...]:
    cats = {c.id: c for c in categories_repo.list_all(conn, user_id, include_deleted=True)}
    txns = transactions_repo.list_filtered(
        conn,
        user_id,
        TransactionFilter(
            date_from=start,
            date_to=end,
            directions=(Direction.EXPENSE,),
        ),
    )
    base_of = _base_of(conn, user_id, converter)
    base_amounts = {t.id: base_of(t) for t in txns}
    ranked = sorted(txns, key=lambda t: (-base_amounts[t.id], t.operation_date))
    return tuple(
        LargestItem(
            transaction_id=t.id,
            operation_date=t.operation_date,
            category_name=cats[t.category_id].name if t.category_id in cats else "?",
            description=t.description,
            amount_minor=base_amounts[t.id],
        )
        for t in ranked[:limit]
    )


def bundle(
    conn: sqlite3.Connection,
    user_id: int,
    converter: fx_svc.FxConverter,
    *,
    today: dt.date,
    period: Period = "month",
    largest_limit: int = _DEFAULT_LARGEST_LIMIT,
) -> AnalyticsBundle:
    """Return the four-panel analytics bundle for ``period``.

    ``converter`` is the cache-only FX converter (ADR-0139): every amount is in
    its base currency, each transaction at its own date's rate (Q-008).
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
        spend_by_category=_spend_by_category(conn, user_id, start, end, converter),
        twelve_month_averages=_twelve_month_averages(conn, user_id, today, converter),
        income_vs_expense_monthly=_income_vs_expense_monthly(conn, user_id, today, converter),
        largest_items=_largest_items(conn, user_id, start, end, largest_limit, converter=converter),
    )


__all__ = [
    "AnalyticsBundle",
    "CategoryTotal",
    "LargestItem",
    "MonthlyFlow",
    "Period",
    "bundle",
    "normalize_period",
    "reference_today",
    "spend_total_minor",
    "twelve_month_avg_by_category",
]


def twelve_month_avg_by_category(bundle: AnalyticsBundle) -> dict[int, int]:
    """Return ``category_id -> 12-month average minor`` for the spend list deltas."""
    return {row.category_id: row.amount_minor for row in bundle.twelve_month_averages}


def spend_total_minor(bundle: AnalyticsBundle) -> int:
    """Return the total of the spend-by-category rows."""
    return sum(row.amount_minor for row in bundle.spend_by_category)


def reference_today(today: dt.date, year: int, month: int) -> dt.date:
    """Return the "today" the analytics math uses for the picked month (ADR-0138).

    The current month keeps real ``today``; any other month is pinned to its last day.
    """
    if (year, month) == (today.year, today.month):
        return today
    return month_bounds(year, month)[1]


_VALID_PERIODS: tuple[Period, ...] = ("month", "year", "trailing-12")


def normalize_period(raw: str | None) -> Period:
    """Return the requested analytics period, defaulting to ``"month"`` on unknown input."""
    for candidate in _VALID_PERIODS:
        if raw == candidate:
            return candidate
    return "month"
