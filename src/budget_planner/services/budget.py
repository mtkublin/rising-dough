"""Budget service (T-024 / T-120).

Resolve monthly budgets via the three-tier null-coalesce (one-off →
recurring → default) and build a month summary with per-category
budgeted / spent / remaining plus analytics (avg monthly overall,
avg this year, delta vs previous month). Flat categories, no rollover
(ADR-0014).

T-120 (ADR-0039) introduces :func:`committed_in_window` + grows
``MonthTotals`` with ``committed_minor``. ``remaining_minor`` becomes
``budgeted - spent - committed`` so the "Left per day" headline is
honest about recurring / planned commitments that have not yet
promoted into actual transactions.

The service does its own aggregation over ``transactions.list_filtered``
rather than extending the repository with aggregate SQL — keeps the repo
a thin SQL wrapper (ADR-0022) and bounded loops are fine for v1 volumes.
"""

from __future__ import annotations

import calendar
import datetime as dt
import logging
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from budget_planner.config import get_settings
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import PlannedFilter
from budget_planner.domain.transactions import Transaction, TransactionFilter
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from budget_planner.services import (
    fx as fx_svc,
    income as income_svc,
    preferences as preferences_svc,
    recurring as recurring_svc,
)

logger = logging.getLogger(__name__)


def base_amount_converter(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    today: dt.date | None = None,
    base_currency: str | None = None,
) -> Callable[[int, int], int]:
    """Return ``(account_id, amount_minor) -> base-currency minor`` (ADR-0092).

    Planned / recurring items are future-dated, so the rate is the latest
    cached one on or before ``today`` (never the item's date, never the
    network). Base-currency accounts are untouched. A missing rate degrades to
    the native amount (rate 1) with a warning, like the Today account rows.
    """
    ref = today if today is not None else dt.date.today()  # noqa: DTZ011 — ADR-0007
    base = base_currency or get_settings().base_currency
    ccy_by_account = {
        a.id: a.currency for a in accounts_repo.list_all(conn, user_id, include_deleted=True)
    }

    def _convert(account_id: int, amount_minor: int) -> int:
        ccy = ccy_by_account.get(account_id, base)
        if ccy == base:
            return amount_minor
        try:
            return fx_svc.convert_cached(conn, amount_minor, ref, ccy, base)
        except fx_svc.FxUnavailableError:
            logger.warning("no FX rate %s->%s; committed uses native amount", ccy, base)
            return amount_minor

    return _convert


@dataclass(frozen=True, slots=True)
class CategoryBudgetLine:
    category_id: int
    category_name: str
    category_direction: Direction
    category_color: str | None
    budgeted_minor: int | None
    spent_minor: int
    remaining_minor: int | None
    avg_monthly_overall_minor: int
    avg_this_year_minor: int
    delta_vs_prev_month_minor: int


@dataclass(frozen=True, slots=True)
class MonthTotals:
    budgeted_minor: int
    spent_minor: int
    committed_minor: int
    remaining_minor: int
    # ADR-0085: same-window planned + recurring expenses in categories with no
    # budget. Informational only; never part of ``remaining_minor``.
    unbudgeted_committed_minor: int = 0


@dataclass(frozen=True, slots=True)
class MonthSummary:
    year: int
    month: int
    lines: tuple[CategoryBudgetLine, ...]
    totals: MonthTotals
    left_daily_spend_minor: int | None
    next_income_date: date
    days_until_next_income: int
    anchor_category_name: str | None
    period_start: date


# ADR-0031 §3 — Yearly budget grid origin tag for cell typography.
# Literal "default" | "recurring" | "one_off" | "unset" is projected into the
# template to encode tier dominance via CSS classes.
@dataclass(frozen=True, slots=True)
class YearlyCell:
    amount_minor: int | None
    origin: str  # "default" | "recurring" | "one_off" | "unset"


@dataclass(frozen=True, slots=True)
class YearlyRow:
    category_id: int
    category_name: str
    category_direction: Direction
    category_color: str | None
    cells: tuple[YearlyCell, ...]  # exactly 12 entries, Jan..Dec
    total_minor: int


def prev_year_month(year: int, month: int) -> tuple[int, int]:
    """Return the previous ``(year, month)`` tuple handling January rollover."""
    if month == 1:
        return year - 1, 12
    return year, month - 1


