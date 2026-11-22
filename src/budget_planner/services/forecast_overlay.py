"""Forecast budget overlay (ADR-0042, T-Q242 split from ``forecast.py``): synthetic events."""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from budget_planner.clock import DEFAULT_DISPLAY_TIMEZONE
from budget_planner.domain.enums import Direction
from budget_planner.domain.money import HALF_EVEN, round_div
from budget_planner.domain.periods import month_bounds
from budget_planner.domain.transactions import Transaction, TransactionFilter
from budget_planner.repositories import transactions as transactions_repo
from budget_planner.services import (
    budget_batch,
    categories as categories_svc,
    fx as fx_svc,
)
from budget_planner.services.forecast_events import CashEvent

_MONTHS_IN_YEAR = 12


def iter_months(start: dt.date, end: dt.date) -> list[tuple[int, int]]:
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
class MonthSpan:
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
    spans: Sequence[MonthSpan],
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


def month_inputs(
    conn: sqlite3.Connection,
    user_id: int,
    spans: Sequence[MonthSpan],
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


def distribute_overlay(
    *,
    unaccounted_minor: int,
    window_start: dt.date,
    window_end_inclusive: dt.date,
    account_id: int,
) -> list[CashEvent]:
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

    events: list[CashEvent] = []
    for i in range(day_count):
        amt = last_day_minor if i == day_count - 1 else per_day_minor
        if amt == 0:
            continue
        events.append(
            CashEvent(
                on_date=window_start + dt.timedelta(days=i),
                account_id=account_id,
                amount_minor=-amt,
            )
        )
    return events


@dataclass(frozen=True, slots=True)
class OverlayMonth:
    """One calendar month the budget overlay touches, with its commit/spend span."""

    year: int
    month: int
    span: MonthSpan
    window_end: dt.date


def overlay_months(event_start: dt.date, end_date: dt.date) -> list[OverlayMonth]:
    out: list[OverlayMonth] = []
    for year, month in iter_months(event_start, end_date):
        month_start, month_end = month_bounds(year, month)
        window_start = max(event_start, month_start)
        window_end = min(end_date, month_end)
        if window_start <= window_end:
            span = MonthSpan(month_start, window_start, month_end, window_start == event_start)
            out.append(OverlayMonth(year, month, span, window_end))
    return out


def collect_budget_overlay(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    today: dt.date,
    end_date: dt.date,
    primary_account_id: int,
    fx: fx_svc.FxConverter,
    display_timezone: str = DEFAULT_DISPLAY_TIMEZONE,
) -> list[CashEvent]:
    """Return synthetic expense events for per-category per-month unaccounted budget.

    A category archived in or before a month adds nothing for it (ADR-0136, T-Q279).
    """
    event_start = today + dt.timedelta(days=1)
    if event_start > end_date:
        return []

    expense_cat_ids = categories_svc.expense_category_ids(conn, user_id)
    if not expense_cat_ids:
        return []

    resolve = budget_batch.budget_resolver(conn, user_id, display_timezone=display_timezone)
    months = overlay_months(event_start, end_date)
    inputs = month_inputs(conn, user_id, [m.span for m in months], today=today, fx=fx)

    events: list[CashEvent] = []
    for month, (spent_by_cat, committed_by_cat) in zip(months, inputs, strict=True):
        for cat_id in expense_cat_ids:
            budget = resolve(cat_id, month.year, month.month)
            if budget is None:
                continue
            unaccounted = budget - spent_by_cat.get(cat_id, 0) - committed_by_cat.get(cat_id, 0)
            if unaccounted > 0:
                events.extend(
                    distribute_overlay(
                        unaccounted_minor=unaccounted,
                        window_start=month.span.window_start,
                        window_end_inclusive=month.window_end,
                        account_id=primary_account_id,
                    )
                )

    return events
