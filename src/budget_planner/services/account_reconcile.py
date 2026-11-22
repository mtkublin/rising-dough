"""Reconcile an account and optionally snapshot it in one transaction (T-Q266).

The reconcile POST used to orchestrate ``reconcile`` and ``create_snapshot`` from the router in two
separate transactions. This service owns both writes under one ``db_transaction`` (G8): a failed
reconcile leaves no snapshot, and the snapshot records the balance after the adjustment.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import sqlite3

from budget_planner.domain.accounts import Account
from budget_planner.domain.snapshots import NewAccountSnapshot
from budget_planner.repositories._shared import transaction as db_transaction
from budget_planner.services import (
    accounts as accounts_service,
    balance as balance_service,
    reconciliation as reconciliation_service,
)

RECONCILE_SNAPSHOT_NOTE = "reconcile snapshot"


def target_balance_minor(account: Account, entered_minor: int) -> int:
    """Balance the account must reach for the amount the user typed.

    A liability with a positive credit limit reconciles by available credit (T-D52): the typed
    amount is the available credit and converts to a (negative) balance. Any other account takes
    the typed amount as the balance. Raises ``InvalidAvailableError`` for impossible availability.
    """
    limit = account.credit_limit_minor or 0
    if account.is_liability and limit > 0:
        return reconciliation_service.available_to_target_balance(limit, entered_minor)
    return entered_minor


def reconcile_account(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    account_id: int,
    actual_balance_minor: int,
    today: dt.date,
    category_id: int | None,
    save_snapshot: bool,
) -> None:
    """Insert the adjustment (a zero delta is fine) and, when asked, snapshot the new balance."""
    with db_transaction(conn):
        with contextlib.suppress(reconciliation_service.NoAdjustmentNeededError):
            reconciliation_service.reconcile(
                conn,
                user_id,
                account_id=account_id,
                actual_balance_minor=actual_balance_minor,
                today=today,
                category_id=category_id,
            )
        if save_snapshot:
            balance = balance_service.derive_balance(conn, user_id, account_id)
            accounts_service.create_snapshot(
                conn,
                user_id,
                NewAccountSnapshot(
                    account_id=account_id, balance=balance, note=RECONCILE_SNAPSHOT_NOTE
                ),
            )
