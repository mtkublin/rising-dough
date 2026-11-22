"""Accounts tab: planned net per account + projected end-of-period balance.

ADR-0089. For each account, the signed net (account currency) of planned,
not-yet-paid payments in the current fiscal period ``[period_start,
period_end)``, and ``balance + net`` as the projected end-of-period balance.
Functional: pure w.r.t. the DB snapshot + injected ``today``.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass

from budget_planner.config import Settings
from budget_planner.domain.enums import Direction
from budget_planner.domain.periods import PeriodWindow, fiscal_window
from budget_planner.domain.transactions import signed_legs
from budget_planner.repositories import (
    accounts as accounts_repo,
)
from budget_planner.services import (
    balance as balance_service,
    budget as budget_svc,
    income as income_svc,
    preferences as preferences_svc,
    recurring as recurring_svc,
)

PlannedWindow = PeriodWindow  # half-open fiscal window ``[start, end)`` (ADR-0138)


@dataclass(frozen=True, slots=True)
class AccountPlanned:
    """Planned net + projected end-of-period balance for one account."""

    account_id: int
    currency: str
    net_minor: int
    projected_minor: int


@dataclass(frozen=True, slots=True)
class AccountsPlanned:
    """Per-account results plus the base-currency hero total."""

    window: PlannedWindow
    by_account: dict[int, AccountPlanned]
    base_net_minor: int


def resolve_window(conn: sqlite3.Connection, user_id: int, today: dt.date) -> PlannedWindow:
    """Return the half-open fiscal window; end falls back to first-of-next-month (ADR-0138)."""
    start = budget_svc.resolve_period_start(conn, user_id, today)
    anchor = preferences_svc.resolve_income_anchor_category(conn, user_id)
    hit = (
        income_svc.next_anchor_date(conn, user_id, anchor.id, after=today)
        if anchor is not None
        else None
    )
    return fiscal_window(today, period_start=start, next_income=hit)


def _legs(
    direction: Direction, account_id: int, dest_account_id: int | None, amount: int
) -> tuple[tuple[int, int], ...]:
    """Return ``(account_id, signed_minor)`` legs; adjustments contribute nothing."""
    if direction is Direction.ADJUSTMENT or (
        direction is Direction.TRANSIT and dest_account_id is None
    ):
        return ()
    return tuple(
        (leg.account_id, leg.amount_minor)
        for leg in signed_legs(direction, amount, account_id, dest_account_id)
    )


def _collect_legs(
    conn: sqlite3.Connection, user_id: int, window: PlannedWindow
) -> list[tuple[int, int]]:
    # Archived categories keep their unpromoted items; count them by direction (ADR-0089).
    # Overdue stays clamped to the period start (ADR-0089), so ``include_overdue=False``.
    items = recurring_svc.pending_occurrences(
        conn,
        user_id,
        start=window.start,
        end=window.last_day + dt.timedelta(days=1),
        today=None,
        include_overdue=False,
    )
    legs: list[tuple[int, int]] = []
    for item in items:
        legs.extend(_legs(item.direction, item.account_id, item.dest_account_id, item.amount))
    return legs


def planned_net_by_account(
    conn: sqlite3.Connection, user_id: int, window: PlannedWindow
) -> dict[int, int]:
    """Return ``{account_id: signed_net_minor}`` for the window (zero nets omitted)."""
    totals: dict[int, int] = {}
    for account_id, signed in _collect_legs(conn, user_id, window):
        totals[account_id] = totals.get(account_id, 0) + signed
    return {k: v for k, v in totals.items() if v != 0}


def compute_accounts_planned(
    conn: sqlite3.Connection, user_id: int, today: dt.date, settings: Settings
) -> AccountsPlanned:
    """Compose per-account planned net, projected balance and the base-ccy hero total."""
    window = resolve_window(conn, user_id, today)
    nets = planned_net_by_account(conn, user_id, window)
    by_account: dict[int, AccountPlanned] = {}
    base_net = 0
    accounts = accounts_repo.list_all(conn, user_id)
    balances = balance_service.derive_balances(conn, user_id, accounts)
    for acc in accounts:
        net = nets.get(acc.id, 0)
        balance = balances[acc.id]
        by_account[acc.id] = AccountPlanned(
            account_id=acc.id,
            currency=acc.currency,
            net_minor=net,
            projected_minor=balance + net,
        )
        if acc.currency == settings.base_currency:
            base_net += net
    return AccountsPlanned(window=window, by_account=by_account, base_net_minor=base_net)


__all__ = [
    "AccountPlanned",
    "AccountsPlanned",
    "PlannedWindow",
    "compute_accounts_planned",
    "planned_net_by_account",
    "resolve_window",
]
