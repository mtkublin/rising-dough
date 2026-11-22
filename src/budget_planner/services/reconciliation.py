"""Reconciliation service (T-026).

Given a user-supplied real-world account balance, compute
``delta = actual - derived`` and insert a signed ``adjustment`` direction
transaction so ``derive_balance`` now equals ``actual`` (ADR-0011). The
adjustment is the only route by which a signed-amount transaction enters
the system (ADR-0008 exception).
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from budget_planner.domain.accounts import Account
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.domain.system_categories import RECONCILIATION_CATEGORY_NAME
from budget_planner.domain.transactions import NewTransaction, Transaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.repositories._shared import transaction as db_transaction
from budget_planner.services import balance as balance_svc
from budget_planner.services.transactions import ValidationError, validate_transit_shape


class AccountNotFoundError(LookupError):
    """Raised when the account id does not exist."""


class CannotReconcileDeletedAccountError(RuntimeError):
    """Raised when the account is soft-deleted."""


class NoAdjustmentNeededError(RuntimeError):
    """Raised when derived == actual (zero-amount txn would violate schema CHECK)."""


class MissingSystemCategoryError(RuntimeError):
    """Raised when the seeded ``Reconciliation`` category cannot be found."""


class CategoryDirectionMismatchError(ValidationError):
    """The chosen reconcile category contradicts the sign of the balance delta."""


class InvalidAvailableError(ValueError):
    """Raised when an available-credit figure is outside ``0..credit_limit``."""


def available_to_target_balance(credit_limit_minor: int, available_minor: int) -> int:
    """Convert bank-reported available credit to the target derived balance.

    ``used = credit_limit - available``; liabilities store owed amounts as
    negative balances, so the target balance is ``-used`` (T-D52, ADR-0011).
    Raises ``InvalidAvailableError`` unless ``0 <= available <= credit_limit``.
    """
    if credit_limit_minor <= 0:
        raise InvalidAvailableError("credit limit must be positive")
    if available_minor < 0:
        raise InvalidAvailableError("available credit cannot be negative")
    if available_minor > credit_limit_minor:
        raise InvalidAvailableError("available credit cannot exceed the credit limit")
    return available_minor - credit_limit_minor


def _require_direction_matches_delta(direction: Direction, delta: int) -> None:
    """Reject a category whose direction contradicts the sign of ``delta`` (ADR-0008)."""
    if (direction is Direction.INCOME and delta < 0) or (
        direction is Direction.EXPENSE and delta > 0
    ):
        raise CategoryDirectionMismatchError(
            f"a {direction.value} category cannot book a "
            f"{'positive' if delta > 0 else 'negative'} difference; "
            "pick a matching category or the default Reconciliation"
        )


def _adjustment_category(
    conn: sqlite3.Connection, user_id: int, category_id: int | None
) -> Category:
    """The caller-chosen category, else the seeded ``Reconciliation`` one."""
    if category_id is not None:
        chosen = categories_repo.find_by_id(conn, user_id, category_id)
        if chosen is None:
            raise MissingSystemCategoryError(f"id={category_id}")
        return chosen
    default = categories_repo.find_by_name(conn, user_id, RECONCILIATION_CATEGORY_NAME)
    if default is None:
        raise MissingSystemCategoryError(RECONCILIATION_CATEGORY_NAME)
    assert default.direction is Direction.ADJUSTMENT  # schema invariant
    return default


def _reconciliation_description(today: dt.date, note: str | None) -> str:
    """Audit-friendly description of an auto-reconciliation row."""
    description = f"auto-reconciliation {today.isoformat()}"
    if note:
        description += f" — {note}"
    return description


def _reconcilable_account(conn: sqlite3.Connection, user_id: int, account_id: int) -> Account:
    """The account, or raise when it is missing or soft-deleted."""
    account = accounts_repo.find_by_id(conn, user_id, account_id, include_deleted=True)
    if account is None:
        raise AccountNotFoundError(account_id)
    if account.deleted_at is not None:
        raise CannotReconcileDeletedAccountError(account_id)
    return account


def reconcile(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    account_id: int,
    actual_balance_minor: int,
    today: dt.date,
    note: str | None = None,
    category_id: int | None = None,
) -> Transaction:
    """Insert a signed adjustment so ``derive_balance == actual_balance_minor``.

    The account must be live and ``delta != 0`` (else ``NoAdjustmentNeededError``).
    Post-condition: ``derive_balance(conn, account_id) == actual_balance_minor``.

    ``category_id`` lets F-03 pin the adjustment to a chosen category. The
    category must be ``ADJUSTMENT``, ``INCOME`` with ``delta > 0`` or
    ``EXPENSE`` with ``delta < 0`` (ADR-0008 amendment 2026-11-21); any other
    combination raises ``CategoryDirectionMismatchError`` and writes nothing.
    ADR-0137: the balance read and the insert share one locked transaction.
    """
    with db_transaction(conn):
        account = _reconcilable_account(conn, user_id, account_id)
        derived = balance_svc.derive_balance(conn, user_id, account_id)
        delta = actual_balance_minor - derived
        if delta == 0:
            raise NoAdjustmentNeededError(account_id)

        category = _adjustment_category(conn, user_id, category_id)

        # A reconciliation row has no destination: reject a transit category (ADR-0008).
        validate_transit_shape(category.direction, account, None)

        _require_direction_matches_delta(category.direction, delta)
        # Preserve direction semantics (ADR-0008).
        stored_amount = delta if category.direction is Direction.ADJUSTMENT else abs(delta)
        description = _reconciliation_description(today, note)
        return transactions_repo.create(
            conn,
            user_id,
            NewTransaction(
                operation_date=today,
                category_id=category.id,
                account_id=account_id,
                dest_account_id=None,
                amount=stored_amount,
                description=description,
                promoted_from_planned_id=None,
            ),
        )


__all__ = [
    "AccountNotFoundError",
    "CannotReconcileDeletedAccountError",
    "InvalidAvailableError",
    "MissingSystemCategoryError",
    "NoAdjustmentNeededError",
    "ValidationError",
    "available_to_target_balance",
    "reconcile",
]
