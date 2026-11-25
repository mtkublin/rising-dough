"""Data assembly and view values of the Today surface (T-D50 / ADR-0077, T-UR07).

Account rows, pace tag, upcoming window, the Can-I-afford state, and the values
the Today templates print (hero, period panel, net worth, upcoming groups and
rows). No business logic: services only; arithmetic stays out of the templates.
"""

from __future__ import annotations

import calendar
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Final, Literal

from fastapi import Request

from budget_planner.domain.accounts import Account
from budget_planner.domain.categories import Category
from budget_planner.domain.category_colors import category_color
from budget_planner.domain.enums import Direction
from budget_planner.domain.money import divide_minor_units, format_figure
from budget_planner.repositories import accounts as accounts_repo
from budget_planner.services import (
    balance as balance_service,
    fortune as fortune_service,
    fx as fx_service,
    ledger_totals,
    today as today_service,
    upcoming as upcoming_service,
)
from budget_planner.services.recurring_formula import FormulaFx
from budget_planner.web import view_models as vm
from budget_planner.web.params import positive_amount, query_choice

PaceKind = Literal["on_track", "pacing_high", "over_budget"]

_PACE_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "on_track": "on track",
        "pacing_high": "pacing high",
        "over_budget": "over budget",
    }
)

_WINDOWS: Final[Mapping[str, int | None]] = MappingProxyType({"7": 7, "30": 30, "all": None})
_DEFAULT_WINDOW: Final[str] = "30"


@dataclass(frozen=True, slots=True)
class AccountRow:
    """Per-account row for Panel A."""

    id: int
    name: str
    type: str | None
    currency: str
    balance_minor: int
    balance_base_minor: int


@dataclass(frozen=True, slots=True)
class CurrencyTotal:
    """Per-currency total for Panel A sub-header."""

    currency: str
    total_minor: int


@dataclass(frozen=True, slots=True)
class PaceTag:
    """Pace signal for Panel B — label + semantic kind."""

    kind: PaceKind
    label: str


@dataclass(frozen=True, slots=True)
class UpcomingRow:
    """Normalised row for Panel C (T-121 — planned + recurring).

    ``planned_id`` / ``rule_id`` are mutually exclusive (one is always
    ``None``), set according to ``kind``. ``override_present`` is only
    meaningful for recurring rows (planned rows always set it to False).
    """

    operation_date: date
    description: str
    amount_minor: int
    is_overdue: bool
    kind: str  # "planned" | "recurring" — drives the row's data-kind attribute.
    planned_id: int | None
    rule_id: int | None
    override_present: bool
    is_formula: bool
    category_id: int
    account_id: int
    dest_account_id: int | None


def collect_account_rows(
    conn: sqlite3.Connection,
    user_id: int,
    fx: fx_service.FxConverter,
) -> tuple[tuple[AccountRow, ...], tuple[CurrencyTotal, ...]]:
    """Return (per-account rows, per-currency totals); net worth is ``compute_fortune``."""
    accs = accounts_repo.list_all(conn, user_id)
    per_ccy: dict[str, int] = {}
    native: list[tuple[int, str, str | None, str, int]] = []
    for a in accs:
        bal = balance_service.derive_balance(conn, user_id, a.id)
        per_ccy[a.currency] = per_ccy.get(a.currency, 0) + bal
        native.append((a.id, a.name, a.type, a.currency, bal))

    rows = tuple(
        AccountRow(
            id=aid,
            name=name,
            type=atype,
            currency=ccy,
            balance_minor=bal,
            balance_base_minor=fx.to_base(bal, ccy),
        )
        for (aid, name, atype, ccy, bal) in native
    )
    totals = tuple(
        CurrencyTotal(currency=ccy, total_minor=total) for ccy, total in sorted(per_ccy.items())
    )
    return rows, totals


def pace_tag(spent: int, budgeted: int, today: date, year: int, month: int) -> PaceTag:
    """Compute pace signal from totals + elapsed fraction of the month."""
    if budgeted <= 0:
        return PaceTag(kind="on_track", label=_PACE_LABELS["on_track"])
    if spent > budgeted:
        return PaceTag(kind="over_budget", label=_PACE_LABELS["over_budget"])
    days_in_month = calendar.monthrange(year, month)[1]
    elapsed = today.day if (today.year == year and today.month == month) else days_in_month
    expected = divide_minor_units(budgeted * elapsed, days_in_month)
    if spent > expected:
        return PaceTag(kind="pacing_high", label=_PACE_LABELS["pacing_high"])
    return PaceTag(kind="on_track", label=_PACE_LABELS["on_track"])


