"""Accounts page data assembly (T-Q266): card contexts, list hydration, reconcile modal values.

Moved out of the accounts router. No business logic of its own: services supply the numbers and
``web.accounts_view`` the presentation values.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.domain.accounts import Account, AccountStats
from budget_planner.domain.snapshots import AccountSnapshot
from budget_planner.services import (
    account_planned as planned_service,
    account_reconcile as reconcile_service,
    accounts as accounts_service,
    balance as balance_service,
    categories as categories_service,
    fortune as fortune_service,
    fx as fx_service,
)
from budget_planner.web.accounts_view import (
    account_row,
    accounts_hero,
    credit_utilisation,
    sparkline_fields,
)

_RECENT_SNAPSHOTS = 5


def planned_now(
    conn: sqlite3.Connection, user_id: int, settings: Settings
) -> planned_service.AccountsPlanned:
    return planned_service.compute_accounts_planned(
        conn, user_id, clock.today_local(settings), settings
    )


def card_context(
    conn: sqlite3.Connection,
    user_id: int,
    account_id: int,
    planned: planned_service.AccountsPlanned,
    today: date,
    *,
    acc: Account | None = None,
    bal: int | None = None,
    stats: AccountStats | None = None,
    series: list[tuple[date, int]] | None = None,
    snapshots: list[AccountSnapshot] | None = None,
) -> dict[str, object]:
    """Build the full context dict a single `_card.html` / `_row.html` needs.

    A value left as ``None`` is loaded for this one account (HTMX single-card
    responses); the list page passes every value, loaded once for all accounts (T-Q234).
    """
    if acc is None:
        acc = accounts_service.find_by_id(conn, user_id, account_id)
    if acc is None:
        raise LookupError(f"account {account_id} not found")
    if bal is None:
        bal = balance_service.derive_balance(conn, user_id, account_id)
    if stats is None:
        stats = balance_service.account_stats(conn, user_id, account_id)
    if series is None:
        series = balance_service.balance_series(conn, user_id, account_id, today=today)
    if snapshots is None:
        snapshots = accounts_service.list_snapshots_for_account(conn, user_id, account_id)
    return {
        "account": acc,
        "balance": bal,
        "stats": stats,
        "series": series,
        **sparkline_fields(series),
        "snapshots": snapshots,
        "planned": planned.by_account.get(account_id),
        "utilisation": credit_utilisation(acc, bal),
    }


def single_card(
    conn: sqlite3.Connection, user_id: int, account_id: int, settings: Settings
) -> dict[str, object]:
    """Card context for one account, with today's planned effect."""
    return card_context(
        conn,
        user_id,
        account_id,
        planned_now(conn, user_id, settings),
        clock.today_local(settings),
    )


def hydrate(conn: sqlite3.Connection, user_id: int, settings: Settings) -> dict[str, object]:
    """Template context for the accounts list page: row view-models and the hero (T-UR08)."""
    today = clock.today_local(settings)
    accs = accounts_service.list_all(conn, user_id)
    planned = planned_service.compute_accounts_planned(conn, user_id, today, settings)
    # T-Q234: every per-account input is loaded once for all accounts (O(1) queries).
    balances = balance_service.derive_balances(conn, user_id, accs)
    stats = balance_service.account_stats_many(conn, user_id, accs)
    series = balance_service.balance_series_many(conn, user_id, accs, today=today)
    snapshots = accounts_service.list_snapshots_for_user(conn, user_id)
    # ADR-0056 section 7: sort by balance desc; liabilities (negative balance) move to the bottom.
    # Assets land first, biggest first; liabilities land last, smallest-liability-first so the
    # credit card with the largest balance sits closer to the assets block visually.
    ordered = sorted(accs, key=lambda a: (0 if balances[a.id] >= 0 else 1, -abs(balances[a.id])))
    cards: list[dict[str, object]] = [
        card_context(
            conn,
            user_id,
            a.id,
            planned,
            today,
            acc=a,
            bal=balances[a.id],
            stats=stats[a.id],
            series=series[a.id],
            snapshots=snapshots.get(a.id, []),
        )
        for a in ordered
    ]
    fortune = fortune_service.compute_fortune(
        conn, user_id, fx_service.converter_for(conn, settings, today)
    )
    return {
        "rows": [account_row(c) for c in cards],
        "hero": accounts_hero(
            count=len(cards),
            net_minor=fortune.net_base,
            assets_minor=fortune.assets_base,
            liabilities_minor=fortune.liabilities_base,
            planned_minor=planned.base_net_minor,
            currency=settings.base_currency,
        ),
        "base_ccy": settings.base_currency,
    }


def available_mode_context(acc: Account, derived: int) -> dict[str, object]:
    """T-D52: a liability with a credit limit reconciles by available credit."""
    util = credit_utilisation(acc, derived)
    if util is None:
        return {"by_available": False}
    return {
        "by_available": True,
        "credit_limit_minor": util.limit_minor,
        "used_minor": util.used_minor,
        "available_minor": util.available_minor,
    }


def reconcile_modal_context(
    conn: sqlite3.Connection,
    user_id: int,
    acc: Account,
    derived: int,
    entered_minor: int | None = None,
) -> dict[str, object]:
    """Category choices and available-credit values shared by the modal and its rejections.

    ``preview`` carries the signed difference for a typed amount (T-UR34f), else ``None``.
    """
    return {
        "preview": (
            None
            if entered_minor is None
            else reconcile_service.preview_difference(acc, entered_minor, derived)
        ),
        "account": acc,
        "derived": derived,
        "categories": [c for c in categories_service.list_all(conn, user_id) if not c.is_system],
        "reconciliation_cat": categories_service.find_by_name(conn, user_id, "Reconciliation"),
        **available_mode_context(acc, derived),
    }


def recent_snapshots(
    conn: sqlite3.Connection, user_id: int, account_id: int
) -> list[AccountSnapshot]:
    """The newest few snapshots for the reconcile modal."""
    return accounts_service.list_snapshots_for_account(conn, user_id, account_id)[
        :_RECENT_SNAPSHOTS
    ]
