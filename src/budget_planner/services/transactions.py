"""Transaction write-path rules shared by every writer (T-Q210, ADR-0008).

``validate_transit_shape`` is the single transit rule applied by transaction
create/update, planned create/update, promotion and reconcile. A transit row
without a valid destination makes ``derive_balance`` raise, which turns
/accounts, /today and /forecast into 500s (Q-004).

The error classes live here so ``_promotion`` and ``planned`` re-export the
same objects without an import cycle.
"""

from __future__ import annotations

import sqlite3

from budget_planner.domain.accounts import Account
from budget_planner.domain.enums import Direction
from budget_planner.domain.limits import DESCRIPTION_MAX_LENGTH, length_error
from budget_planner.domain.planned import PatchPlannedTransaction, PlannedTransaction
from budget_planner.domain.transactions import (
    NewTransaction,
    PatchTransaction,
    Transaction,
    TransactionFilter,
)
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.services.account_pair import validate_distinct_accounts


class UnsupportedDirectionError(RuntimeError):
    """Raised for direction=adjustment; use reconciliation service instead."""


class ValidationError(ValueError):
    """Raised for invalid write payloads (zero amount, bad transit shape, ...)."""


def validate_transit_shape(direction: Direction, account: Account, dest: Account | None) -> None:
    """Raise ``ValidationError`` unless a transit has a usable destination.

    Other directions are unconstrained. A transit needs a destination that
    differs from the source and shares its currency (ADR-0006).
    """
    if direction is not Direction.TRANSIT:
        return
    if dest is None:
        raise ValidationError("transit requires a destination account")
    same = validate_distinct_accounts(account.id, dest.id)
    if same is not None:
        raise ValidationError(same)
    if account.currency != dest.currency:
        raise ValidationError("cross-currency transit not supported")


def check_transit_shape(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    direction: Direction,
    account_id: int,
    dest_account_id: int | None,
) -> None:
    """Load the user's accounts and apply :func:`validate_transit_shape`."""
    if direction is not Direction.TRANSIT:
        return
    account = accounts_repo.find_by_id(conn, user_id, account_id)
    if account is None:
        raise ValidationError("unknown account")
    dest = (
        accounts_repo.find_by_id(conn, user_id, dest_account_id)
        if dest_account_id is not None
        else None
    )
    if dest_account_id is not None and dest is None:
        raise ValidationError("unknown destination")
    validate_transit_shape(direction, account, dest)


def transit_shape_error(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    direction: Direction,
    account_id: int,
    dest_account_id: int | None,
) -> str | None:
    """Like :func:`check_transit_shape` but returns the form error message or None."""
    try:
        check_transit_shape(
            conn,
            user_id,
            direction=direction,
            account_id=account_id,
            dest_account_id=dest_account_id,
        )
    except ValidationError as exc:
        return str(exc)
    return None


def validate_entry(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    category_id: int,
    account_id: int,
    dest_account_id: int | None,
    amount: int,
    description: str,
) -> None:
    """Domain rules shared by transaction and planned writes (raises :class:`ValidationError`).

    Description length, a positive amount (adjustments are stored signed), and the transit shape.
    A category that is not the caller's is left to the repository's ownership check.
    """
    if (too_long := length_error(description, maximum=DESCRIPTION_MAX_LENGTH)) is not None:
        raise ValidationError(f"description {too_long}")
    category = categories_repo.find_by_id(conn, user_id, category_id, include_deleted=True)
    if category is None:
        return
    if category.direction is not Direction.ADJUSTMENT and amount <= 0:
        raise ValidationError("amount must be positive")
    check_transit_shape(
        conn,
        user_id,
        direction=category.direction,
        account_id=account_id,
        dest_account_id=dest_account_id,
    )


def validate_patched_entry(
    conn: sqlite3.Connection,
    user_id: int,
    existing: Transaction | PlannedTransaction | None,
    patch: PatchTransaction | PatchPlannedTransaction,
) -> None:
    """:func:`validate_entry` on a stored row with ``patch`` applied (unset fields keep the row).

    A missing row is left to the repository's own not-found error.
    """
    if existing is None:
        return
    validate_entry(
        conn,
        user_id,
        category_id=existing.category_id if patch.category_id is None else patch.category_id,
        account_id=existing.account_id if patch.account_id is None else patch.account_id,
        dest_account_id=(
            existing.dest_account_id if patch.dest_account_id is None else patch.dest_account_id
        ),
        amount=existing.amount if patch.amount is None else patch.amount,
        description=existing.description if patch.description is None else patch.description,
    )


def find_by_id(
    conn: sqlite3.Connection, user_id: int, txn_id: int, *, include_deleted: bool = False
) -> Transaction | None:
    """The caller's transaction, or ``None`` (soft-deleted rows only with ``include_deleted``)."""
    return transactions_repo.find_by_id(conn, user_id, txn_id, include_deleted=include_deleted)


def list_filtered(
    conn: sqlite3.Connection,
    user_id: int,
    filters: TransactionFilter,
    *,
    include_deleted: bool = False,
) -> list[Transaction]:
    """Transactions matching ``filters`` for the caller."""
    return transactions_repo.list_filtered(conn, user_id, filters, include_deleted=include_deleted)


def count_filtered(
    conn: sqlite3.Connection,
    user_id: int,
    filters: TransactionFilter | None = None,
    *,
    include_deleted: bool = False,
) -> int:
    """Number of the caller's transactions matching ``filters``."""
    return transactions_repo.count_filtered(conn, user_id, filters, include_deleted=include_deleted)


def list_recently_deleted(
    conn: sqlite3.Connection, user_id: int, *, days: int = 90, limit: int = 500
) -> list[Transaction]:
    """Transactions soft-deleted within ``days``, newest first."""
    return transactions_repo.list_recently_deleted(conn, user_id, days=days, limit=limit)


def create(conn: sqlite3.Connection, user_id: int, data: NewTransaction) -> Transaction:
    """Create a transaction after :func:`validate_entry` (one mutation: row and audit atomic)."""
    validate_entry(
        conn,
        user_id,
        category_id=data.category_id,
        account_id=data.account_id,
        dest_account_id=data.dest_account_id,
        amount=data.amount,
        description=data.description,
    )
    return transactions_repo.create(conn, user_id, data)


def update(
    conn: sqlite3.Connection, user_id: int, txn_id: int, data: PatchTransaction
) -> Transaction:
    """Patch a transaction; the merged result must satisfy :func:`validate_entry`."""
    stored = transactions_repo.find_by_id(conn, user_id, txn_id, include_deleted=True)
    validate_patched_entry(conn, user_id, stored, data)
    return transactions_repo.update(conn, user_id, txn_id, data)


def soft_delete(conn: sqlite3.Connection, user_id: int, txn_id: int) -> None:
    """Soft-delete one transaction."""
    transactions_repo.soft_delete(conn, user_id, txn_id)


def undelete(conn: sqlite3.Connection, user_id: int, txn_id: int) -> Transaction:
    """Restore a soft-deleted transaction."""
    return transactions_repo.undelete(conn, user_id, txn_id)


__all__ = [
    "UnsupportedDirectionError",
    "ValidationError",
    "check_transit_shape",
    "count_filtered",
    "create",
    "find_by_id",
    "list_filtered",
    "list_recently_deleted",
    "soft_delete",
    "transit_shape_error",
    "undelete",
    "update",
    "validate_entry",
    "validate_patched_entry",
    "validate_transit_shape",
]
