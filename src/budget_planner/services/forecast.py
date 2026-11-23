"""Forecast service (T-025, T-126).

Deterministic forward-looking balance projection (ADR-0015). For each day
in ``[today, today + horizon_days]`` the service applies planned-cash
events in operation-date order on top of each account's current derived
balance, then aggregates to ``base_currency`` using TODAY's FX rate held
constant across the horizon (ADR-0006).

T-126 (ADR-0042) introduces a **budget overlay**: synthetic expense cash
events for the per-category per-month residual budget not already covered
by planned transactions or recurring occurrences. The overlay is on by
default; callers may disable it via ``include_budget_overlay=False`` to
exercise the pre-overlay projection in regression tests.

Pure w.r.t. the DB snapshot + FX cache + injected clock. The caller owns
``today`` (routers compute it in the display timezone, ADR-0007) so unit
tests remain tz-independent.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from budget_planner.clock import HasDisplayTimezone
from budget_planner.domain.accounts import Account
from budget_planner.domain.enums import Direction
from budget_planner.domain.periods import month_bounds, shift_month
from budget_planner.repositories import (
    accounts as accounts_repo,
)
from budget_planner.services import (
    balance as balance_svc,
    budget as budget_svc,
    budget_batch,
    categories as categories_svc,
    fx as fx_svc,
    recurring as recurring_svc,
)
from budget_planner.services.forecast_events import CashEvent, collect_events
from budget_planner.services.forecast_overlay import (
    MonthSpan,
    collect_budget_overlay,
    month_inputs,
)
from budget_planner.services.recurring_formula import formula_fx


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountBalancePoint:
    """One account's projected balance on a single horizon day."""

    account_id: int
    on_date: dt.date
    native_minor: int
    base_minor: int


