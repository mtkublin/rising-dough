"""Template view-model values for the budget surfaces (T-Q237, Q-039).

Canonical owner of every derived number a budget template prints (left per day,
percent used, remaining after spend, over/under flags, month pickers). Templates
only render these precomputed values: no arithmetic, ``float`` or ``{% set %}``
(ADR-0130 §3.3, G9). Money maths delegates to ``domain.money`` and ``services``;
this module does no I/O and reads no clock (``today`` comes in as an argument).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal

from budget_planner.domain.accounts import Account
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.domain.money import format_money, percent_of
from budget_planner.services import (
    analytics as analytics_service,
    budget as budget_service,
    ledger_totals,
    today as today_service,
)
from budget_planner.services.categories import CategoryUsage

if TYPE_CHECKING:
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
UPCOMING_CAP: Final = 6
ROW_BAR_CELLS: Final = 10
"""Block cells in a table-row bar (handoff README: 10 in rows and on phone)."""
HERO_BAR_CELLS: Final = 20
"""Block cells in a hero or desktop share bar (handoff README: 20 wide)."""
_SIGN_MARKS: Final = ("-", "\u2212")
_GROUP_MARKS: Final = (",", ".")
_NEXT_WEEK_DAYS: Final = 7
_YEAR_TIERS: Final[Mapping[str, str]] = MappingProxyType(
    {"one_off": "one-off", "recurring": "recurring", "default": "default", "unset": "unset"}
)

DeltaKind = Literal["up", "down", "flat"]


def clamped_percent(part_minor: int, total_minor: int) -> int:
    """Whole percent of ``part`` in ``total`` clamped to 0..100 (bar widths)."""
    return max(0, min(_MAX_PCT, percent_of(part_minor, total_minor)))


@dataclass(frozen=True, slots=True)
class BarCells:
    """Segmented block bar: ``filled`` + ``empty`` == the bar's cell count."""

    filled: int
    empty: int
    left_pct: int


def bar_cells(
    used_pct: int, cells: int, *, is_over: bool = False, min_one: bool = False
) -> BarCells:
    """Filled/empty cells for a ``cells``-wide bar from a whole ``used_pct`` (0..100).

    Rounding: half up on the already-floored ``used_pct`` (``percent_of`` floors,
    the handoff rounds cells half up: 39 % of 10 -> 4 cells). ``is_over`` fills
    every cell and reports 0 % left. ``min_one`` (handoff 20-cell bar only) shows
    at least one filled cell for any non-zero use. ``left_pct`` is ``100 - used_pct``.
    """
    if is_over:
        return BarCells(filled=cells, empty=0, left_pct=0)
    used = max(0, min(_MAX_PCT, used_pct))
    # Cell i is filled when used% reaches its midpoint: (i + 1/2) * 100 / cells <= used.
    filled = sum(1 for i in range(cells) if (2 * i + 1) * _MAX_PCT <= 2 * used * cells)
    if min_one and used > 0:
        filled = max(filled, 1)
    return BarCells(filled=filled, empty=cells - filled, left_pct=_MAX_PCT - used)


@dataclass(frozen=True, slots=True)
class BarSpans:
    """Block-character bar for the template: modifier class, two text runs, label."""

    modifier: str
    filled: str
    remainder: str
    remainder_class: str
    left_pct: int
    label: str


BAR_FILLED: Final = "\u2588"
BAR_LEFT: Final = "\u2591"
BAR_REST: Final = "\u2592"


_DIRECTION_LABELS: Final[Mapping[Direction, str]] = MappingProxyType(
    {
        Direction.EXPENSE: "\u2193 expense",
        Direction.INCOME: "\u2191 income",
        Direction.TRANSIT: "\u21c4 transit",
        Direction.ADJUSTMENT: "\u00b1 adjustment",
    }
)


def direction_label(direction: Direction | str) -> str:
    """Handoff wording for a category direction, arrow included: ``↓ expense``."""
    return _DIRECTION_LABELS[Direction(direction)]


def bar_aria_label(used_pct: int, left_pct: int) -> str:
    """Handoff wording for a ``role="img"`` bar: ``78 percent spent, 15 percent left``."""
    return f"{used_pct} percent spent, {left_pct} percent left"


