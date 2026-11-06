"""Accounts tab: planned net per account + projected end-of-period balance.

ADR-0089. For each account, the signed net (account currency) of planned,
not-yet-paid payments in the current fiscal period ``[period_start,
period_end)``, and ``balance + net`` as the projected end-of-period balance.
Functional: pure w.r.t. the DB snapshot + injected ``today``.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from calendar import monthrange
from dataclasses import dataclass

from budget_planner.config import Settings
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import PlannedFilter
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
)
from budget_planner.services import (
    balance as balance_service,
    budget as budget_svc,
    income as income_svc,
    preferences as preferences_svc,
    recurring as recurring_svc,
)

_ONE_DAY = dt.timedelta(days=1)


@dataclass(frozen=True, slots=True)
class PlannedWindow:
    """Half-open fiscal window ``[start, end)``."""

    start: dt.date
    end: dt.date


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
    """Return the fiscal window; end falls back to end-of-month only without a next income."""
    start = budget_svc.resolve_period_start(conn, user_id, today)
    end_of_month = today.replace(day=monthrange(today.year, today.month)[1]) + _ONE_DAY
    anchor = preferences_svc.resolve_income_anchor_category(conn, user_id)
    if anchor is None:
        return PlannedWindow(start=start, end=end_of_month)
    hit = income_svc.next_anchor_date(conn, user_id, anchor.id, after=today)
    return PlannedWindow(start=start, end=hit if hit is not None else end_of_month)


def _legs(
    direction: Direction, account_id: int, dest_account_id: int | None, amount: int
) -> tuple[tuple[int, int], ...]:
    """Return ``(account_id, signed_minor)`` legs; adjustments contribute nothing."""
    if direction is Direction.INCOME:
        return ((account_id, amount),)
    if direction is Direction.EXPENSE:
        return ((account_id, -amount),)
    if direction is Direction.TRANSIT and dest_account_id is not None:
        return ((account_id, -amount), (dest_account_id, amount))
    return ()


def _collect_legs(
    conn: sqlite3.Connection, user_id: int, window: PlannedWindow
) -> list[tuple[int, int]]:
    last_day = window.end - _ONE_DAY
    # Archived categories keep their unpromoted items; count them by direction (ADR-0089).
    directions = {
        c.id: c.direction for c in categories_repo.list_all(conn, user_id, include_deleted=True)
    }
    persisted = planned_repo.list_filtered(
        conn,
        user_id,
        PlannedFilter(date_from=window.start, date_to=last_day, promoted=False),
    )
    legs: list[tuple[int, int]] = []
    dedup = recurring_svc.linked_occurrence_keys(conn, user_id)
    for row in persisted:
        legs.extend(
            _legs(directions[row.category_id], row.account_id, row.dest_account_id, row.amount)
        )
    for rule in recurring_repo.list_rules(conn, user_id, active_only=True):
        overrides = recurring_repo.list_overrides(conn, user_id, rule.id)
        occs = recurring_svc.expand_unpromoted(
            conn, user_id, rule, overrides, window.start, last_day
        )
        for occ in occs:
            if occ.is_skipped or (rule.id, occ.occurrence_date) in dedup:
                continue
            legs.extend(
                _legs(directions[rule.category_id], occ.account_id, occ.dest_account_id, occ.amount)
            )
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
    for acc in accounts_repo.list_all(conn, user_id):
        net = nets.get(acc.id, 0)
        balance = balance_service.derive_balance(conn, user_id, acc.id)
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
