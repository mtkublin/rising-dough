"""Accounts page data assembly (T-Q266): card contexts, list hydration, reconcile modal values.

Moved out of the accounts router. No business logic of its own: services supply the numbers and
``web.accounts_view`` the presentation values.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.domain.accounts import Account, AccountStats
from budget_planner.domain.money import format_major, parse_amount_minor
from budget_planner.domain.snapshots import AccountSnapshot
from budget_planner.services import (
    account_planned as planned_service,
    account_reconcile as reconcile_service,
    accounts as accounts_service,
    balance as balance_service,
    fortune as fortune_service,
    fx as fx_service,
    reconciliation as reconciliation_service,
)
from budget_planner.web.accounts_view import (
    account_row,
    accounts_hero,
    credit_utilisation,
    reconcile_dialog,
    sparkline_fields,
)

_RECENT_SNAPSHOTS = 5


def last_checked_by_account(conn: sqlite3.Connection, user_id: int) -> dict[int, datetime | None]:
    """Newest snapshot or reconciliation per account (``accounts.last_checked``)."""
    return {r.account_id: r.last_checked_at for r in accounts_service.last_checked(conn, user_id)}


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
    checked: dict[int, datetime | None] | None = None,
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
    if checked is None:
        checked = last_checked_by_account(conn, user_id)
    return {
        "account": acc,
        "balance": bal,
        "checked_at": checked.get(account_id),
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
    checked = last_checked_by_account(conn, user_id)
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
            checked=checked,
        )
        for a in ordered
    ]
    fortune = fortune_service.compute_fortune(
        conn,
        user_id,
        fx_service.converter_for(conn, settings, today),
        skip_unconvertible=True,
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
        "unconverted_note": _unconverted_note(fortune.unconverted_ccys),
    }


def _unconverted_note(ccys: tuple[str, ...]) -> str | None:
    """Hero note naming the currencies left out of the base totals (T-UR69)."""
    if not ccys:
        return None
    return "rate unavailable for " + ", ".join(ccys) + ": left out of totals"


def recent_snapshots(
    conn: sqlite3.Connection, user_id: int, account_id: int
) -> list[AccountSnapshot]:
    """The newest few snapshots for the reconcile modal."""
    stored = accounts_service.list_snapshots_for_account(conn, user_id, account_id)
    return stored[::-1][:_RECENT_SNAPSHOTS]


def row_context(
    conn: sqlite3.Connection, user_id: int, account_id: int, settings: Settings
) -> dict[str, object]:
    """Context of one ``rows/account-row`` after a save (T-UR08b)."""
    return {"row": account_row(single_card(conn, user_id, account_id, settings))}


def _typed_difference(acc: Account, text: str, derived: int) -> tuple[int, dict[str, str]]:
    """Signed difference of the typed amount (service preview) and the field error, if any."""
    if not text:
        return 0, {}
    entered = parse_amount_minor(text, acc.currency)
    if entered is None:
        return 0, {"actual_balance": "invalid number"}
    try:
        return reconcile_service.preview_difference(acc, entered, derived).difference_minor, {}
    except reconciliation_service.InvalidAvailableError as exc:
        return 0, {"actual_balance": str(exc)}


def reconcile_dialog_context(
    conn: sqlite3.Connection,
    user_id: int,
    acc: Account,
    *,
    actual_text: str = "",
    message: str | None = None,
) -> tuple[dict[str, object], dict[str, str]]:
    """Reconcile dialog view-model plus the field errors of the typed amount (T-UR08b).

    The difference in the hero is the service preview (``preview_difference``); a liability
    with a limit is prefilled with its available credit and so starts at zero.
    """
    derived = balance_service.derive_balance(conn, user_id, acc.id)
    util = credit_utilisation(acc, derived)
    text = actual_text.strip()
    difference, errors = _typed_difference(acc, text, derived)
    if message is not None:
        errors = {"actual_balance": message}
    prefill = format_major(util.available_minor, acc.currency) if util is not None else ""
    dlg = reconcile_dialog(
        acc,
        current_minor=util.available_minor if util is not None else derived,
        difference_minor=difference,
        value=text or prefill,
        credit=util,
        snapshots=recent_snapshots(conn, user_id, acc.id),
    )
    return {"dlg": dlg}, errors


def book_reconcile(
    conn: sqlite3.Connection,
    user_id: int,
    acc: Account,
    settings: Settings,
    *,
    actual_text: str,
) -> tuple[str | None, bool]:
    """Book the reconcile adjustment: (field error when refused, True when already in sync)."""
    entered = parse_amount_minor(actual_text, acc.currency)
    if entered is None:
        return "invalid number", False
    try:
        in_sync = reconcile_service.reconcile_account(
            conn,
            user_id,
            account_id=acc.id,
            actual_balance_minor=reconcile_service.target_balance_minor(acc, entered),
            today=clock.today_local(settings),
        )
    except (
        reconciliation_service.InvalidAvailableError,
        reconciliation_service.ValidationError,
    ) as exc:
        return str(exc), False
    return None, in_sync
