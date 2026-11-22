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
import logging
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from budget_planner.domain.accounts import Account
from budget_planner.domain.enums import Direction
from budget_planner.domain.money import HALF_EVEN, major_float, round_div
from budget_planner.domain.periods import month_bounds, shift_month
from budget_planner.domain.transactions import Transaction, TransactionFilter, signed_legs
from budget_planner.repositories import (
    accounts as accounts_repo,
    transactions as transactions_repo,
)
from budget_planner.services import (
    balance as balance_svc,
    budget as budget_svc,
    budget_batch,
    categories as categories_svc,
    fx as fx_svc,
    recurring as recurring_svc,
)

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True, slots=True, kw_only=True)
class _CashEvent:
    """Signed per-account cash movement scheduled on a particular date."""

    on_date: dt.date
    account_id: int
    amount_minor: int


# ---------------------------------------------------------------------------
# event emission
# ---------------------------------------------------------------------------
def _signed_events_for_direction(
    direction: Direction,
    operation_date: dt.date,
    account_id: int,
    dest_account_id: int | None,
    amount_minor: int,
) -> tuple[_CashEvent, ...]:
    """Return the per-account cash events for one planned/virtual leg.

    Adapter over ``domain.transactions.signed_legs`` but for forward-looking events
    (operates on dates + raw ints rather than ``Transaction`` rows). Returns
    ``()`` for adjustments — planned adjustments are unsupported (ADR-0011
    + T-023 guard); surviving rows are skipped defensively with a DEBUG log.
    """
    if direction is Direction.ADJUSTMENT:
        logger.debug(
            "forecast skipping adjustment-direction planned leg on %s acct=%s",
            operation_date,
            account_id,
        )
        return ()
    if direction is Direction.TRANSIT:
        if dest_account_id is None:
            raise ValueError("transit event missing dest_account_id")
        if dest_account_id == account_id:
            raise ValueError("transit source and dest must differ")
    return tuple(
        _CashEvent(on_date=operation_date, account_id=leg.account_id, amount_minor=leg.amount_minor)
        for leg in signed_legs(direction, amount_minor, account_id, dest_account_id)
    )


def _events_for_item(item: recurring_svc.PendingItem) -> tuple[_CashEvent, ...]:
    return _signed_events_for_direction(
        direction=item.direction,
        operation_date=item.on_date,
        account_id=item.account_id,
        dest_account_id=item.dest_account_id,
        amount_minor=item.amount,
    )


# ---------------------------------------------------------------------------
# event collection
# ---------------------------------------------------------------------------
def _collect_events(
    conn: sqlite3.Connection,
    user_id: int,
    today: dt.date,
    end_date: dt.date,
) -> dict[dt.date, list[_CashEvent]]:
    """Return per-date cash events sourced from planned rows + virtual occurrences.

    Overdue unpromoted items are counted and placed on ``today + 1`` (ADR-0105
    amendment 2026-11-21, OQ-6 default).
    """
    event_start = today + dt.timedelta(days=1)
    if event_start > end_date:
        return {}

    events: dict[dt.date, list[_CashEvent]] = {}
    for item in recurring_svc.pending_occurrences(
        conn,
        user_id,
        start=event_start,
        end=end_date + dt.timedelta(days=1),
        today=today,
        include_overdue=True,
        overdue_on=event_start,
    ):
        for ev in _events_for_item(item):
            events.setdefault(ev.on_date, []).append(ev)
    return events


# ---------------------------------------------------------------------------
# budget overlay (ADR-0042)
# ---------------------------------------------------------------------------
_MONTHS_IN_YEAR = 12


def _iter_months(start: dt.date, end: dt.date) -> list[tuple[int, int]]:
    """Return ``(year, month)`` tuples whose month overlaps ``[start, end]``."""
    out: list[tuple[int, int]] = []
    year, month = start.year, start.month
    end_year, end_month = end.year, end.month
    while (year, month) <= (end_year, end_month):
        out.append((year, month))
        month += 1
        if month > _MONTHS_IN_YEAR:
            month = 1
            year += 1
    return out


@dataclass(frozen=True, slots=True)
class _MonthSpan:
    """One budget month: spend window ``[month_start, min(today, month_end)]``, commit window."""

    month_start: dt.date
    window_start: dt.date
    month_end: dt.date
    include_overdue: bool


def _base_of_txn(
    conn: sqlite3.Connection, user_id: int, fx: fx_svc.FxConverter
) -> Callable[[Transaction], int]:
    return fx_svc.txn_base_of(fx, fx_svc.currency_by_account(conn, user_id))


