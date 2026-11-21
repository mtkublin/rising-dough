"""Template view-model values for the budget surfaces (T-Q237, Q-039).

Canonical owner of every derived number a budget template prints (left per day,
percent used, remaining after spend, over/under flags, month pickers). Templates
only render these precomputed values: no arithmetic, ``float`` or ``{% set %}``
(ADR-0130 §3.3, G9). Money maths delegates to ``domain.money`` and ``services``;
this module does no I/O and reads no clock (``today`` comes in as an argument).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Final, Literal

from budget_planner.domain.accounts import Account
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.domain.money import percent_of
from budget_planner.services import (
    analytics as analytics_service,
    budget as budget_service,
    today as today_service,
)
from budget_planner.web.today_data import UpcomingRow

MONTH_SHORT: Final[tuple[str, ...]] = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
MONTH_LONG: Final[tuple[str, ...]] = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

_MAX_PCT: Final = 100
_UPCOMING_CAP: Final = 6
_NEXT_WEEK_DAYS: Final = 7
_YEAR_TIERS: Final[Mapping[str, str]] = MappingProxyType(
    {"one_off": "one-off", "recurring": "recurring", "default": "default", "unset": "unset"}
)

DeltaKind = Literal["up", "down", "flat"]


def clamped_percent(part_minor: int, total_minor: int) -> int:
    """Whole percent of ``part`` in ``total`` clamped to 0..100 (bar widths)."""
    return max(0, min(_MAX_PCT, percent_of(part_minor, total_minor)))


def left_per_day(summary: budget_service.MonthSummary) -> int:
    """Remaining budget divided over the days until the next income (not clamped)."""
    return today_service.daily_share_minor(
        summary.totals.remaining_minor, summary.days_until_next_income
    )


def month_name(month: int) -> str:
    """Long English month name for ``month`` (1..12)."""
    return MONTH_LONG[month - 1]


def period_label(year: int, month: int) -> str:
    """``YYYY-MM`` label for a budget month."""
    return f"{year}-{month:02d}"


@dataclass(frozen=True, slots=True)
class MonthOption:
    """One ``<option>`` of the month selector."""

    number: int
    label: str
    is_selected: bool


def month_options(selected: int) -> tuple[MonthOption, ...]:
    """The twelve month options with ``selected`` flagged."""
    return tuple(MonthOption(n, f"{n:02d}", n == selected) for n in range(1, 13))


@dataclass(frozen=True, slots=True)
class BudgetLineView:
    """One category row: service line plus the values the table prints."""

    line: budget_service.CategoryBudgetLine
    budgeted_minor: int
    remaining_after_minor: int
    used_pct: int
    is_over: bool
    delta_kind: DeltaKind


@dataclass(frozen=True, slots=True)
class BudgetView:
    """Everything the budget hero, period bar and category table print."""

    summary: budget_service.MonthSummary
    lines: tuple[BudgetLineView, ...]
    left_per_day_minor: int
    spent_pct: int
    committed_pct: int
    is_over: bool
    period_day: int
    period_total_days: int


def _delta_kind(delta_minor: int) -> DeltaKind:
    if delta_minor > 0:
        return "up"
    if delta_minor < 0:
        return "down"
    return "flat"


def _line_view(line: budget_service.CategoryBudgetLine) -> BudgetLineView:
    budgeted = line.budgeted_minor or 0
    return BudgetLineView(
        line=line,
        budgeted_minor=budgeted,
        remaining_after_minor=budgeted - line.spent_minor,
        used_pct=clamped_percent(line.spent_minor, budgeted),
        is_over=line.spent_minor > budgeted,
        delta_kind=_delta_kind(line.delta_vs_prev_month_minor),
    )


def budget_view(summary: budget_service.MonthSummary, today: date) -> BudgetView:
    """Derive the budget view from a :class:`MonthSummary` (``today`` places the day marker)."""
    totals = summary.totals
    return BudgetView(
        summary=summary,
        lines=tuple(_line_view(line) for line in summary.lines),
        left_per_day_minor=left_per_day(summary),
        spent_pct=clamped_percent(totals.spent_minor, totals.budgeted_minor),
        committed_pct=clamped_percent(totals.committed_minor, totals.budgeted_minor),
        is_over=totals.budgeted_minor > 0 and totals.spent_minor > totals.budgeted_minor,
        period_day=(today - summary.period_start).days + 1,
        period_total_days=(summary.next_income_date - summary.period_start).days or 1,
    )


# --- Today upcoming list -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class UpcomingItem:
    """One Upcoming row with the lookups and flags the template needs."""

    row: UpcomingRow
    row_id: str
    category: Category | None
    account: Account | None
    direction: str
    is_income: bool
    is_planned: bool
    is_overdue: bool
    is_due_today: bool


@dataclass(frozen=True, slots=True)
class UpcomingView:
    """Upcoming list grouped into next-7-days and later, capped for display."""

    next_7: tuple[UpcomingItem, ...]
    later: tuple[UpcomingItem, ...]
    total_count: int
    cap: int
    has_more: bool


def _upcoming_item(
    row: UpcomingRow,
    today: date,
    categories_by_id: Mapping[int, Category],
    accounts_by_id: Mapping[int, Account],
) -> UpcomingItem:
    is_planned = row.kind == "planned"
    row_id = (
        f"upcoming-planned-{row.planned_id}" if is_planned else f"upcoming-recurring-{row.rule_id}"
    )
    category = categories_by_id.get(row.category_id)
    direction = (category.direction if category else Direction.EXPENSE).value
    return UpcomingItem(
        row=row,
        row_id=row_id,
        category=category,
        account=accounts_by_id.get(row.account_id),
        direction=direction,
        is_income=direction == Direction.INCOME.value,
        is_planned=is_planned,
        is_overdue=row.operation_date < today,
        is_due_today=row.operation_date == today,
    )


def upcoming_view(
    upcoming: tuple[UpcomingRow, ...],
    today: date,
    categories_by_id: Mapping[int, Category],
    accounts_by_id: Mapping[int, Account],
) -> UpcomingView:
    """Group, cap and annotate Today's upcoming rows."""
    next_7: list[UpcomingItem] = []
    later: list[UpcomingItem] = []
    for row in upcoming[:_UPCOMING_CAP]:
        item = _upcoming_item(row, today, categories_by_id, accounts_by_id)
        near = (row.operation_date - today).days <= _NEXT_WEEK_DAYS
        (next_7 if near else later).append(item)
    return UpcomingView(
        next_7=tuple(next_7),
        later=tuple(later),
        total_count=len(upcoming),
        cap=_UPCOMING_CAP,
        has_more=len(upcoming) > _UPCOMING_CAP,
    )


