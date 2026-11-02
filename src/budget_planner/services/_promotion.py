"""Shared promotion validator (T-118).

Both the planned → actual (ADR-0012) and recurring → actual (ADR-0038)
promotion flows must enforce the same guards:

- `direction=adjustment` is unsupported (reconciliation handles it).
- amount must be non-zero.
- transit requires `dest_account_id` whose currency matches the source.

The error classes also live here so the planned service can re-export them
without creating an import cycle. Callers may import either module —
``services.planned.ValidationError`` and ``services._promotion.ValidationError``
reference the same class.
"""

from __future__ import annotations

import sqlite3

from budget_planner.domain.enums import Direction
from budget_planner.repositories import accounts as accounts_repo


class UnsupportedDirectionError(RuntimeError):
    """Raised for direction=adjustment; use reconciliation service instead."""


class ValidationError(ValueError):
    """Raised for invalid promotion payloads (zero amount, cross-currency transit, …)."""


def validate_promotion(
    conn: sqlite3.Connection,
    *,
    direction: Direction,
    account_id: int,
    dest_account_id: int | None,
    amount: int,
) -> None:
    """Raise if a promotion payload violates the shared contract.

    Parameters mirror the three fields that materialise on the resulting
    ``transactions`` row: source account, (optional) transit destination,
    and amount. ``direction`` is read from the paired category.
    """
    if direction is Direction.ADJUSTMENT:
        raise UnsupportedDirectionError(
            "adjustment promotion is handled by the reconciliation flow"
        )
    if amount == 0:
        raise ValidationError("amount must be non-zero")
    if direction is Direction.TRANSIT:
        if dest_account_id is None:
            raise ValidationError("transit requires dest_account_id")
        src = accounts_repo.find_by_id(conn, account_id)
        dst = accounts_repo.find_by_id(conn, dest_account_id)
        if src is None or dst is None:  # pragma: no cover - FK blocks it
            raise ValidationError("transit source or destination account not found")
        if src.currency != dst.currency:
            raise ValidationError(
                f"transit currencies must match (got {src.currency} vs {dst.currency})"
            )


__all__ = ["UnsupportedDirectionError", "ValidationError", "validate_promotion"]