def _spent_per_span(
    conn: sqlite3.Connection,
    user_id: int,
    spans: Sequence[_MonthSpan],
    *,
    today: dt.date,
    base_of: Callable[[Transaction], int],
) -> list[dict[int, int]]:
    """Base-currency expense per category in each span's ``[month_start, min(today, month_end)]``.

    Each transaction converts at its own date's cached rate, like the budget (ADR-0006, Q-008).
    """
    cutoffs = [min(today, sp.month_end) for sp in spans]
    spent: list[dict[int, int]] = [{} for _ in spans]
    live = [(sp, c) for sp, c in zip(spans, cutoffs, strict=True) if c >= sp.month_start]
    if not live:
        return spent
    rows = transactions_repo.list_filtered(
        conn,
        user_id,
        TransactionFilter(
            live_accounts_only=True,
            date_from=min(sp.month_start for sp, _ in live),
            date_to=max(c for _, c in live),
            directions=(Direction.EXPENSE,),
        ),
    )
    for row in rows:
        for bucket, sp, cutoff in zip(spent, spans, cutoffs, strict=True):
            if sp.month_start <= row.operation_date <= cutoff:
                bucket[row.category_id] = bucket.get(row.category_id, 0) + base_of(row)
    return spent


def _month_inputs(
    conn: sqlite3.Connection,
    user_id: int,
    spans: Sequence[_MonthSpan],
    *,
    today: dt.date,
    fx: fx_svc.FxConverter,
) -> list[tuple[dict[int, int], dict[int, int]]]:
    """Per span ``(spent_by_category, committed_by_category)`` with O(1) queries (T-Q234).

    Spent is actual expense in ``[month_start, min(today, month_end)]`` (one transaction
    query bucketed per span); committed is unpromoted planned + active recurring expense
    in ``[window_start, month_end]`` (one expansion, ADR-0087 dedup via the budget owner).
    """
    if not spans:
        return []
    spent = _spent_per_span(
        conn, user_id, spans, today=today, base_of=_base_of_txn(conn, user_id, fx)
    )
    committed = budget_batch.committed_by_category_windows(
        conn,
        user_id,
        windows=[
            budget_batch.CommitWindow(
                start=sp.window_start,
                end=sp.month_end + dt.timedelta(days=1),
                include_overdue=sp.include_overdue,
            )
            for sp in spans
        ],
        today=today,
        base_currency=fx.base_currency,
    )
    return list(zip(spent, committed, strict=True))


def _distribute_overlay(
    *,
    unaccounted_minor: int,
    window_start: dt.date,
    window_end_inclusive: dt.date,
    account_id: int,
) -> list[_CashEvent]:
    """Spread ``unaccounted_minor`` evenly as expense events, residual on last day.

    Per-day amount via ``HALF_EVEN`` (``round_div``); the final day absorbs any
    rounding delta so the window sum equals ``unaccounted_minor`` exactly.
    Zero-amount days are omitted. Caller guarantees ``unaccounted_minor > 0``
    and ``window_end_inclusive >= window_start``.
    """
    day_count = (window_end_inclusive - window_start).days + 1
    per_day_minor = round_div(unaccounted_minor, day_count, mode=HALF_EVEN)
    distributed_before_last = per_day_minor * (day_count - 1)
    last_day_minor = unaccounted_minor - distributed_before_last

    events: list[_CashEvent] = []
    for i in range(day_count):
        amt = last_day_minor if i == day_count - 1 else per_day_minor
        if amt == 0:
            continue
        events.append(
            _CashEvent(
                on_date=window_start + dt.timedelta(days=i),
                account_id=account_id,
                amount_minor=-amt,
            )
        )
    return events


@dataclass(frozen=True, slots=True)
class _OverlayMonth:
    """One calendar month the budget overlay touches, with its commit/spend span."""

    year: int
    month: int
    span: _MonthSpan
    window_end: dt.date


def _overlay_months(event_start: dt.date, end_date: dt.date) -> list[_OverlayMonth]:
    out: list[_OverlayMonth] = []
    for year, month in _iter_months(event_start, end_date):
        month_start, month_end = month_bounds(year, month)
        window_start = max(event_start, month_start)
        window_end = min(end_date, month_end)
        if window_start <= window_end:
            span = _MonthSpan(month_start, window_start, month_end, window_start == event_start)
            out.append(_OverlayMonth(year, month, span, window_end))
    return out


