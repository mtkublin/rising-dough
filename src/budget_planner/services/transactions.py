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
from budget_planner.repositories import accounts as accounts_repo
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


__all__ = [
    "UnsupportedDirectionError",
    "ValidationError",
    "check_transit_shape",
    "transit_shape_error",
    "validate_transit_shape",
]