@dataclass(frozen=True, slots=True, kw_only=True)
class DayPoint:
    """All active accounts' projected balances on one horizon day + the base total."""

    on_date: dt.date
    totals_base_minor: int
    by_account: tuple[AccountBalancePoint, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ForecastSeries:
    """Window + per-day projections. ``len(days) == horizon_days + 1``."""

    base_currency: str
    start_date: dt.date
    end_date: dt.date
    days: tuple[DayPoint, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class MonthlyPoint:
    """Per-month forecast aggregate (ADR-0043).

    All amounts are in ``base_currency`` minor units. ``income`` /
    ``expense`` are unsigned sums over cash events landing in the month;
    transits + adjustments are excluded (transits net to zero across
    accounts; planned adjustments are unsupported — see ADR-0011).

    ``planned_budget_base_minor`` is the sum of
    ``services.budget.resolve_budget(cat, year, month)`` across every
    live expense category — the total budget allocated for the month
    regardless of whether planned/recurring events already cover it.
    ``net_base_minor = income - expense - planned_budget``.
    """

    month: dt.date
    income_base_minor: int
    expense_base_minor: int
    planned_budget_base_minor: int
    net_base_minor: int
    end_balance_base_minor: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MonthlySeries:
    """Monthly aggregates over the forecast horizon (ADR-0043)."""

    base_currency: str
    start_month: dt.date
    end_month: dt.date
    months: tuple[MonthlyPoint, ...]


# ---------------------------------------------------------------------------
# anchor
# ---------------------------------------------------------------------------
def _anchor_balances(
    conn: sqlite3.Connection,
    user_id: int,
    today: dt.date,
    accounts: tuple[Account, ...],
) -> dict[int, int]:
    """Day-0 native balance per account via ``services.balance.derive_balances`` (one query)."""
    return balance_svc.as_of_today_many(conn, user_id, accounts, today)


# ---------------------------------------------------------------------------
# day construction
# ---------------------------------------------------------------------------
def _build_day(
    on_date: dt.date,
    accounts: tuple[Account, ...],
    running_native: dict[int, int],
    fx: fx_svc.FxConverter,
) -> DayPoint:
    points = tuple(
        AccountBalancePoint(
            account_id=a.id,
            on_date=on_date,
            native_minor=running_native[a.id],
            base_minor=fx.to_base(running_native[a.id], a.currency),
        )
        for a in accounts
    )
    total = sum(p.base_minor for p in points)
    return DayPoint(on_date=on_date, totals_base_minor=total, by_account=points)


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def forecast(
    conn: sqlite3.Connection,
    user_id: int,
    fx: fx_svc.FxConverter,
    today: dt.date,
    horizon_days: int,
    *,
    include_budget_overlay: bool = True,
    display_timezone: str,
) -> ForecastSeries:
    """Project per-account balances forward ``horizon_days`` days.

    ``today`` is day 0 (routers inject it in the display timezone); ``fx`` is cache-only
    (ADR-0139). ``include_budget_overlay`` adds the ADR-0042 synthetic expense events; pass
    ``False`` for the pre-overlay projection. Returns ``horizon_days + 1`` days.

    Invariants: day 0 equals ``services.balance.derive_balance`` as of ``today``; soft-deleting
    a planned row drops the balance after its date by exactly its signed-leg magnitude; same
    inputs and snapshot give identical output.
    """
    if horizon_days < 0:
        raise ValueError(f"horizon_days must be >= 0, got {horizon_days}")
    end_date = today + dt.timedelta(days=horizon_days)
    active_accounts = tuple(accounts_repo.list_all(conn, user_id))
    if not active_accounts:
        days = _zero_days(today, horizon_days)
    else:
        overlay_account_id = min(a.id for a in active_accounts) if include_budget_overlay else None
        events = _events_by_date(
            conn,
            user_id,
            today=today,
            end_date=end_date,
            primary_account_id=overlay_account_id,
            fx=fx,
            display_timezone=display_timezone,
        )
        days = _roll_days(
            conn,
            user_id,
            today=today,
            horizon_days=horizon_days,
            accounts=active_accounts,
            events=events,
            fx=fx,
        )
    return ForecastSeries(
        base_currency=fx.base_currency, start_date=today, end_date=end_date, days=days
    )


def _zero_days(today: dt.date, horizon_days: int) -> tuple[DayPoint, ...]:
    """No accounts: every day of the horizon is an empty point."""
    return tuple(
        DayPoint(on_date=today + dt.timedelta(days=i), totals_base_minor=0, by_account=())
        for i in range(horizon_days + 1)
    )


def _events_by_date(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    today: dt.date,
    end_date: dt.date,
    primary_account_id: int | None,
    fx: fx_svc.FxConverter,
    display_timezone: str,
) -> dict[dt.date, list[CashEvent]]:
    """Explicit events plus (when ``primary_account_id`` is given) the budget overlay, by date."""
    events = collect_events(conn, user_id, today, end_date, formula_fx(conn, user_id, fx))
    if primary_account_id is None:
        return events
    for ev in collect_budget_overlay(
        conn,
        user_id,
        today=today,
        end_date=end_date,
        primary_account_id=primary_account_id,
        fx=fx,
        display_timezone=display_timezone,
    ):
        events.setdefault(ev.on_date, []).append(ev)
    return events


def _roll_days(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    today: dt.date,
    horizon_days: int,
    accounts: tuple[Account, ...],
    events: dict[dt.date, list[CashEvent]],
    fx: fx_svc.FxConverter,
) -> tuple[DayPoint, ...]:
    """Apply ``events`` day by day on top of the day-0 anchor balances."""
    running_native = dict(_anchor_balances(conn, user_id, today, accounts))
    days: list[DayPoint] = [_build_day(today, accounts, running_native, fx)]
    for offset in range(1, horizon_days + 1):
        on_date = today + dt.timedelta(days=offset)
        for ev in events.get(on_date, ()):
            running_native[ev.account_id] = running_native.get(ev.account_id, 0) + ev.amount_minor
        days.append(_build_day(on_date, accounts, running_native, fx))
    return tuple(days)


def _month_offset(anchor: dt.date, months: int) -> dt.date:
    """Return the first day of ``anchor``'s month shifted by ``months``."""
    return dt.date(*shift_month(anchor.year, anchor.month, months), 1)


def _last_day_of_month(month: dt.date) -> dt.date:
    return month_bounds(month.year, month.month)[1]


def horizon_days_for_months(today: dt.date, horizon_months: int) -> int:
    """Convert a months-horizon into the daily horizon that covers it end-to-end."""
    last_month_start = _month_offset(today, horizon_months - 1)
    end_date = _last_day_of_month(last_month_start)
    return (end_date - today).days


def _current_month_budget_totals(
    conn: sqlite3.Connection,
    user_id: int,
    today: dt.date,
    *,
    base_currency: str,
    fiscal_year: int | None = None,
    fiscal_month: int | None = None,
    display_timezone: str,
) -> budget_svc.MonthTotals | None:
    """Return ``month_summary(fiscal).totals`` or ``None`` if no live categories."""
    y = fiscal_year if fiscal_year is not None else today.year
    m = fiscal_month if fiscal_month is not None else today.month
    summary = budget_svc.month_summary(
        conn,
        user_id,
        y,
        m,
        today=today,
        base_currency=base_currency,
        display_timezone=display_timezone,
    )
    return summary.totals


def _month_spans(months: Sequence[dt.date], today: dt.date) -> list[MonthSpan]:
    """Commit windows starting tomorrow (or the month start, if later) for each month."""
    tomorrow = today + dt.timedelta(days=1)
    return [
        MonthSpan(
            month_start=m,
            window_start=max(tomorrow, m),
            month_end=_last_day_of_month(m),
            include_overdue=max(tomorrow, m) == tomorrow,
        )
        for m in months
    ]


def _planned_budget_per_month(
    conn: sqlite3.Connection,
    user_id: int,
    today: dt.date,
    horizon_months: int,
    *,
    fx: fx_svc.FxConverter,
    start_month: dt.date | None = None,
    display_timezone: str,
) -> dict[dt.date, int]:
    """Return per-month **remaining** budget, clamped at zero.

    For each month ``m`` in the horizon:

    ``remaining(m) = Σ max(resolve_budget(cat, m) - spent_so_far(cat, m) -
                            committed_future(cat, m), 0)``

    across every expense category that reserves budget in ``m`` (archived ones stop from their
    archive month, ADR-0136 / T-Q279; their booked ``spent`` still counts as actuals).

    * ``spent_so_far`` counts actual expense transactions in
      ``[month_start, min(today, month_end)]`` — zero for future months.
    * ``committed_future`` counts unpromoted planned + active recurring
      expense amounts in ``(max(today, month_start - 1 day), month_end]``.
    * The clamp drops categories whose planned/recurring already covers
      (or exceeds) their budget, matching the ADR-0042 overlay semantics
      and the user's "only if remaining is positive" rule.

    Budgets are stored in base currency; ``spent_so_far`` is converted to base (Q-008).
    Budget-period consumption boundaries (ADR-0041) are approximated with
    calendar months here, matching ``collect_budget_overlay``.
    """
    expense_cat_ids = categories_svc.expense_category_ids(conn, user_id)
    anchor_month = start_month if start_month is not None else today.replace(day=1)
    resolve = budget_batch.budget_resolver(conn, user_id, display_timezone=display_timezone)
    months = [_month_offset(anchor_month, offset) for offset in range(horizon_months)]
    spans = _month_spans(months, today)
    inputs = month_inputs(conn, user_id, spans, today=today, fx=fx)
    out: dict[dt.date, int] = {}
    for month, (spent_by_cat, committed_by_cat) in zip(months, inputs, strict=True):
        total = 0
        for cat_id in expense_cat_ids:
            amount = resolve(cat_id, month.year, month.month)
            if amount is None:
                continue
            remaining = amount - spent_by_cat.get(cat_id, 0) - committed_by_cat.get(cat_id, 0)
            if remaining > 0:
                total += remaining
        out[month] = total
    return out


def _month_flow_sums(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    today: dt.date,
    end_date: dt.date,
    accounts: tuple[Account, ...],
    fx: fx_svc.FxConverter,
) -> dict[dt.date, tuple[int, int]]:
    """Sum signed income + expense events per calendar month, in base currency.

    Returns ``{month_first_day: (income_base_minor, expense_base_minor)}``.
    Transits + adjustments are excluded (see MonthlyPoint docstring).
    """
    acct_ccy = {a.id: a.currency for a in accounts}
    sums: dict[dt.date, list[int]] = {}  # month -> [income, expense]

    def _add(on_date: dt.date, idx: int, delta: int) -> None:
        key = on_date.replace(day=1)
        bucket = sums.setdefault(key, [0, 0])
        bucket[idx] += delta

    start = today + dt.timedelta(days=1)
    if start > end_date:
        return {}

    for item in recurring_svc.pending_occurrences(
        conn,
        user_id,
        fx=formula_fx(conn, user_id, fx),
        start=start,
        end=end_date + dt.timedelta(days=1),
        today=today,
        include_overdue=True,
        overdue_on=start,
    ):
        ccy = acct_ccy.get(item.account_id)
        if ccy is None:
            continue
        base = fx.to_base(item.amount, ccy)
        if item.direction is Direction.INCOME:
            _add(item.on_date, 0, base)
        elif item.direction is Direction.EXPENSE:
            _add(item.on_date, 1, base)

    return {month: (bucket[0], bucket[1]) for month, bucket in sums.items()}


def _monthly_table(
    conn: sqlite3.Connection,
    user_id: int,
    fx: fx_svc.FxConverter,
    *,
    today: dt.date,
    start_month: dt.date,
    horizon_months: int,
    display_timezone: str,
) -> tuple[MonthlyPoint, ...]:
    """The monthly rows: daily projection, residual budget per month, flows, chained balances."""
    end_date = _last_day_of_month(_month_offset(start_month, horizon_months - 1))
    series = forecast(
        conn,
        user_id,
        fx,
        today,
        max((end_date - today).days, 0),
        display_timezone=display_timezone,
    )
    planned_budget_by_month = _planned_budget_per_month(
        conn,
        user_id,
        today,
        horizon_months,
        fx=fx,
        start_month=start_month,
        display_timezone=display_timezone,
    )
    accounts = tuple(accounts_repo.list_all(conn, user_id))
    if accounts:
        rows = _monthly_rows(
            conn,
            user_id,
            today=today,
            end_date=end_date,
            accounts=accounts,
            fx=fx,
            start_month=start_month,
            horizon_months=horizon_months,
            opening_balance=series.days[0].totals_base_minor,
            planned_budget_by_month=planned_budget_by_month,
            display_timezone=display_timezone,
        )
    else:
        rows = _zero_flow_rows(start_month, horizon_months, planned_budget_by_month)
    return rows


def forecast_monthly(
    conn: sqlite3.Connection,
    user_id: int,
    fx: fx_svc.FxConverter,
    today: dt.date,
    horizon_months: int,
    *,
    display_timezone: str,
) -> MonthlySeries:
    """Monthly aggregate projection over ``horizon_months`` months (ADR-0043).

    One row per month from the fiscal month: income, expense, ``net`` and the projected
    month-end fortune. End balances chain from today's net worth (ADR-0042 overlay enabled in
    the daily projection); income/expense come from the explicit event stream only (no overlay);
    ``planned_budget_base_minor`` is the per-month residual budget.
    """
    if horizon_months < 1:
        raise ValueError(f"horizon_months must be >= 1, got {horizon_months}")
    # Start at the fiscal cycle, not the calendar month, so the "current" row lines up with
    # the Plan hub's landing month (ADR-0064).
    fiscal_year, fiscal_month = budget_svc.fiscal_month_for(conn, user_id, today)
    start_month = dt.date(fiscal_year, fiscal_month, 1)
    last_month = _month_offset(start_month, horizon_months - 1)
    rows = _monthly_table(
        conn,
        user_id,
        fx,
        today=today,
        start_month=start_month,
        horizon_months=horizon_months,
        display_timezone=display_timezone,
    )
    return MonthlySeries(
        base_currency=fx.base_currency,
        start_month=start_month,
        end_month=last_month,
        months=rows,
    )


def _zero_flow_rows(
    start_month: dt.date, horizon_months: int, planned_budget_by_month: dict[dt.date, int]
) -> tuple[MonthlyPoint, ...]:
    """No accounts: only the planned budget moves (all balances zero)."""
    return tuple(
        MonthlyPoint(
            month=month,
            income_base_minor=0,
            expense_base_minor=0,
            planned_budget_base_minor=planned_budget_by_month[month],
            net_base_minor=-planned_budget_by_month[month],
            end_balance_base_minor=0,
        )
        for month in (_month_offset(start_month, offset) for offset in range(horizon_months))
    )


def _monthly_rows(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    today: dt.date,
    end_date: dt.date,
    accounts: tuple[Account, ...],
    fx: fx_svc.FxConverter,
    start_month: dt.date,
    horizon_months: int,
    opening_balance: int,
    planned_budget_by_month: dict[dt.date, int],
    display_timezone: str,
) -> tuple[MonthlyPoint, ...]:
    """Load the flow sums and the fiscal-month totals, then chain the rows."""
    flows = _month_flow_sums(
        conn, user_id, today=today, end_date=end_date, accounts=accounts, fx=fx
    )
    fiscal_totals = _current_month_budget_totals(
        conn,
        user_id,
        today,
        base_currency=fx.base_currency,
        fiscal_year=start_month.year,
        fiscal_month=start_month.month,
        display_timezone=display_timezone,
    )
    return _chain_rows(
        start_month=start_month,
        horizon_months=horizon_months,
        opening_balance=opening_balance,
        flows=flows,
        planned_budget_by_month=planned_budget_by_month,
        current_month_totals=fiscal_totals,
    )


def _chain_rows(
    *,
    start_month: dt.date,
    horizon_months: int,
    opening_balance: int,
    flows: dict[dt.date, tuple[int, int]],
    planned_budget_by_month: dict[dt.date, int],
    current_month_totals: budget_svc.MonthTotals | None,
) -> tuple[MonthlyPoint, ...]:
    """One row per month; ``start_month`` is the fiscal row.

    EOM is a running chain anchored at today's net worth, so each row
    answers "what will my balance be at the end of this row's period
    given the plan it displays?". The identity previous_EOM + Net = EOM
    is the user-visible contract: mixing daily-projection EOM for
    non-fiscal rows with current+Net for the fiscal row broke that
    contract across the fiscal/calendar seam.
    """
    running_balance = opening_balance
    rows: list[MonthlyPoint] = []
    for offset in range(horizon_months):
        month = _month_offset(start_month, offset)
        income, expense = flows.get(month, (0, 0))
        if month == start_month and current_month_totals is not None:
            # Current fiscal period reuses services.budget.month_summary so the
            # Forecast table lines up with the Budget page + Overview panel.
            # ADR-0085: unbudgeted bills still leave the account.
            expense = (
                current_month_totals.committed_minor
                + current_month_totals.unbudgeted_committed_minor
            )
            planned_budget = max(current_month_totals.remaining_minor, 0)
        else:
            planned_budget = planned_budget_by_month[month]
        net = income - expense - planned_budget
        running_balance += net
        rows.append(
            MonthlyPoint(
                month=month,
                income_base_minor=income,
                expense_base_minor=expense,
                planned_budget_base_minor=planned_budget,
                net_base_minor=net,
                end_balance_base_minor=running_balance,
            )
        )
    return tuple(rows)


@dataclass(frozen=True, slots=True, kw_only=True)
class MonthlyProjectionPoint:
    """Template-friendly projection point for the Plan · Forecast chart.

    One entry per calendar month in the horizon. ``end_balance_minor`` is the
    projected end-of-month fortune; the plan router converts it to chart
    geometry. ``label`` is a short month label suitable for the x-axis.

    ADR-0056 Plan · Forecast reskin adds the per-month flow aggregates so
    the inline table beneath the chart does not need a second service call.
    All *_minor fields are in base-currency minor units.
    """

    month: dt.date
    label: str
    income_minor: int = 0
    expense_minor: int = 0
    planned_budget_minor: int = 0
    net_minor: int = 0
    end_balance_minor: int = 0


class SettingsSlice(fx_svc.HasBaseCurrency, HasDisplayTimezone, Protocol):
    """The slice of ``Settings`` the monthly forecast needs."""


def monthly_for_settings(
    conn: sqlite3.Connection,
    user_id: int,
    settings: SettingsSlice,
    today: dt.date,
    horizon_months: int,
) -> MonthlySeries:
    """:func:`forecast_monthly` with the request's cache-only converter (ADR-0139)."""
    return forecast_monthly(
        conn,
        user_id,
        fx_svc.converter_for(conn, settings, today),
        today,
        horizon_months,
        display_timezone=settings.display_timezone,
    )


def monthly_projection(
    conn: sqlite3.Connection,
    user_id: int,
    settings: SettingsSlice,
    today: dt.date,
    horizon: int = 12,
) -> tuple[MonthlyProjectionPoint, ...]:
    """Return the per-month end-of-month projection series for the Plan tab.

    Thin composer over :func:`monthly_for_settings`; reshapes the result into
    points the chart templates can consume directly (no further template-side math).
    """
    series = monthly_for_settings(conn, user_id, settings, today, horizon)
    return tuple(
        MonthlyProjectionPoint(
            month=point.month,
            label=point.month.strftime("%b %Y"),
            income_minor=point.income_base_minor,
            expense_minor=point.expense_base_minor,
            planned_budget_minor=point.planned_budget_base_minor,
            net_minor=point.net_base_minor,
            end_balance_minor=point.end_balance_base_minor,
        )
        for point in series.months
    )


__all__ = [
    "AccountBalancePoint",
    "DayPoint",
    "ForecastSeries",
    "MonthlyPoint",
    "MonthlyProjectionPoint",
    "MonthlySeries",
    "ProjectionSummary",
    "TrendDirection",
    "forecast",
    "forecast_monthly",
    "horizon_days_for_months",
    "monthly_for_settings",
    "monthly_projection",
    "normalize_horizon",
    "projection_summary",
]


class TrendDirection(StrEnum):
    """Direction of the projected change over the horizon (ADR-0147 §3, G9)."""

    UP = "up"
    DOWN = "down"
    FLAT = "flat"


@dataclass(frozen=True, slots=True)
class ProjectionSummary:
    """NOW / END / PEAK strip of the forecast tab.

    ``delta_minor`` is the non-negative magnitude of ``end - now`` in base
    currency minor units and ``delta_direction`` carries the sign (ADR-0147
    §3, ADR-0148); ``months`` is the horizon length shown as "over N months".
    The balances themselves stay signed, as in the rest of this module.
    """

    now_value: int
    end_point: MonthlyProjectionPoint
    peak_point: MonthlyProjectionPoint
    delta_minor: int
    delta_direction: TrendDirection
    months: int


def _trend_direction(change: int) -> TrendDirection:
    if change > 0:
        return TrendDirection.UP
    if change < 0:
        return TrendDirection.DOWN
    return TrendDirection.FLAT


def projection_summary(projection: tuple[MonthlyProjectionPoint, ...]) -> ProjectionSummary | None:
    """Return the summary strip for a projection, or ``None`` when it is empty."""
    if not projection:
        return None
    now_value = projection[0].end_balance_minor
    change = projection[-1].end_balance_minor - now_value
    return ProjectionSummary(
        now_value=now_value,
        end_point=projection[-1],
        peak_point=max(projection, key=lambda p: p.end_balance_minor),
        delta_minor=abs(change),
        delta_direction=_trend_direction(change),
        months=len(projection),
    )


_DEFAULT_HORIZON_MONTHS = 12


def normalize_horizon(raw: str | None, choices: tuple[int, ...]) -> int:
    """Return the requested forecast horizon when it is one of ``choices``, else 12 months."""
    if raw is None or not raw.isdigit() or int(raw) not in choices:
        return _DEFAULT_HORIZON_MONTHS
    return int(raw)