def _collect_budget_overlay(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    today: dt.date,
    end_date: dt.date,
    primary_account_id: int,
    fx: fx_svc.FxConverter,
) -> list[_CashEvent]:
    """Return synthetic expense events for per-category per-month unaccounted budget."""
    event_start = today + dt.timedelta(days=1)
    if event_start > end_date:
        return []

    expense_cat_ids = categories_svc.expense_category_ids(conn, user_id)
    if not expense_cat_ids:
        return []

    resolve = budget_batch.budget_resolver(conn, user_id)
    months = _overlay_months(event_start, end_date)
    inputs = _month_inputs(conn, user_id, [m.span for m in months], today=today, fx=fx)

    events: list[_CashEvent] = []
    for month, (spent_by_cat, committed_by_cat) in zip(months, inputs, strict=True):
        for cat_id in expense_cat_ids:
            budget = resolve(cat_id, month.year, month.month)
            if budget is None:
                continue
            unaccounted = budget - spent_by_cat.get(cat_id, 0) - committed_by_cat.get(cat_id, 0)
            if unaccounted > 0:
                events.extend(
                    _distribute_overlay(
                        unaccounted_minor=unaccounted,
                        window_start=month.span.window_start,
                        window_end_inclusive=month.window_end,
                        account_id=primary_account_id,
                    )
                )

    return events


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
) -> ForecastSeries:
    """Project per-account balances forward ``horizon_days`` days.

    Args:
        conn: Open SQLite connection (read-only usage).
        fx: Cache-only converter (ADR-0139); a missing rate raises ``FxUnavailableError``.
        today: Day 0 of the series. Routers inject the date in the display
            timezone so the forecast is tz-independent and deterministic.
        horizon_days: Non-negative count of additional days to project.
        include_budget_overlay: When ``True`` (default), inject synthetic
            expense events for the per-category per-month residual budget
            (ADR-0042). Pass ``False`` for the pre-overlay projection used
            by targeted regression tests.

    Returns:
        ``ForecastSeries`` with ``len(days) == horizon_days + 1``.

    Invariants:
        * ``days[0].by_account[i].native_minor ==
          services.balance.derive_balance(conn, account_id, as_of_date=today)``.
        * Removing (soft-delete) a planned row before the call drops the
          projected balance after its ``operation_date`` by exactly the
          signed-leg magnitude.
        * Same inputs + same DB snapshot + same FX cache state → identical output.
    """
    if horizon_days < 0:
        raise ValueError(f"horizon_days must be >= 0, got {horizon_days}")
    base_currency = fx.base_currency

    end_date = today + dt.timedelta(days=horizon_days)
    active_accounts = tuple(accounts_repo.list_all(conn, user_id))
    if not active_accounts:
        return ForecastSeries(
            base_currency=base_currency,
            start_date=today,
            end_date=end_date,
            days=tuple(
                DayPoint(on_date=today + dt.timedelta(days=i), totals_base_minor=0, by_account=())
                for i in range(horizon_days + 1)
            ),
        )

    events = _collect_events(conn, user_id, today, end_date)

    if include_budget_overlay:
        primary_account_id = min(a.id for a in active_accounts)
        overlay_events = _collect_budget_overlay(
            conn,
            user_id,
            today=today,
            end_date=end_date,
            primary_account_id=primary_account_id,
            fx=fx,
        )
        for ev in overlay_events:
            events.setdefault(ev.on_date, []).append(ev)

    running_native = dict(_anchor_balances(conn, user_id, today, active_accounts))
    days: list[DayPoint] = [_build_day(today, active_accounts, running_native, fx)]

    for offset in range(1, horizon_days + 1):
        on_date = today + dt.timedelta(days=offset)
        for ev in events.get(on_date, ()):
            running_native[ev.account_id] = running_native.get(ev.account_id, 0) + ev.amount_minor
        days.append(_build_day(on_date, active_accounts, running_native, fx))

    return ForecastSeries(
        base_currency=base_currency,
        start_date=today,
        end_date=end_date,
        days=tuple(days),
    )


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
) -> budget_svc.MonthTotals | None:
    """Return ``month_summary(fiscal).totals`` or ``None`` if no live categories."""
    y = fiscal_year if fiscal_year is not None else today.year
    m = fiscal_month if fiscal_month is not None else today.month
    summary = budget_svc.month_summary(
        conn, user_id, y, m, today=today, base_currency=base_currency
    )
    return summary.totals