def bar_spans(
    used_pct: int,
    cells: int,
    *,
    is_over: bool = False,
    has_budget: bool = True,
    min_one: bool = False,
    share: bool = False,
) -> BarSpans:
    """Block characters for a budget bar (``share=False``) or a share bar (``share=True``).

    Built on ``bar_cells``. Filled cells are full blocks; the remainder is the light
    shade (``.rd-bar__left``) for budget bars and the medium shade (``.rd-bar__rest``)
    for share bars. ``is_over`` -> ``rd-bar--over`` (all filled); ``has_budget=False``
    -> ``rd-bar--none`` (all remainder, label ``no budget``).
    """
    remainder_class = "rd-bar__rest" if share else "rd-bar__left"
    remainder_char = BAR_REST if share else BAR_LEFT
    if not has_budget:
        return BarSpans(
            modifier="rd-bar--none",
            filled="",
            remainder=remainder_char * cells,
            remainder_class=remainder_class,
            left_pct=0,
            label="no budget",
        )
    parts = bar_cells(used_pct, cells, is_over=is_over, min_one=min_one)
    used = used_pct if is_over else _MAX_PCT - parts.left_pct
    return BarSpans(
        modifier="rd-bar--over" if is_over else "",
        filled=BAR_FILLED * parts.filled,
        remainder=remainder_char * parts.empty,
        remainder_class=remainder_class,
        left_pct=parts.left_pct,
        label=bar_aria_label(used, parts.left_pct),
    )


def year_cell_state(origin: str | None, *, editing: bool = False) -> str:
    """``data-state`` of a ``.rd-year-cell``: default|recurring|one-off|unset|editing."""
    if editing:
        return "editing"
    return _YEAR_TIERS.get(origin or "", "default")


@dataclass(frozen=True, slots=True)
class HeroFit:
    """Counts for the hero figure's ``data-digits`` / ``data-marks`` / ``data-signs``."""

    digits: int
    marks: int
    signs: int


def hero_fit(amount_minor: int, currency: str) -> HeroFit:
    """Digit, grouping/decimal mark and sign counts of the formatted amount.

    Counted over ``format_money`` output (the figure the page prints): digits are
    0-9 characters, marks are ``,`` and ``.``, signs are 1 for a negative amount.
    """
    text = format_money(amount_minor, currency)
    return HeroFit(
        digits=sum(ch.isdigit() for ch in text),
        marks=sum(text.count(m) for m in _GROUP_MARKS),
        signs=int(any(text.startswith(m) for m in _SIGN_MARKS)),
    )


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
    left_pct: int
    cells: BarCells
    is_over: bool
    delta_kind: DeltaKind
    has_budget: bool
    over_minor: int
    bar: BarSpans


@dataclass(frozen=True, slots=True)
class BudgetView:
    """Everything the budget hero, period bar and category table print."""

    summary: budget_service.MonthSummary
    lines: tuple[BudgetLineView, ...]
    left_per_day_minor: int
    spent_pct: int
    committed_pct: int
    is_over: bool
    over_count: int
    left_pct: int
    cells: BarCells
    period_start: date
    period_end: date
    period_day: int
    period_total_days: int


def _delta_kind(delta_minor: int) -> DeltaKind:
    if delta_minor > 0:
        return "up"
    if delta_minor < 0:
        return "down"
    return "flat"


def _row_bar(used_pct: int, *, is_over: bool, has_budget: bool) -> BarSpans:
    """Table-row bar; an over-budget row is announced as ``over budget`` (handoff)."""
    spans = bar_spans(used_pct, ROW_BAR_CELLS, is_over=is_over, has_budget=has_budget)
    return replace(spans, label="over budget") if is_over and has_budget else spans


def _line_view(line: budget_service.CategoryBudgetLine) -> BudgetLineView:
    budgeted = line.budgeted_minor or 0
    used_pct = clamped_percent(line.spent_minor, budgeted)
    is_over = line.spent_minor > budgeted
    cells = bar_cells(used_pct, ROW_BAR_CELLS, is_over=is_over)
    return BudgetLineView(
        line=line,
        budgeted_minor=budgeted,
        remaining_after_minor=budgeted - line.spent_minor,
        used_pct=used_pct,
        left_pct=cells.left_pct,
        cells=cells,
        is_over=is_over,
        delta_kind=_delta_kind(line.delta_vs_prev_month_minor),
        has_budget=line.budgeted_minor is not None,
        over_minor=max(0, line.spent_minor - budgeted),
        bar=_row_bar(used_pct, is_over=is_over, has_budget=line.budgeted_minor is not None),
    )


