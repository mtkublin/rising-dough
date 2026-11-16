"""Transaction entity + DTOs + filter."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime
from typing import Any

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

    def as_dict(self) -> dict[str, Any]:
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
    limit: int | None = None
    offset: int = 0
    order_desc: bool = False