def window_from(request: Request) -> tuple[str, int | None]:
    """Parse ``?window=`` → (label, days); absent or empty is the default, unknown raises."""
    raw = query_choice("window", request.query_params.get("window"), tuple(_WINDOWS))
    label = raw or _DEFAULT_WINDOW
    return label, _WINDOWS[label]


def list_upcoming(
    conn: sqlite3.Connection,
    user_id: int,
    today: date,
    window_days: int | None,
    fx: FormulaFx,
) -> tuple[UpcomingRow, ...]:
    """Return the Panel C row set — planned one-offs + recurring next_due.

    T-119: delegates to ``services.upcoming.list_upcoming`` which composes
    persisted planned rows (``promoted=False``) with active recurring
    rules (ADR-0038) and applies ``next_due`` overrides. ``window_days``
    forwards unchanged.
    """
    items = upcoming_service.list_upcoming(
        conn, user_id, today=today, window_days=window_days, fx=fx
    )
    return tuple(
        UpcomingRow(
            operation_date=item.effective_date,
            description=item.description,
            amount_minor=item.amount_minor,
            is_overdue=item.is_overdue,
            kind=item.kind,
            planned_id=item.planned_id,
            rule_id=item.rule_id,
            override_present=item.override_present,
            is_formula=item.is_formula,
            category_id=item.category_id,
            account_id=item.account_id,
            dest_account_id=item.dest_account_id,
        )
        for item in items
    )


@dataclass(frozen=True, slots=True)
class AffordState:
    """Outcome of one Can-I-afford request: nothing typed, invalid, or a result."""

    typed: bool
    amount_minor: int | None
    result: today_service.AffordResult | None

    @property
    def invalid(self) -> bool:
        """True when something was typed that is not a positive amount."""
        return self.typed and self.amount_minor is None


def afford_state(
    conn: sqlite3.Connection,
    user_id: int,
    today: date,
    raw_amount: str,
    *,
    base_currency: str,
    display_timezone: str,
) -> AffordState:
    """Parse ``raw_amount`` and, when it is a positive amount, recompute the per-day figure."""
    typed = bool(raw_amount.strip())
    amount_minor, error = positive_amount(raw_amount, base_currency)
    if amount_minor is None or error is not None:
        return AffordState(typed=typed, amount_minor=None, result=None)
    result = today_service.afford(
        conn,
        user_id,
        today,
        amount_minor,
        base_currency=base_currency,
        display_timezone=display_timezone,
    )
    return AffordState(typed=typed, amount_minor=amount_minor, result=result)


# --- Today page view values (T-UR07, ADR-0107 section 5) --------------------------

_HEX_COLOR: Final = re.compile(r"#[0-9a-f]{6}")
_PACE_STATUS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "on_track": "● on track",
        "pacing_high": "▲ over pace",
        "over_budget": "▲ over budget",
    }
)
_ROW_CLASSES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "overdue": "rd-upcoming__row rd-upcoming__row--overdue",
        "due": "rd-upcoming__row rd-upcoming__row--due",
        "upcoming": "rd-upcoming__row",
    }
)
_WINDOW_HEADINGS: Final[Mapping[str, str]] = MappingProxyType(
    {"7": "NEXT 7 DAYS", "30": "NEXT 30 DAYS", "all": "LATER"}
)


def _day_month_upper(day: date, *, padded: bool) -> str:
    """``07 NOV`` (row dates, padded) or ``7 NOV`` (the period caption)."""
    number = f"{day.day:02d}" if padded else str(day.day)
    return f"{number} {vm.MONTH_SHORT[day.month - 1].upper()}"