def _planned_budget_per_month(
    conn: sqlite3.Connection,
    user_id: int,
    today: dt.date,
    horizon_months: int,
    *,
    fx: fx_svc.FxConverter,
    start_month: dt.date | None = None,
) -> dict[dt.date, int]:
    """Return per-month **remaining** budget, clamped at zero.

    For each month ``m`` in the horizon:

    ``remaining(m) = Σ max(resolve_budget(cat, m) - spent_so_far(cat, m) -
                            committed_future(cat, m), 0)``

    across every live expense category.

    * ``spent_so_far`` counts actual expense transactions in
      ``[month_start, min(today, month_end)]`` — zero for future months.
    * ``committed_future`` counts unpromoted planned + active recurring
      expense amounts in ``(max(today, month_start - 1 day), month_end]``.
    * The clamp drops categories whose planned/recurring already covers
      (or exceeds) their budget, matching the ADR-0042 overlay semantics
      and the user's "only if remaining is positive" rule.

    Budgets are stored in base currency; ``spent_so_far`` is converted to base (Q-008).
    Budget-period consumption boundaries (ADR-0041) are approximated with
    calendar months here, matching ``_collect_budget_overlay``.
    """
    expense_cat_ids = categories_svc.expense_category_ids(conn, user_id)
    anchor_month = start_month if start_month is not None else today.replace(day=1)
    resolve = budget_batch.budget_resolver(conn, user_id)
    months = [_month_offset(anchor_month, offset) for offset in range(horizon_months)]
    tomorrow = today + dt.timedelta(days=1)
    spans = [
        _MonthSpan(
            month_start=m,
            window_start=max(tomorrow, m),
            month_end=_last_day_of_month(m),
            include_overdue=max(tomorrow, m) == tomorrow,
        )
        for m in months
    ]
    inputs = _month_inputs(conn, user_id, spans, today=today, fx=fx)
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


