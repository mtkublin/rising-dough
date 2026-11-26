"""Reconcile an account and snapshot it in one transaction (T-Q266).

The reconcile POST used to orchestrate ``reconcile`` and ``create_snapshot`` from the router in two
separate transactions. This service owns both writes under one ``db_transaction`` (G8): a failed
reconcile leaves no snapshot, and the snapshot records the balance after the adjustment.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import sqlite3
from dataclasses import dataclass
from typing import Literal

from budget_planner.domain.accounts import Account
from budget_planner.domain.snapshots import NewAccountSnapshot
from budget_planner.repositories._shared import transaction as db_transaction
from budget_planner.services import (
    accounts as accounts_service,
    balance as balance_service,
    reconciliation as reconciliation_service,
)

RECONCILE_SNAPSHOT_NOTE = "reconcile snapshot"

Adjustment = Literal["increase", "decrease", "none"]


@dataclass(frozen=True)
class ReconcilePreview:
    """What a reconcile would do for a typed amount (T-UR34f, ADR-0147 §3, ADR-0148).

    ``difference_minor`` is signed (typed - current), reconciliation being the one signed money
    exception. ``current_minor`` is the figure the typed amount is compared with: the available
    credit for a limited liability, else the derived balance. ``target_balance_minor`` is the
    derived balance after the adjustment; ``adjustment`` names the direction of the booked row.
    """

    entered_minor: int
    current_minor: int
    difference_minor: int
    target_balance_minor: int
    adjustment: Adjustment


def preview_difference(
    account: Account, entered_minor: int, derived_minor: int
) -> ReconcilePreview:
    """Signed difference between the typed amount and the app's figure, no writes.

    Raises ``InvalidAvailableError`` for an impossible available-credit amount (same rule as the
    submit), so the preview and the booking agree.
    """
    target = target_balance_minor(account, entered_minor)
    limit = account.credit_limit_minor or 0
    by_available = account.is_liability and limit > 0
    current = limit + derived_minor if by_available else derived_minor
    difference = entered_minor - current
    adjustment: Adjustment = (
        "increase" if difference > 0 else "decrease" if difference < 0 else "none"
    )
    return ReconcilePreview(
        entered_minor=entered_minor,
        current_minor=current,
        difference_minor=difference,
        target_balance_minor=target,
        adjustment=adjustment,
    )


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
) -> None:
    """Book the adjustment to the Reconciliation category and snapshot the new balance.

    A zero delta books nothing but still snapshots (ADR-0011 amendment 2026-11-26).
    """
    with db_transaction(conn):
        with contextlib.suppress(reconciliation_service.NoAdjustmentNeededError):
            reconciliation_service.reconcile(
                conn,
                user_id,
                account_id=account_id,
                actual_balance_minor=actual_balance_minor,
                today=today,
            )
        balance = balance_service.derive_balance(conn, user_id, account_id)
        accounts_service.create_snapshot(
            conn,
            user_id,
            NewAccountSnapshot(
                account_id=account_id, balance=balance, note=RECONCILE_SNAPSHOT_NOTE
            ),
        )