# --- Plan header -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MonthCell:
    """One cell of the 12-month picker grid."""

    number: int
    label: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class PlanHeader:
    """Title and period-navigation values for the shared Plan header."""

    title: str
    month_label: str
    year: int
    prev_year: int
    next_year: int
    month: int
    month_cells: tuple[MonthCell, ...]


def plan_header(tab: str, year: int, month: int, year_selected: int | None = None) -> PlanHeader:
    """Header values for ``tab``; ``year_selected`` drives the Year tab."""
    titles = {
        "budget": f"{month_name(month)} budget",
        "year": f"Budget {year_selected if year_selected is not None else year}",
        "forecast": "Projected balance",
        "analytics": "Where it went",
    }
    shown_year = year_selected if year_selected is not None else year
    return PlanHeader(
        title=titles.get(tab, "Plan"),
        month_label=f"{month_name(month)} {year}",
        year=shown_year,
        prev_year=shown_year - 1,
        next_year=shown_year + 1,
        month=month,
        month_cells=tuple(MonthCell(n, MONTH_SHORT[n - 1], n == month) for n in range(1, 13)),
    )


# --- Plan year tab -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class YearCellView:
    """One month cell of a year row."""

    month: int
    month_label: str
    month_initial: str
    amount_minor: int
    tier: str


@dataclass(frozen=True, slots=True)
class YearRowView:
    """One category row of the year heatmap."""

    category_id: int
    category_name: str
    category_direction: Direction
    category_color: str | None
    total_minor: int
    cells: tuple[YearCellView, ...]


@dataclass(frozen=True, slots=True)
class YearView:
    """Year tab rows split into budgeted and unset, plus labels."""

    month_labels: tuple[str, ...]
    with_rows: tuple[YearRowView, ...]
    unset_rows: tuple[YearRowView, ...]
    unset_heading: str


def _year_row(row: budget_service.YearlyRow) -> YearRowView:
    return YearRowView(
        category_id=row.category_id,
        category_name=row.category_name,
        category_direction=row.category_direction,
        category_color=row.category_color,
        total_minor=row.total_minor,
        cells=tuple(
            YearCellView(
                month=i,
                month_label=MONTH_SHORT[i - 1],
                month_initial=MONTH_SHORT[i - 1][0],
                amount_minor=cell.amount_minor or 0,
                tier=_YEAR_TIERS.get(cell.origin, "default"),
            )
            for i, cell in enumerate(row.cells, start=1)
        ),
    )


def year_view(rows: tuple[budget_service.YearlyRow, ...]) -> YearView:
    """Split the yearly grid into rows with a budget and rows without."""
    with_rows = tuple(_year_row(r) for r in rows if r.total_minor)
    unset_rows = tuple(_year_row(r) for r in rows if not r.total_minor)
    noun = "category" if len(unset_rows) == 1 else "categories"
    return YearView(
        month_labels=MONTH_SHORT,
        with_rows=with_rows,
        unset_rows=unset_rows,
        unset_heading=f"Show {len(unset_rows)} {noun} without a budget",
    )


# --- Analytics spend rows ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class SpendRowView:
    """One spend-by-category row with its bar width and 12-month delta."""

    category_id: int
    category_name: str
    amount_minor: int
    bar_pct: int
    has_average: bool
    delta_minor: int
    delta_kind: Literal["over", "under", "flat"]


def spend_rows(
    bundle: analytics_service.AnalyticsBundle, averages: Mapping[int, int]
) -> tuple[SpendRowView, ...]:
    """Spend rows scaled against the largest row, with deltas vs the 12-month average."""
    rows = bundle.spend_by_category
    top = rows[0].amount_minor if rows else 1
    out: list[SpendRowView] = []
    for row in rows:
        avg = averages.get(row.category_id, 0)
        delta = row.amount_minor - avg
        kind: Literal["over", "under", "flat"] = (
            "over" if delta > 0 else "under" if delta < 0 else "flat"
        )
        out.append(
            SpendRowView(
                category_id=row.category_id,
                category_name=row.category_name,
                amount_minor=row.amount_minor,
                bar_pct=percent_of(row.amount_minor, top),
                has_average=avg > 0,
                delta_minor=delta,
                delta_kind=kind,
            )
        )
    return tuple(out)


# --- Override form -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OverridePeriod:
    """Year/month an override form opens on."""

    year: int
    month: int
    label: str


def override_period(month: int, year: int) -> OverridePeriod:
    """The override form's month/year with its short month label."""
    return OverridePeriod(year, month, MONTH_SHORT[month - 1])