def budget_view(summary: budget_service.MonthSummary, today: date) -> BudgetView:
    """Derive the budget view from a :class:`MonthSummary` (``today`` places the day marker)."""
    totals = summary.totals
    lines = tuple(_line_view(line) for line in summary.lines)
    spent_pct = clamped_percent(totals.spent_minor, totals.budgeted_minor)
    is_over = totals.budgeted_minor > 0 and totals.spent_minor > totals.budgeted_minor
    cells = bar_cells(spent_pct, HERO_BAR_CELLS, is_over=is_over, min_one=True)
    return BudgetView(
        summary=summary,
        lines=lines,
        left_per_day_minor=left_per_day(summary),
        spent_pct=spent_pct,
        committed_pct=clamped_percent(totals.committed_minor, totals.budgeted_minor),
        is_over=is_over,
        over_count=sum(1 for line in lines if line.is_over),
        left_pct=cells.left_pct,
        cells=cells,
        period_start=summary.period_start,
        period_end=summary.next_income_date,
        period_day=(today - summary.period_start).days + 1,
        period_total_days=(summary.next_income_date - summary.period_start).days or 1,
    )


@dataclass(frozen=True, slots=True)
class PickerCell:
    """One link of the period picker: month or year."""

    label: str
    url: str
    current: bool


@dataclass(frozen=True, slots=True)
class PeriodPicker:
    """Inputs of ``popovers/period-picker`` (month kind)."""

    id: str
    is_year: bool
    year: int
    prev_year_url: str
    next_year_url: str
    cells: tuple[PickerCell, ...]
    note: str


@dataclass(frozen=True, slots=True)
class BudgetPeriod:
    """Inputs of ``plan/period-nav`` for the budget tab."""

    label: str
    prev_url: str
    next_url: str
    picker: PeriodPicker


def day_month(day: date) -> str:
    """``7 oct``: the handoff's lower-case day and short month."""
    return f"{day.day} {MONTH_SHORT[day.month - 1].lower()}"


def period_note(month: int, start: date, end: date) -> str:
    """Picker note ``oct = 7 oct -> 7 nov``: the month's income-to-income range."""
    return f"{MONTH_SHORT[month - 1].lower()} = {day_month(start)} \u2192 {day_month(end)}"


def budget_period(
    picked: budget_service.PickerMonth, summary: budget_service.MonthSummary, base_url: str
) -> BudgetPeriod:
    """Period nav and month picker for ``picked``; ``base_url`` ends in a query string."""

    def url(year: int, month: int) -> str:
        return f"{base_url}&year={year}&month={month}"

    picker = PeriodPicker(
        id="period-budget",
        is_year=False,
        year=picked.year,
        prev_year_url=url(picked.year - 1, picked.month),
        next_year_url=url(picked.year + 1, picked.month),
        cells=tuple(
            PickerCell(MONTH_SHORT[n - 1], url(picked.year, n), n == picked.month)
            for n in range(1, 13)
        ),
        note=period_note(picked.month, summary.period_start, summary.next_income_date),
    )
    return BudgetPeriod(
        label=f"{month_name(picked.month)} {picked.year}",
        prev_url=url(picked.prev_year, picked.prev_month),
        next_url=url(picked.next_year, picked.next_month),
        picker=picker,
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
    overdue_count: int
    due_today_count: int
    next_7_count: int
    later_count: int


def upcoming_item(
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
    status = ledger_totals.planned_status(row.operation_date, today).kind
    return UpcomingItem(
        row=row,
        row_id=row_id,
        category=category,
        account=accounts_by_id.get(row.account_id),
        direction=direction,
        is_income=direction == Direction.INCOME.value,
        is_planned=is_planned,
        is_overdue=status is ledger_totals.PlannedStatusKind.OVERDUE,
        is_due_today=status is ledger_totals.PlannedStatusKind.DUE_TODAY,
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
    for row in upcoming[:UPCOMING_CAP]:
        item = upcoming_item(row, today, categories_by_id, accounts_by_id)
        near = (row.operation_date - today).days <= _NEXT_WEEK_DAYS
        (next_7 if near else later).append(item)
    shown = (*next_7, *later)
    return UpcomingView(
        next_7=tuple(next_7),
        later=tuple(later),
        total_count=len(upcoming),
        cap=UPCOMING_CAP,
        has_more=len(upcoming) > UPCOMING_CAP,
        overdue_count=sum(1 for item in shown if item.is_overdue),
        due_today_count=sum(1 for item in shown if item.is_due_today),
        next_7_count=len(next_7),
        later_count=len(later),
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


def category_usage_text(usage: CategoryUsage) -> str | None:
    """Usage line "41 entries · 2 planned · 1 rule"; zero parts omitted, None when all zero."""
    entries, planned, rules = usage.entry_count, usage.planned_count, usage.rule_count
    parts = [
        f"{entries} {'entry' if entries == 1 else 'entries'}" if entries else "",
        f"{planned} planned" if planned else "",
        f"{rules} {'rule' if rules == 1 else 'rules'}" if rules else "",
    ]
    return " · ".join(p for p in parts if p) or None
