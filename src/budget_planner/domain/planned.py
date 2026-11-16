"""Planned transaction entity + DTOs + filter."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime
from typing import Any

from budget_planner.domain.enums import Direction


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannedTransaction:
    """Persisted planned transaction row."""

    id: int
    user_id: int
    operation_date: date
    category_id: int
    account_id: int
    dest_account_id: int | None
    amount: int
    description: str
    recurring_rule_id: int | None
    occurrence_date: date | None
    promoted_to_txn_id: int | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class NewPlannedTransaction:
    """Insertable fields for a new planned transaction."""

    operation_date: date
    category_id: int
    account_id: int
    amount: int
    description: str = ""
    dest_account_id: int | None = None
    recurring_rule_id: int | None = None
    occurrence_date: date | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PatchPlannedTransaction:
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
class PlannedFilter:
    """Filter DTO consumed by `planned.list_filtered`."""

    date_from: date | None = None
    date_to: date | None = None
    account_ids: tuple[int, ...] = ()
    category_ids: tuple[int, ...] = ()
    directions: tuple[Direction, ...] = ()
    recurring_rule_id: int | None = None
    promoted: bool | None = None
    limit: int | None = None
    offset: int = 0