def _count_noun(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


@dataclass(frozen=True, slots=True)
class TodayBar:
    """Hero period bar: ``solid`` (spent then committed cells) + ``remainder`` run + label."""

    modifier: str
    solid: str
    remainder: str
    remainder_class: str
    label: str


def _today_bar(budget: vm.BudgetView) -> TodayBar:
    totals = budget.summary.totals
    if totals.budgeted_minor <= 0 or budget.is_over:
        spans = vm.bar_spans(
            budget.spent_pct,
            vm.HERO_BAR_CELLS,
            is_over=budget.is_over,
            has_budget=totals.budgeted_minor > 0,
            min_one=True,
        )
        return TodayBar(
            spans.modifier, spans.filled, spans.remainder, spans.remainder_class, spans.label
        )
    committed_cells = 0
    if totals.committed_minor > 0:
        committed_cells = min(
            vm.bar_cells(budget.committed_pct, vm.HERO_BAR_CELLS, min_one=True).filled,
            budget.cells.empty,
        )
    left_pct = vm.clamped_percent(totals.remaining_minor, totals.budgeted_minor)
    return TodayBar(
        modifier="",
        solid=vm.BAR_FILLED * budget.cells.filled + vm.BAR_REST * committed_cells,
        remainder=vm.BAR_LEFT * (budget.cells.empty - committed_cells),
        remainder_class="rd-bar__left",
        label=vm.bar_aria_label(budget.spent_pct, left_pct),
    )


@dataclass(frozen=True, slots=True)
class TodayStat:
    """One ``dt`` / ``dd`` pair of the period stats."""

    label: str
    value: str


@dataclass(frozen=True, slots=True)
class TodayView:
    """Every printed value of the Today hero, period panel and net-worth block."""

    figure: str
    fit: vm.HeroFit
    status_text: str
    status_over: bool
    note_long: str
    note_short: str
    caption: str
    bar: TodayBar
    stats: tuple[TodayStat, ...]
    net_total: str
    net_assets: str
    net_liabilities: str
    accounts_link: str


def today_view(
    budget: vm.BudgetView,
    pace: PaceTag,
    fortune: fortune_service.FortuneTotals,
    account_count: int,
    base_currency: str,
) -> TodayView:
    """Derive the Today page values from the budget view, pace tag and fortune totals."""
    summary = budget.summary
    totals = summary.totals
    days = _count_noun(summary.days_until_next_income, "day")
    anchor = summary.anchor_category_name
    until = vm.day_month(summary.next_income_date)
    long_who = f"next income ({anchor}, {until})" if anchor else f"next income ({until})"
    short_who = f"{anchor.lower()} ({until})" if anchor else f"next income ({until})"
    liabilities = -fortune.liabilities_base

    def fmt(minor: int) -> str:
        return format_figure(minor, base_currency)

    return TodayView(
        figure=fmt(budget.left_per_day_minor),
        fit=vm.hero_fit(budget.left_per_day_minor, base_currency),
        status_text=_PACE_STATUS[pace.kind],
        status_over=pace.kind != "on_track",
        note_long=f"{days} until {long_who}",
        note_short=f"{days} until {short_who}",
        caption=(
            f"PERIOD · {_day_month_upper(budget.period_start, padded=False)} → "
            f"{_day_month_upper(budget.period_end, padded=False)} · "
            f"DAY {budget.period_day} OF {budget.period_total_days}"
        ),
        bar=_today_bar(budget),
        stats=(
            TodayStat("spent", fmt(totals.spent_minor)),
            TodayStat("committed ▒", fmt(totals.committed_minor)),
            TodayStat("left", fmt(totals.remaining_minor)),
            TodayStat("of", fmt(totals.budgeted_minor)),
        ),
        net_total=fmt(fortune.net_base),
        net_assets=fmt(fortune.assets_base),
        net_liabilities=fmt(liabilities),
        accounts_link=f"all {account_count} accounts →",
    )


@dataclass(frozen=True, slots=True)
class AffordView:
    """The Can-I-afford result line: over (red) or a per-day figure with its delta."""

    is_over: bool
    per_day: str
    over_by: str
    delta_arrow: str
    delta: str


def afford_view(result: today_service.AffordResult, base_currency: str) -> AffordView:
    """Result values: over shows the unclamped per-day and the over amount (ADR-0151)."""
    is_over = result.over_minor > 0
    shown = result.unclamped_per_day_minor if is_over else result.per_day_minor
    return AffordView(
        is_over=is_over,
        per_day=format_figure(shown, base_currency),
        over_by=format_figure(result.over_minor, base_currency),
        delta_arrow="↓" if result.delta_minor < 0 else "↑",
        delta=format_figure(abs(result.delta_minor), base_currency),
    )


@dataclass(frozen=True, slots=True)
class UpcomingRowView:
    """One Today upcoming row: the item plus its printed texts."""

    item: vm.UpcomingItem
    status: str
    row_class: str
    date_text: str
    flag: str
    amount_text: str
    currency: str
    cat_color: str
    color_rule: str
    menu_title: str
    menu_sub: str
    occurrence: str


@dataclass(frozen=True, slots=True)
class UpcomingGroup:
    """A group heading (overdue, due today, next N days) and its rows."""

    key: str
    heading: str
    rows: tuple[UpcomingRowView, ...]


@dataclass(frozen=True, slots=True)
class TodayUpcoming:
    """The upcoming list: groups, footer counts, ``promote all due`` flag, custom hue rules."""

    groups: tuple[UpcomingGroup, ...]
    total_count: int
    shown_count: int
    has_more: bool
    has_due: bool
    color_rules: str


def _status_key(item: vm.UpcomingItem) -> str:
    if item.is_overdue:
        return "overdue"
    return "due" if item.is_due_today else "upcoming"


def _category_hue(category: Category | None) -> tuple[str, str]:
    """(named hue, custom colour rule) of a category chip; empty when it has no colour."""
    if category is None or not category.color:
        return "", ""
    colour = category_color(category.color)
    rule = colour.rule if colour.custom and _HEX_COLOR.fullmatch(category.color.lower()) else ""
    return colour.name or "", rule


def _row_view(item: vm.UpcomingItem, today: date, base_currency: str) -> UpcomingRowView:
    status = ledger_totals.planned_status(item.row.operation_date, today)
    date_text = _day_month_upper(item.row.operation_date, padded=True)
    is_expense = item.direction == Direction.EXPENSE.value
    # The account owns the currency; the base currency only stands in when the account is gone.
    currency = item.account.currency if item.account else base_currency
    amount = format_figure(
        -item.row.amount_minor if is_expense else item.row.amount_minor,
        currency,
        plus=item.is_income,
    )
    cat_color, color_rule = _category_hue(item.category)
    account = item.account.name if item.account else ""
    return UpcomingRowView(
        item=item,
        status=_status_key(item),
        row_class=_ROW_CLASSES[_status_key(item)],
        date_text=date_text,
        flag=f"▲ overdue {_count_noun(status.days, 'day')}" if item.is_overdue else "",
        amount_text=amount,
        currency=currency,
        cat_color=cat_color,
        color_rule=color_rule,
        menu_title=f"{item.row.description} · {amount} {currency}",
        menu_sub=f"{date_text} · {account}" if account else date_text,
        occurrence=item.row.operation_date.isoformat(),
    )


def today_upcoming(
    upcoming: tuple[UpcomingRow, ...],
    today: date,
    categories_by_id: Mapping[int, Category],
    accounts_by_id: Mapping[int, Account],
    *,
    base_currency: str,
    window_label: str,
) -> TodayUpcoming:
    """Overdue, due-today and next-N-days groups; only the next-N-days rows are capped at 6.

    Flagged rows (overdue, due today) are always listed, as in the handoff board; the footer
    reads "showing <upcoming rows listed> of <all pending items>".
    """
    flagged = [row for row in upcoming if row.operation_date <= today]
    later = [row for row in upcoming if row.operation_date > today][: vm.UPCOMING_CAP]
    shown = tuple(
        _row_view(
            vm.upcoming_item(row, today, categories_by_id, accounts_by_id), today, base_currency
        )
        for row in (*flagged, *later)
    )
    headed = (
        ("overdue", "▲ OVERDUE"),
        ("due", "● DUE TODAY"),
        ("upcoming", _WINDOW_HEADINGS[window_label]),
    )
    groups: list[UpcomingGroup] = []
    for key, heading in headed:
        rows = tuple(r for r in shown if r.status == key)
        if rows:
            full = heading if key == "upcoming" else f"{heading} · {len(rows)}"
            groups.append(UpcomingGroup(key=key, heading=full, rows=rows))
    return TodayUpcoming(
        groups=tuple(groups),
        total_count=len(upcoming),
        shown_count=len(later),
        has_more=len(upcoming) > len(shown),
        has_due=any(row.operation_date <= today for row in upcoming),
        color_rules="".join(dict.fromkeys(r.color_rule for r in shown if r.color_rule)),
    )


@dataclass(frozen=True, slots=True)
class AffordPanel:
    """The Can-I-afford block of the page: input text, error flag and the result line."""

    input_text: str
    invalid: bool
    message: str
    result: AffordView | None


def afford_panel(state: AffordState, base_currency: str) -> AffordPanel:
    """Input text (grouped, as the handoff shows ``1,800.00``) and the result for ``state``."""
    if state.result is None or state.amount_minor is None:
        return AffordPanel("", state.invalid, today_service.AFFORD_INVALID_MESSAGE, None)
    return AffordPanel(
        format_figure(state.amount_minor, base_currency),
        False,
        "",
        afford_view(state.result, base_currency),
    )
