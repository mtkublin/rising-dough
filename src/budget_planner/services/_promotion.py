"""Shared promotion validator (T-118).

Both the planned → actual (ADR-0012) and recurring → actual (ADR-0038)
promotion flows must enforce the same guards:

- `direction=adjustment` is unsupported (reconciliation handles it).
- amount must be non-zero.
- transit shape (`transactions.validate_transit_shape`, ADR-0008 amendment 2026-11-21).

The error classes also live here so the planned service can re-export them
without creating an import cycle. Callers may import either module —
``services.planned.ValidationError`` and ``services._promotion.ValidationError``
reference the same class.
"""

from __future__ import annotations

import sqlite3

from budget_planner.domain.enums import Direction
from budget_planner.services.transactions import (
    UnsupportedDirectionError,
    ValidationError,
    check_transit_shape,
)


def validate_promotion(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    direction: Direction,
    account_id: int,
    dest_account_id: int | None,
    amount: int,
) -> None:
    """Raise if a promotion payload violates the shared contract."""
    if direction is Direction.ADJUSTMENT:
        raise UnsupportedDirectionError(
            "adjustment promotion is handled by the reconciliation flow"
        )
    if amount == 0:
        raise ValidationError("amount must be non-zero")
    check_transit_shape(
        conn,
        user_id,
        direction=direction,
        account_id=account_id,
        dest_account_id=dest_account_id,
    )


__all__ = ["UnsupportedDirectionError", "ValidationError", "validate_promotion"]
