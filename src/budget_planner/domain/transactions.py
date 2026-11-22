"""Transaction entity + DTOs + filter."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime
from typing import assert_never

from budget_planner.domain.enums import Direction


@dataclass(frozen=True, slots=True, kw_only=True)
class Transaction:
    """Persisted transaction row.

    `amount` is positive integer minor units except when the paired category
    has direction=`adjustment` (ADR-0008).

    Promotion provenance (ADR-0012 planned → actual, ADR-0038 recurring →
    actual) is tracked by two mutually-exclusive columns:
    `promoted_from_planned_id` and `promoted_from_recurring_rule_id` +
    `promoted_from_recurring_date`. The XOR invariant lives in the service
    layer (not a CHECK constraint) so the migration stays additive.
    """

    id: int
    user_id: int
    operation_date: date
    category_id: int
    account_id: int
    dest_account_id: int | None
    amount: int
    description: str
    promoted_from_planned_id: int | None
    promoted_from_recurring_rule_id: int | None
    promoted_from_recurring_date: date | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class NewTransaction:
    """Insertable fields for a new transaction."""

    operation_date: date
    category_id: int
    account_id: int
    amount: int
    description: str = ""
    dest_account_id: int | None = None
    promoted_from_planned_id: int | None = None
    promoted_from_recurring_rule_id: int | None = None
    promoted_from_recurring_date: date | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PatchTransaction:
    """Partial update DTO."""

    operation_date: date | None = None
    category_id: int | None = None
    account_id: int | None = None
    dest_account_id: int | None = None
    amount: int | None = None
    description: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name) is not None
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class TransactionFilter:
    """Filter DTO consumed by `transactions.list_filtered`.

    `tuple` instead of `list` so the DTO is hashable and truly immutable.
    """

    date_from: date | None = None
    date_to: date | None = None
    up_to_date: date | None = None
    account_ids: tuple[int, ...] = ()
    category_ids: tuple[int, ...] = ()
    directions: tuple[Direction, ...] = ()
    amount_min: int | None = None
    amount_max: int | None = None
    description_contains: str | None = None
    account_or_dest: int | None = None
    live_accounts_only: bool = False  # ADR-0136: derived reads skip soft-deleted accounts
    limit: int | None = None
    offset: int = 0
    order_desc: bool = False


@dataclass(frozen=True, slots=True)
class SignedLeg:
    """Per-account signed effect of one transaction or planned item (ADR-0008)."""

    account_id: int
    amount_minor: int


def signed_legs(
    direction: Direction, amount: int, account_id: int, dest_account_id: int | None
) -> tuple[SignedLeg, ...]:
    """Canonical direction-to-sign rule: one or two signed legs of an amount (ADR-0008, 0009).

    * ``income`` is ``(account, +amount)``; ``expense`` is ``(account, -amount)``.
    * ``transit`` is ``(account, -amount)`` plus ``(dest, +amount)``; a missing destination raises.
    * ``adjustment`` is ``(account, +amount)`` because the amount is stored already signed.
    """
    match direction:
        case Direction.INCOME | Direction.ADJUSTMENT:
            return (SignedLeg(account_id=account_id, amount_minor=amount),)
        case Direction.EXPENSE:
            return (SignedLeg(account_id=account_id, amount_minor=-amount),)
        case Direction.TRANSIT:
            if dest_account_id is None:
                raise ValueError("transit transaction missing dest_account_id")
            return (
                SignedLeg(account_id=account_id, amount_minor=-amount),
                SignedLeg(account_id=dest_account_id, amount_minor=amount),
            )
        case _ as unreachable:
            assert_never(unreachable)