def resolve_budget(
    conn: sqlite3.Connection,
    user_id: int,
    category_id: int,
    year: int,
    month: int,
) -> int | None:
    """Null-coalesce: one-off → recurring → default. Zero is a valid value."""
    one_off = budgets_repo.get_one_off(conn, user_id, category_id, year, month)
    if one_off is not None:
        return one_off.amount
    recurring = budgets_repo.get_recurring(conn, user_id, category_id, month)
    if recurring is not None:
        return recurring.amount
    default = budgets_repo.get_default(conn, user_id, category_id)
    if default is not None:
        return default.amount
    return None


def _month_range(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _expense_txns_in_range(
    conn: sqlite3.Connection, user_id: int, start: date, end: date
) -> list[Transaction]:
    return transactions_repo.list_filtered(
        conn,
        user_id,
        TransactionFilter(
            date_from=start,
            date_to=end,
            directions=(Direction.EXPENSE,),
        ),
    )


def _sum_by_category(txns: list[Transaction]) -> dict[int, int]:
    out: dict[int, int] = defaultdict(int)
    for t in txns:
        out[t.category_id] += t.amount
    return dict(out)


def _active_month_counts(txns: list[Transaction]) -> dict[int, int]:
    """Count distinct ``YYYY-MM`` buckets per category (expense direction only)."""
    seen: dict[int, set[str]] = defaultdict(set)
    for t in txns:
        key = f"{t.operation_date.year:04d}-{t.operation_date.month:02d}"
        seen[t.category_id].add(key)
    return {cat_id: len(months) for cat_id, months in seen.items()}


def _mean_minor(total: int, count: int) -> int:
    if count <= 0:
        return 0
    quantised = (Decimal(total) / Decimal(count)).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
    return int(quantised)


def _all_expense_txns(conn: sqlite3.Connection, user_id: int) -> list[Transaction]:
    return transactions_repo.list_filtered(
        conn, user_id, TransactionFilter(directions=(Direction.EXPENSE,))
    )


def _committed_by_category(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    start: dt.date,
    end: dt.date,
    today: dt.date | None = None,
    base_currency: str | None = None,
) -> dict[int, int]:
    """Return ``{category_id: committed_minor}`` for ``[start, end)`` in base currency.

    Expense-direction categories only (transit + adjustment + income
    excluded). Sources: unpromoted planned rows and active recurring-rule
    occurrences (overrides applied) - see :func:`committed_in_window`.
    """
    out: dict[int, int] = defaultdict(int)
    if end <= start:
        return out
    to_base = base_amount_converter(conn, user_id, today=today, base_currency=base_currency)

    expense_ids = {
        cat.id
        for cat in categories_repo.list_all(conn, user_id, include_deleted=True)
        if cat.direction is Direction.EXPENSE
    }
    inclusive_end = end - dt.timedelta(days=1)
    dedup_keys = recurring_svc.linked_occurrence_keys(conn, user_id)

    planned_rows = planned_repo.list_filtered(
        conn,
        user_id,
        PlannedFilter(
            date_from=start,
            date_to=inclusive_end,
            directions=(Direction.EXPENSE,),
            promoted=False,
        ),
    )
    for row in planned_rows:
        out[row.category_id] += to_base(row.account_id, row.amount)

    # Clamp the generator window to [max(rule.next_due, start), end). Rules
    # advance ``next_due`` on promote; occurrences on-or-before the previous
    # ``next_due`` have either been promoted (counted in ``spent``) or are
    # historical no-ops. The generator anchors on ``rule.start_date``, so the
    # clamp never shifts the cadence (each occurrence is counted once).
    for rule in recurring_repo.list_rules(conn, user_id, active_only=True):
        if rule.category_id not in expense_ids:
            continue
        rule_start = max(rule.next_due, start)
        if rule_start > inclusive_end:
            continue
        overrides = recurring_repo.list_overrides(conn, user_id, rule.id)
        occurrences = recurring_svc.rt_expand(
            conn, user_id, rule, overrides, rule_start, inclusive_end
        )
        out[rule.category_id] += sum(
            to_base(occ.account_id, occ.amount)
            for occ in occurrences
            if (rule.id, occ.occurrence_date) not in dedup_keys
        )
    return out


def committed_in_window(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    start: dt.date,
    end: dt.date,
    today: dt.date | None = None,
    base_currency: str | None = None,
) -> int:
    """Return the committed-minor sum for ``[start, end)`` over ALL expense categories.

    Composes unpromoted planned expenses and active recurring-rule expense
    occurrences (``state=skipped`` drops, ``state=overridden`` merges).
    Returns ``0`` when ``end <= start``. This is the unfiltered total; the
    budget "left" math uses :func:`committed_split_in_window` (ADR-0085).
    """
    by_cat = _committed_by_category(
        conn, user_id, start=start, end=end, today=today, base_currency=base_currency
    )
    return sum(by_cat.values())


def committed_split_in_window(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    start: dt.date,
    end: dt.date,
    budgeted_category_ids: frozenset[int],
    today: dt.date | None = None,
    base_currency: str | None = None,
) -> tuple[int, int]:
    """Return ``(budgeted_committed, unbudgeted_committed)`` for ``[start, end)``.

    ADR-0085: only commitments in categories with a resolved budget reduce
    "left"; the rest is surfaced as an informational figure.
    """
    by_cat = _committed_by_category(
        conn, user_id, start=start, end=end, today=today, base_currency=base_currency
    )
    budgeted = sum(v for k, v in by_cat.items() if k in budgeted_category_ids)
    unbudgeted = sum(v for k, v in by_cat.items() if k not in budgeted_category_ids)
    return budgeted, unbudgeted


def _resolve_anchor(
    conn: sqlite3.Connection,
    user_id: int,
    today: date,
    budgeted_total: int,
    end_of_month: date,
) -> tuple[str | None, date]:
    """Return (anchor_name, next_income_date) for the daily-spend math.

    Zero-budget months and missing/stale anchors fall back to end-of-month
    per F4.6. Pulled out of ``month_summary`` to keep its statement count
    under PLR0915.
    """
    if budgeted_total == 0:
        return None, end_of_month
    anchor = preferences_svc.resolve_income_anchor_category(conn, user_id)
    if anchor is None:
        return None, end_of_month
    hit = income_svc.next_anchor_date(conn, user_id, anchor.id, after=today)
    if hit is None:
        return None, end_of_month
    return anchor.name, hit


def fiscal_month_for(conn: sqlite3.Connection, user_id: int, today: date) -> tuple[int, int]:
    """Return the ``(year, month)`` of the cycle whose paycheck most recently landed."""
    anchor_category = preferences_svc.resolve_income_anchor_category(conn, user_id)
    if anchor_category is None:
        return today.year, today.month
    rows = transactions_repo.list_filtered(
        conn,
        user_id,
        TransactionFilter(
            date_to=today,
            category_ids=(anchor_category.id,),
            directions=(Direction.INCOME,),
        ),
    )
    if not rows:
        return today.year, today.month
    last_anchor_date = max(row.operation_date for row in rows)
    return last_anchor_date.year, last_anchor_date.month


def _resolve_period_start(  # noqa: PLR0917 — user_id gates isolation; ADR-0061 §5
    conn: sqlite3.Connection,
    user_id: int,
    today: date,
    year: int,
    month: int,
    anchor_category: Category | None,
) -> date:
    """Return the start of the paycheck window for per-category ``spent_minor``.

    ADR-0041: the budget "period" is ``[last_anchor_date, today]`` where
    ``last_anchor_date`` is the operation date of the most recent **promoted**
    (actual) transaction in the anchor category with ``operation_date <= today``.
    Falls back to ``date(year, month, 1)`` when the anchor is unset or has no
    prior landed row. Planned/virtual recurring rows deliberately do not count —
    only money that has actually landed resets the window.
    """
    month_start = date(year, month, 1)
    if anchor_category is None:
        return month_start
    rows = transactions_repo.list_filtered(
        conn,
        user_id,
        TransactionFilter(
            date_to=today,
            category_ids=(anchor_category.id,),
            directions=(Direction.INCOME,),
        ),
    )
    if not rows:
        return month_start
    # Repo defaults to ASC on operation_date; take max() for clarity rather
    # than relying on the sort direction.
    return max(row.operation_date for row in rows)


def resolve_period_start(conn: sqlite3.Connection, user_id: int, today: date) -> date:
    """Public period-start resolution for ``today`` (ADR-0041, ADR-0089).

    Last landed income-anchor transaction ``<= today``; else the 1st of
    ``today``'s month. Same logic as the budget's private resolver.
    """
    anchor = preferences_svc.resolve_income_anchor_category(conn, user_id)
    return _resolve_period_start(conn, user_id, today, today.year, today.month, anchor)


def month_summary(  # noqa: PLR0915
    conn: sqlite3.Connection,
    user_id: int,
    year: int,
    month: int,
    *,
    today: date,
    period_window: tuple[date, date] | None = None,
) -> MonthSummary:
    """Build the per-category spent / budgeted / remaining view + analytics.

    Lines include every live expense-direction category. Totals exclude
    unbudgeted lines (``remaining_minor is None``). ``today`` is injected
    (ADR-0007) so left-daily-spend math stays deterministic in tests.

    ``period_window`` optionally caps the ``spent_minor`` lookup to an
    explicit ``(start, end)`` range. Used by Plan · Budget when the user
    picks a non-current month, so the "Actual" column reflects what
    actually landed inside that calendar month instead of inheriting the
    anchor-window Y-axis of the real today (V.32).
    """
    cats = [c for c in categories_repo.list_all(conn, user_id) if c.direction is Direction.EXPENSE]

    prev_y, prev_m = prev_year_month(year, month)
    prev_start, prev_end = _month_range(prev_y, prev_m)
    year_start = date(year, 1, 1)
    year_end = _month_range(year, 12)[1]

    # Resolve budgets up front so zero-budget months can short-circuit the
    # paycheck-window shift (ADR-0041 keeps those on month-start to preserve
    # the pre-ADR-0041 per-category view).
    budgets_by_cat: dict[int, int | None] = {
        cat.id: resolve_budget(conn, user_id, cat.id, year, month) for cat in cats
    }
    budgeted_total = sum(amount or 0 for amount in budgets_by_cat.values())

    # ADR-0041: per-category ``spent_minor`` sums over the paycheck window
    # ``[last_anchor_date, today]``; analytics windows (prev / year / all)
    # stay on calendar-month windows as backward-looking references.
    month_start = date(year, month, 1)
    if period_window is not None:
        period_start, period_end = period_window
    elif budgeted_total == 0:
        period_start = month_start
        period_end = today
    else:
        anchor_category = preferences_svc.resolve_income_anchor_category(conn, user_id)
        period_start = _resolve_period_start(conn, user_id, today, year, month, anchor_category)
        period_end = today
    this_txns = _expense_txns_in_range(conn, user_id, period_start, period_end)
    prev_txns = _expense_txns_in_range(conn, user_id, prev_start, prev_end)
    year_txns = _expense_txns_in_range(conn, user_id, year_start, year_end)
    all_txns = _all_expense_txns(conn, user_id)

    spent_this = _sum_by_category(this_txns)
    spent_prev = _sum_by_category(prev_txns)
    year_sums = _sum_by_category(year_txns)
    overall_sum = _sum_by_category(all_txns)
    overall_mo = _active_month_counts(all_txns)

    elapsed_in_year = month if year_txns else max(month, 1)

    lines: list[CategoryBudgetLine] = []
    for cat in cats:
        budgeted = budgets_by_cat[cat.id]
        spent = spent_this.get(cat.id, 0)
        remaining = (budgeted - spent) if budgeted is not None else None
        avg_overall = _mean_minor(overall_sum.get(cat.id, 0), overall_mo.get(cat.id, 0))
        avg_year = _mean_minor(year_sums.get(cat.id, 0), elapsed_in_year)
        delta_prev = spent - spent_prev.get(cat.id, 0)
        lines.append(
            CategoryBudgetLine(
                category_id=cat.id,
                category_name=cat.name,
                category_direction=cat.direction,
                category_color=cat.color,
                budgeted_minor=budgeted,
                spent_minor=spent,
                remaining_minor=remaining,
                avg_monthly_overall_minor=avg_overall,
                avg_this_year_minor=avg_year,
                delta_vs_prev_month_minor=delta_prev,
            )
        )

    # Budgeted first (False sorts before True), then alphabetical.
    lines.sort(key=lambda line: (line.budgeted_minor is None, line.category_name))

    spent_total = sum(line.spent_minor for line in lines if line.budgeted_minor is not None)
    pre_commit_remaining = sum(line.remaining_minor or 0 for line in lines)

    end_of_month = _month_range(year, month)[1]
    anchor_category_name, next_income_date = _resolve_anchor(
        conn, user_id, today, budgeted_total, end_of_month
    )
    left_daily_spend_minor: int | None = None
    days_until_next_income = max((next_income_date - today).days, 1)

    # ADR-0039/0085: committed = unpromoted planned + active-recurring expense
    # amounts due in [today, next_income_date) in BUDGETED categories only. Zero-budget months keep
    # committed_minor=0 so the dim sub-line renders a flat zero (clearer
    # than hiding).
    if budgeted_total == 0:
        committed_total = 0
        unbudgeted_committed = 0
    else:
        committed_total, unbudgeted_committed = committed_split_in_window(
            conn,
            user_id,
            start=today,
            end=next_income_date,
            today=today,
            budgeted_category_ids=frozenset(
                cat_id for cat_id, amount in budgets_by_cat.items() if amount is not None
            ),
        )

    remaining_total = pre_commit_remaining - committed_total

    totals = MonthTotals(
        budgeted_minor=budgeted_total,
        spent_minor=spent_total,
        committed_minor=committed_total,
        remaining_minor=remaining_total,
        unbudgeted_committed_minor=unbudgeted_committed,
    )

    if budgeted_total != 0:
        left_daily_spend_minor = int(
            (Decimal(totals.remaining_minor) / Decimal(days_until_next_income)).quantize(
                Decimal("1"), rounding=ROUND_HALF_EVEN
            )
        )

    return MonthSummary(
        year=year,
        month=month,
        lines=tuple(lines),
        totals=totals,
        left_daily_spend_minor=left_daily_spend_minor,
        next_income_date=next_income_date,
        days_until_next_income=days_until_next_income,
        anchor_category_name=anchor_category_name,
        period_start=period_start,
    )


def yearly_grid(conn: sqlite3.Connection, user_id: int, year: int) -> tuple[YearlyRow, ...]:
    """Return per-category (rows) by Jan..Dec (12 cells) resolved budgets."""
    cats = [c for c in categories_repo.list_all(conn, user_id) if c.direction is Direction.EXPENSE]
    defaults_by_cat = {d.category_id: d.amount for d in budgets_repo.list_defaults(conn, user_id)}
    recurring_by_key: dict[tuple[int, int], int] = {
        (r.category_id, r.month): r.amount for r in budgets_repo.list_recurring(conn, user_id)
    }
    one_off_by_key: dict[tuple[int, int], int] = {
        (o.category_id, o.month): o.amount
        for o in budgets_repo.list_one_off(conn, user_id, year=year)
    }

    rows: list[YearlyRow] = []
    for cat in cats:
        cells: list[YearlyCell] = []
        total = 0
        for month in range(1, 13):
            one_off = one_off_by_key.get((cat.id, month))
            if one_off is not None:
                cells.append(YearlyCell(amount_minor=one_off, origin="one_off"))
                total += one_off
                continue
            recurring = recurring_by_key.get((cat.id, month))
            if recurring is not None:
                cells.append(YearlyCell(amount_minor=recurring, origin="recurring"))
                total += recurring
                continue
            default = defaults_by_cat.get(cat.id)
            if default is not None:
                cells.append(YearlyCell(amount_minor=default, origin="default"))
                total += default
                continue
            cells.append(YearlyCell(amount_minor=None, origin="unset"))
        rows.append(
            YearlyRow(
                category_id=cat.id,
                category_name=cat.name,
                category_direction=cat.direction,
                category_color=cat.color,
                cells=tuple(cells),
                total_minor=total,
            )
        )
    rows.sort(key=lambda r: r.category_name.casefold())
    return tuple(rows)


__all__ = [
    "CategoryBudgetLine",
    "MonthSummary",
    "MonthTotals",
    "YearlyCell",
    "YearlyRow",
    "committed_in_window",
    "committed_split_in_window",
    "fiscal_month_for",
    "month_summary",
    "prev_year_month",
    "resolve_budget",
    "resolve_period_start",
    "yearly_grid",
]