def forecast_monthly(
    conn: sqlite3.Connection,
    user_id: int,
    fx: fx_svc.FxConverter,
    today: dt.date,
    horizon_months: int,
) -> MonthlySeries:
    """Monthly aggregate projection over ``horizon_months`` months (ADR-0043).

    One row per calendar month in ``[today.month, today.month + horizon_months - 1]``:
    ``income_base_minor``, ``expense_base_minor``, ``net`` = income - expense,
    and ``end_balance_base_minor`` = projected total fortune at month-end.

    The daily projection is reused for end-of-month balances with the
    ADR-0042 budget overlay enabled, so each row's ``end_balance_base_minor``
    absorbs the remaining-budget synthetic spend across the horizon.
    Monthly flow sums (``income`` / ``expense``) are re-derived from the
    explicit event stream only (no overlay) so those columns stay
    traceable to real planned + recurring + anchor state.
    ``planned_budget_base_minor`` is the per-month residual budget
    (``max(resolved - spent_so_far - committed_future, 0)``) summed across
    live expense categories.
    """
    if horizon_months < 1:
        raise ValueError(f"horizon_months must be >= 1, got {horizon_months}")
    base_currency = fx.base_currency

    # Start the series at the fiscal cycle, not the calendar month, so the
    # "current" row of the Forecast table lines up with the Plan hub's
    # landing month (ADR-0064). Falls back to the calendar month when no
    # anchor is configured.
    fiscal_year, fiscal_month = budget_svc.fiscal_month_for(conn, user_id, today)
    start_month = dt.date(fiscal_year, fiscal_month, 1)
    last_month = _month_offset(start_month, horizon_months - 1)
    end_date = _last_day_of_month(last_month)
    horizon_days = max((end_date - today).days, 0)
    series = forecast(conn, user_id, fx, today, horizon_days)

    planned_budget_by_month = _planned_budget_per_month(
        conn, user_id, today, horizon_months, fx=fx, start_month=start_month
    )

    active_accounts = tuple(accounts_repo.list_all(conn, user_id))
    if not active_accounts:
        months_empty = tuple(
            MonthlyPoint(
                month=_month_offset(start_month, offset),
                income_base_minor=0,
                expense_base_minor=0,
                planned_budget_base_minor=planned_budget_by_month[
                    _month_offset(start_month, offset)
                ],
                net_base_minor=-planned_budget_by_month[_month_offset(start_month, offset)],
                end_balance_base_minor=0,
            )
            for offset in range(horizon_months)
        )
        return MonthlySeries(
            base_currency=base_currency,
            start_month=start_month,
            end_month=last_month,
            months=months_empty,
        )

    flows = _month_flow_sums(
        conn,
        user_id,
        today=today,
        end_date=end_date,
        accounts=active_accounts,
        fx=fx,
    )

    fiscal_month_start = start_month
    current_month_totals = _current_month_budget_totals(
        conn,
        user_id,
        today,
        base_currency=base_currency,
        fiscal_year=fiscal_year,
        fiscal_month=fiscal_month,
    )

    # EOM is a running chain anchored at today's net worth, so each row
    # answers "what will my balance be at the end of this row's period
    # given the plan it displays?". The identity previous_EOM + Net = EOM
    # is the user-visible contract — mixing daily-projection EOM for
    # non-fiscal rows with current+Net for the fiscal row broke that
    # contract across the fiscal/calendar seam.
    running_balance = series.days[0].totals_base_minor
    rows: list[MonthlyPoint] = []
    for offset in range(horizon_months):
        month = _month_offset(start_month, offset)
        income, expense = flows.get(month, (0, 0))
        is_fiscal_row = month == fiscal_month_start
        if is_fiscal_row and current_month_totals is not None:
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

    return MonthlySeries(
        base_currency=base_currency,
        start_month=start_month,
        end_month=last_month,
        months=tuple(rows),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class MonthlyProjectionPoint:
    """Template-friendly projection point for the Plan · Forecast chart.

    One entry per calendar month in the horizon. ``value_major`` is the
    projected end-of-month fortune in major units, convenient for SVG
    plotting (``charts.line_area`` normalises on raw floats). ``label``
    is a short month label suitable for the x-axis.

    ADR-0056 Plan · Forecast reskin adds the per-month flow aggregates so
    the inline table beneath the chart does not need a second service call.
    All *_minor fields are in base-currency minor units.
    """

    month: dt.date
    label: str
    value_major: float
    income_minor: int = 0
    expense_minor: int = 0
    planned_budget_minor: int = 0
    net_minor: int = 0
    end_balance_minor: int = 0


def monthly_for_settings(
    conn: sqlite3.Connection,
    user_id: int,
    settings: fx_svc.HasBaseCurrency,
    today: dt.date,
    horizon_months: int,
) -> MonthlySeries:
    """:func:`forecast_monthly` with the request's cache-only converter (ADR-0139)."""
    return forecast_monthly(
        conn, user_id, fx_svc.converter_for(conn, settings, today), today, horizon_months
    )


def monthly_projection(
    conn: sqlite3.Connection,
    user_id: int,
    settings: fx_svc.HasBaseCurrency,
    today: dt.date,
    horizon: int = 12,
) -> tuple[MonthlyProjectionPoint, ...]:
    """Return the per-month end-of-month projection series for the Plan tab.

    Thin composer over :func:`monthly_for_settings`; reshapes the result into
    points the chart templates can consume directly (no further template-side math).
    """
    base_ccy = settings.base_currency
    series = monthly_for_settings(conn, user_id, settings, today, horizon)
    return tuple(
        MonthlyProjectionPoint(
            month=point.month,
            label=point.month.strftime("%b %Y"),
            value_major=major_float(point.end_balance_base_minor, base_ccy),
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
    "forecast",
    "forecast_monthly",
    "horizon_days_for_months",
    "monthly_for_settings",
    "monthly_projection",
    "normalize_horizon",
    "projection_summary",
]


@dataclass(frozen=True, slots=True)
class ProjectionSummary:
    """NOW / END / PEAK strip of the forecast tab."""

    now_value: int
    end_point: MonthlyProjectionPoint
    peak_point: MonthlyProjectionPoint


def projection_summary(projection: tuple[MonthlyProjectionPoint, ...]) -> ProjectionSummary | None:
    """Return the summary strip for a projection, or ``None`` when it is empty."""
    if not projection:
        return None
    return ProjectionSummary(
        now_value=projection[0].end_balance_minor,
        end_point=projection[-1],
        peak_point=max(projection, key=lambda p: p.value_major),
    )


_DEFAULT_HORIZON_MONTHS = 12


def normalize_horizon(raw: str | None, choices: tuple[int, ...]) -> int:
    """Return the requested forecast horizon when it is one of ``choices``, else 12 months."""
    if raw is None or not raw.isdigit() or int(raw) not in choices:
        return _DEFAULT_HORIZON_MONTHS
    return int(raw)
