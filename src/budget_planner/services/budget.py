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

import dataclasses
import datetime as dt
import functools
import logging
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.domain.money import round_div
from budget_planner.domain.periods import (
    MONTHS_IN_YEAR,
    PeriodWindow,
    clamp_day,
    month_bounds,
    next_month_start,
    shift_month,
    window_label_month,
)
from budget_planner.domain.transactions import Transaction, TransactionFilter
from budget_planner.repositories import (
    budgets as budgets_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from budget_planner.services import (
    categories as categories_svc,
    fx as fx_svc,
    income as income_svc,
    preferences as preferences_svc,
    recurring as recurring_svc,
)
from budget_planner.services.aggregates import sum_by_category
from budget_planner.services.budget_lines import (
    CategoryBudgetLine,
    CategorySums,
    build_budget_lines,
)
from budget_planner.services.recurring_formula import formula_ctx_for

logger = logging.getLogger(__name__)


def planned_base_amounts(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    today: dt.date,
    base_currency: str,
) -> Callable[[int, int], int]:
    """Return ``(account_id, amount_minor) -> base-currency minor`` (ADR-0095, ADR-0139).

    Planned / recurring items are future-dated, so the rate is the latest
    cached one on or before ``today`` (never the item's date, never the
    network). Base-currency accounts are untouched. A missing rate raises
    ``FxUnavailableError``; there is no native-amount fallback.
    """
    fx = fx_svc.converter_for(conn, fx_svc.BaseCurrency(base_currency), today)
    # Planned rows on soft-deleted accounts are filtered at the source (ADR-0136).
    ccy_by_account = fx_svc.currency_by_account(conn, user_id)

    def base_of(account_id: int, amount_minor: int) -> int:
        return fx.to_base(amount_minor, ccy_by_account.get(account_id, fx.base_currency))

    return base_of


def txn_base_amounts(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    today: dt.date,
    base_currency: str,
) -> Callable[[Transaction], int]:
    """Return ``txn -> base-currency minor`` for posted transactions (ADR-0095, ADR-0139).

    Per ADR-0006 aggregates use historical rates: each transaction converts at
    the latest cached rate on or before its own ``operation_date`` (cache only,
    no network). A missing rate raises ``FxUnavailableError``.
    """
    fx = fx_svc.converter_for(conn, fx_svc.BaseCurrency(base_currency), today)
    return fx_svc.txn_base_of(fx, fx_svc.currency_by_account(conn, user_id))


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


def pick_tier(
    one_off: int | None, recurring: int | None, default: int | None
) -> tuple[int | None, str]:
    """The one budget-tier rule: one-off, then recurring, then default; zero is a value.

    Returns ``(amount, origin)`` with origin ``"one_off" | "recurring" | "default" | "unset"``.
    """
    if one_off is not None:
        return one_off, "one_off"
    if recurring is not None:
        return recurring, "recurring"
    if default is not None:
        return default, "default"
    return None, "unset"


def resolve_budget(
    conn: sqlite3.Connection,
    user_id: int,
    category_id: int,
    year: int,
    month: int,
) -> int | None:
    """Null-coalesce: one-off → recurring → default. Zero is a valid value."""
    one_off = budgets_repo.get_one_off(conn, user_id, category_id, year, month)
    recurring = budgets_repo.get_recurring(conn, user_id, category_id, month)
    default = budgets_repo.get_default(conn, user_id, category_id)
    return pick_tier(
        one_off.amount if one_off is not None else None,
        recurring.amount if recurring is not None else None,
        default.amount if default is not None else None,
    )[0]


def _expense_txns_in_range(
    conn: sqlite3.Connection, user_id: int, start: date, end: date
) -> list[Transaction]:
    return transactions_repo.list_filtered(
        conn,
        user_id,
        TransactionFilter(
            live_accounts_only=True,
            date_from=start,
            date_to=end,
            directions=(Direction.EXPENSE,),
        ),
    )


def _active_month_counts(txns: list[Transaction]) -> dict[int, int]:
    """Count distinct ``YYYY-MM`` buckets per category (expense direction only)."""
    seen: dict[int, set[str]] = defaultdict(set)
    for t in txns:
        key = f"{t.operation_date.year:04d}-{t.operation_date.month:02d}"
        seen[t.category_id].add(key)
    return {cat_id: len(months) for cat_id, months in seen.items()}


def _all_expense_txns(conn: sqlite3.Connection, user_id: int) -> list[Transaction]:
    return transactions_repo.list_filtered(
        conn, user_id, TransactionFilter(live_accounts_only=True, directions=(Direction.EXPENSE,))
    )


def committed_by_category(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    start: dt.date | None,
    end: dt.date,
    today: dt.date,
    base_currency: str,
    include_overdue: bool = False,
) -> dict[int, int]:
    """Return ``{category_id: committed_minor}`` for ``[start, end)`` in base currency.

    Expense-direction categories only (transit + adjustment + income
    excluded). Sources: unpromoted planned rows and active recurring-rule
    occurrences (overrides applied) - see :func:`committed_in_window`.
    ``start=None`` drops the lower bound so every overdue item counts (ADR-0105);
    ``include_overdue`` adds items dated before ``today`` to a bounded window.
    """
    out: dict[int, int] = defaultdict(int)
    if start is not None and end <= start:
        return out
    base_of = planned_base_amounts(conn, user_id, today=today, base_currency=base_currency)

    items = recurring_svc.pending_occurrences(
        conn,
        user_id,
        fx=formula_ctx_for(conn, user_id, fx_svc.BaseCurrency(base_currency), today),
        start=start,
        end=end,
        today=today,
        include_overdue=start is None or include_overdue,
        directions=(Direction.EXPENSE,),
    )
    for item in items:
        out[item.category_id] += base_of(item.account_id, item.amount)
    return out


def committed_in_window(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    start: dt.date | None,
    end: dt.date,
    today: dt.date,
    base_currency: str,
) -> int:
    """Return the committed-minor sum for ``[start, end)`` over ALL expense categories.

    Composes unpromoted planned expenses and active recurring-rule expense
    occurrences (``state=skipped`` drops, ``state=overridden`` merges).
    Returns ``0`` when ``end <= start``; ``start=None`` means unbounded
    (all overdue items, ADR-0105). This is the unfiltered total; the
    budget "left" math uses :func:`committed_split_in_window` (ADR-0085).
    """
    by_cat = committed_by_category(
        conn, user_id, start=start, end=end, today=today, base_currency=base_currency
    )
    return sum(by_cat.values())


def committed_split_in_window(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    start: dt.date | None,
    end: dt.date,
    budgeted_category_ids: frozenset[int],
    today: dt.date,
    base_currency: str,
) -> tuple[int, int]:
    """Return ``(budgeted_committed, unbudgeted_committed)`` for ``[start, end)``.

    ADR-0085: only commitments in categories with a resolved budget reduce
    "left"; the rest is surfaced as an informational figure.
    """
    by_cat = committed_by_category(
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
    fallback_end: date,
) -> tuple[str | None, date]:
    """Return (anchor_name, next_income_date) for the daily-spend math.

    ``next_income_date`` is the exclusive end of the period (ADR-0138).
    Zero-budget months and missing/stale anchors fall back to
    ``fallback_end``, the first day of the next month (half-open window).
    Pulled out of ``month_summary`` to keep its statement count under PLR0915.
    """
    if budgeted_total == 0:
        return None, fallback_end
    anchor = preferences_svc.resolve_income_anchor_category(conn, user_id)
    if anchor is None:
        return None, fallback_end
    hit = income_svc.next_anchor_date(conn, user_id, anchor.id, after=today)
    if hit is None:
        return None, fallback_end
    return anchor.name, hit


def fiscal_month_for(conn: sqlite3.Connection, user_id: int, today: date) -> tuple[int, int]:
    """Return the ``(year, month)`` label of the cycle containing ``today``.

    ADR-0138: the period starts at the most recent landed anchor income and is
    labelled by the calendar month holding most of its days (tie: later month).
    """
    anchor_category = preferences_svc.resolve_income_anchor_category(conn, user_id)
    if anchor_category is None:
        return today.year, today.month
    rows = transactions_repo.list_filtered(
        conn,
        user_id,
        TransactionFilter(
            live_accounts_only=True,
            date_to=today,
            category_ids=(anchor_category.id,),
            directions=(Direction.INCOME,),
        ),
    )
    if not rows:
        return today.year, today.month
    start = max(row.operation_date for row in rows)
    end = income_svc.next_anchor_date(conn, user_id, anchor_category.id, after=start)
    if end is None:
        end = clamp_day(*shift_month(start.year, start.month, 1), start.day)
    return window_label_month(PeriodWindow(start=start, end=end))


def _anchor_due_on(conn: sqlite3.Connection, user_id: int, anchor: Category, day: date) -> bool:
    """Return True when the anchor income is scheduled for ``day`` (payday)."""
    hit = income_svc.next_anchor_date(conn, user_id, anchor.id, after=day - dt.timedelta(days=1))
    return hit == day


def _resolve_period_start(
    conn: sqlite3.Connection,
    user_id: int,
    *,
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
    if _anchor_due_on(conn, user_id, anchor_category, today):
        return today  # payday opens the new period (ADR-0138, OQ-14)
    rows = transactions_repo.list_filtered(
        conn,
        user_id,
        TransactionFilter(
            live_accounts_only=True,
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
    return _resolve_period_start(
        conn, user_id, today=today, year=today.year, month=today.month, anchor_category=anchor
    )


def month_summary(
    conn: sqlite3.Connection,
    user_id: int,
    year: int,
    month: int,
    *,
    today: date,
    base_currency: str,
    period_window: tuple[date, date] | None = None,
    display_timezone: str,
) -> MonthSummary:
    """Build the per-category spent / budgeted / remaining view + analytics.

    Lines are the expense categories that reserve budget in the month (live, or archived later;
    ADR-0136, T-Q279); totals exclude unbudgeted lines. ``today`` is injected (ADR-0007).
    ``period_window`` caps the ``spent_minor`` lookup to an explicit ``(start, end)`` range
    (Plan · Budget for a non-current month; V.32).
    """
    ctx = _SummaryCtx(conn, user_id, year, month, today, base_currency)
    cats = categories_svc.budgeted_expense_categories(
        conn, user_id, year, month, display_timezone=display_timezone
    )
    # Budgets first: zero-budget months skip the paycheck-window shift (ADR-0041).
    budgets_by_cat: dict[int, int | None] = {
        cat.id: resolve_budget(conn, user_id, cat.id, year, month) for cat in cats
    }
    budgeted_total = sum(amount or 0 for amount in budgets_by_cat.values())

    period = _summary_period(ctx, budgeted_total, period_window)
    lines = build_budget_lines(cats, budgets_by_cat, _category_sums(ctx, period))
    anchor_category_name, next_income_date = _resolve_anchor(
        conn, user_id, today, budgeted_total, next_month_start(year, month)
    )
    days_until_next_income = max((next_income_date - today).days, 1)
    totals = _month_totals(ctx, lines, budgets_by_cat, budgeted_total, next_income_date)
    return MonthSummary(
        year=year,
        month=month,
        lines=tuple(lines),
        totals=totals,
        left_daily_spend_minor=(
            round_div(totals.remaining_minor, days_until_next_income)
            if budgeted_total != 0
            else None
        ),
        next_income_date=next_income_date,
        days_until_next_income=days_until_next_income,
        anchor_category_name=anchor_category_name,
        period_start=period[0],
    )


@dataclass(frozen=True, slots=True)
class _SummaryCtx:
    """The read context shared by the ``month_summary`` steps."""

    conn: sqlite3.Connection
    user_id: int
    year: int
    month: int
    today: date
    base_currency: str


def _summary_period(
    ctx: _SummaryCtx, budgeted_total: int, period_window: tuple[date, date] | None
) -> tuple[date, date]:
    """The ``spent_minor`` window (ADR-0041): explicit, month-start, or paycheck window."""
    if period_window is not None:
        return period_window
    if budgeted_total == 0:
        return date(ctx.year, ctx.month, 1), ctx.today
    anchor_category = preferences_svc.resolve_income_anchor_category(ctx.conn, ctx.user_id)
    start = _resolve_period_start(
        ctx.conn,
        ctx.user_id,
        today=ctx.today,
        year=ctx.year,
        month=ctx.month,
        anchor_category=anchor_category,
    )
    return start, ctx.today


def _category_sums(ctx: _SummaryCtx, period: tuple[date, date]) -> CategorySums:
    """Sum expenses per category over the period, previous month, year and all time.

    Analytics windows (prev / year / all) stay on calendar months as
    backward-looking references (ADR-0041).
    """
    conn, user_id = ctx.conn, ctx.user_id
    prev_start, prev_end = month_bounds(*shift_month(ctx.year, ctx.month, -1))
    year_end = month_bounds(ctx.year, 12)[1]
    this_txns = _expense_txns_in_range(conn, user_id, *period)
    prev_txns = _expense_txns_in_range(conn, user_id, prev_start, prev_end)
    year_txns = _expense_txns_in_range(conn, user_id, date(ctx.year, 1, 1), year_end)
    all_txns = _all_expense_txns(conn, user_id)

    txn_base = txn_base_amounts(conn, user_id, today=ctx.today, base_currency=ctx.base_currency)
    return CategorySums(
        spent_this=sum_by_category(this_txns, txn_base),
        spent_prev=sum_by_category(prev_txns, txn_base),
        year_sums=sum_by_category(year_txns, txn_base),
        overall_sum=sum_by_category(all_txns, txn_base),
        overall_months=_active_month_counts(all_txns),
        elapsed_in_year=ctx.month if year_txns else max(ctx.month, 1),
    )


def _month_totals(
    ctx: _SummaryCtx,
    lines: Sequence[CategoryBudgetLine],
    budgets_by_cat: Mapping[int, int | None],
    budgeted_total: int,
    next_income_date: date,
) -> MonthTotals:
    """Totals over the lines, net of what is committed before ``next_income_date``.

    ADR-0039/0085/0105: committed = unpromoted planned + active-recurring
    expense amounts (no lower bound: every overdue item counts) in BUDGETED
    categories only. Zero-budget months keep committed_minor=0 so the dim
    sub-line renders a flat zero (clearer than hiding).
    """
    committed, unbudgeted_committed = 0, 0
    if budgeted_total != 0:
        committed, unbudgeted_committed = committed_split_in_window(
            ctx.conn,
            ctx.user_id,
            start=None,
            end=next_income_date,
            today=ctx.today,
            base_currency=ctx.base_currency,
            budgeted_category_ids=frozenset(
                cat_id for cat_id, amount in budgets_by_cat.items() if amount is not None
            ),
        )
    return MonthTotals(
        budgeted_minor=budgeted_total,
        spent_minor=sum(line.spent_minor for line in lines if line.budgeted_minor is not None),
        committed_minor=committed,
        remaining_minor=sum(line.remaining_minor or 0 for line in lines) - committed,
        unbudgeted_committed_minor=unbudgeted_committed,
    )


@dataclass(frozen=True, slots=True)
class PickerMonth:
    """The month selected on the Plan page plus its neighbours (ADR-0064)."""

    year: int
    month: int
    fiscal_year: int
    fiscal_month: int
    prev_year: int
    prev_month: int
    next_year: int
    next_month: int

    @property
    def is_fiscal(self) -> bool:
        """Return True when the selection is the current fiscal cycle."""
        return (self.year, self.month) == (self.fiscal_year, self.fiscal_month)


def _parse_picker_month(
    year_raw: str | None, month_raw: str | None, fallback: tuple[int, int]
) -> tuple[int, int]:
    if not year_raw and not month_raw:
        return fallback
    try:
        year = int(year_raw) if year_raw else fallback[0]
        month = int(month_raw) if month_raw else fallback[1]
    except ValueError:
        return fallback
    if not 1 <= month <= MONTHS_IN_YEAR or not date.min.year <= year <= date.max.year:
        return fallback
    return year, month


def resolve_picker_month(
    conn: sqlite3.Connection,
    user_id: int,
    today: date,
    *,
    year_raw: str | None = None,
    month_raw: str | None = None,
) -> PickerMonth:
    """Resolve the Plan page month: raw ``?year=&month=`` override, else the fiscal cycle."""
    fiscal = fiscal_month_for(conn, user_id, today)
    year, month = _parse_picker_month(year_raw, month_raw, fiscal)
    prev_year, prev_month = shift_month(year, month, -1)
    next_year, next_month = shift_month(year, month, 1)
    return PickerMonth(
        year=year,
        month=month,
        fiscal_year=fiscal[0],
        fiscal_month=fiscal[1],
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
    )


def _anchor_day_for_picker(conn: sqlite3.Connection, user_id: int) -> int:
    """Return the day of month the anchor income recurs on (1 when no monthly rule)."""
    anchor = preferences_svc.resolve_income_anchor_category(conn, user_id)
    if anchor is None:
        return 1
    for rule in recurring_repo.list_rules(conn, user_id, active_only=True):
        if rule.category_id == anchor.id and rule.day_of_month:
            return max(1, rule.day_of_month)
    return 1


def month_summary_for_picker(
    conn: sqlite3.Connection,
    user_id: int,
    picked: PickerMonth,
    today: date,
    *,
    base_currency: str,
    display_timezone: str,
) -> MonthSummary:
    """Return the Plan · Budget summary for the picked month (ADR-0138).

    The fiscal cycle uses the live anchor-window math. Any other month is
    shown over ``[anchor_day(month), anchor_day(month+1))`` with the day
    clamped per month (never capped at 28), committed zeroed (future: nothing
    scheduled; past: already actuals) and spent clamped to that calendar month.
    """
    year, month = picked.year, picked.month
    summarise = functools.partial(
        month_summary,
        conn,
        user_id,
        year,
        month,
        base_currency=base_currency,
        display_timezone=display_timezone,
    )
    if picked.is_fiscal:
        return summarise(today=today)
    month_first, month_last = month_bounds(year, month)
    ref = today.replace(year=year, month=month, day=min(today.day, month_last.day))
    summary = summarise(today=ref, period_window=(month_first, month_last))
    anchor_day = _anchor_day_for_picker(conn, user_id)
    window = PeriodWindow(
        start=clamp_day(year, month, anchor_day),
        end=clamp_day(picked.next_year, picked.next_month, anchor_day),
    )
    days_left = window.length_days if window.end > today else 0
    totals = dataclasses.replace(
        summary.totals,
        committed_minor=0,
        unbudgeted_committed_minor=0,
        remaining_minor=summary.totals.budgeted_minor - summary.totals.spent_minor,
    )
    return dataclasses.replace(
        summary,
        totals=totals,
        period_start=window.start,
        next_income_date=window.end,
        days_until_next_income=days_left,
    )


def yearly_grid_totals(rows: tuple[YearlyRow, ...]) -> tuple[tuple[int, ...], int]:
    """Return ``(per-month column totals, grand total)`` for the yearly grid rows."""
    columns = tuple(
        sum((row.cells[i].amount_minor or 0) for row in rows) for i in range(MONTHS_IN_YEAR)
    )
    return columns, sum(row.total_minor for row in rows)


@dataclass(frozen=True, slots=True)
class _YearlyTiers:
    """The three budget tiers loaded once for the yearly grid."""

    defaults: Mapping[int, int]
    recurring: Mapping[tuple[int, int], int]
    one_off: Mapping[tuple[int, int], int]

    def cell(self, category_id: int, month: int) -> YearlyCell:
        amount, origin = pick_tier(
            self.one_off.get((category_id, month)),
            self.recurring.get((category_id, month)),
            self.defaults.get(category_id),
        )
        return YearlyCell(amount_minor=amount, origin=origin)


def _yearly_row(cat: Category, tiers: _YearlyTiers, reserving: Sequence[bool]) -> YearlyRow:
    """One grid row; months that do not reserve budget show the unset cell."""
    unset = YearlyCell(*pick_tier(None, None, None))
    cells = tuple(
        tiers.cell(cat.id, month) if reserving[month - 1] else unset for month in range(1, 13)
    )
    return YearlyRow(
        category_id=cat.id,
        category_name=cat.name,
        category_direction=cat.direction,
        category_color=cat.color,
        cells=cells,
        total_minor=sum(c.amount_minor or 0 for c in cells),
    )


def yearly_grid(
    conn: sqlite3.Connection,
    user_id: int,
    year: int,
    *,
    display_timezone: str,
) -> tuple[YearlyRow, ...]:
    """Return per-category (rows) by Jan..Dec (12 cells) resolved budgets.

    An archived category keeps its cells before its archive month and has no budget (and no
    row, when none of the year's months reserve it) from then on (ADR-0136, T-Q279).
    """
    tiers = _YearlyTiers(
        defaults={d.category_id: d.amount for d in budgets_repo.list_defaults(conn, user_id)},
        recurring={
            (r.category_id, r.month): r.amount for r in budgets_repo.list_recurring(conn, user_id)
        },
        one_off={
            (o.category_id, o.month): o.amount
            for o in budgets_repo.list_one_off(conn, user_id, year=year)
        },
    )
    rows: list[YearlyRow] = []
    for cat in categories_svc.expense_categories(conn, user_id):
        reserving = [
            categories_svc.reserves_budget(cat, year, month, display_timezone=display_timezone)
            for month in range(1, 13)
        ]
        if any(reserving):
            rows.append(_yearly_row(cat, tiers, reserving))
    rows.sort(key=lambda r: r.category_name.casefold())
    return tuple(rows)


__all__ = [
    "CategoryBudgetLine",
    "MonthSummary",
    "MonthTotals",
    "PickerMonth",
    "YearlyCell",
    "YearlyRow",
    "committed_in_window",
    "committed_split_in_window",
    "fiscal_month_for",
    "month_summary",
    "month_summary_for_picker",
    "pick_tier",
    "resolve_budget",
    "resolve_period_start",
    "resolve_picker_month",
    "yearly_grid",
    "yearly_grid_totals",
]
