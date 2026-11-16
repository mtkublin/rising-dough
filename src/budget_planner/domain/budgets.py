"""Budget tier entities + New DTOs (ADR-0014)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class BudgetDefault:
    """Default monthly budget for a category."""

    id: int
    user_id: int
    category_id: int
    amount: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class NewBudgetDefault:
    """Insertable fields for a default budget tier."""

    category_id: int
    amount: int


@dataclass(frozen=True, slots=True, kw_only=True)
class BudgetRecurringOverride:
    """Per-month-of-year recurring override."""

    id: int
    user_id: int
    category_id: int
    month: int
    amount: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class NewBudgetRecurringOverride:
    """Insertable fields for a recurring override tier."""

    category_id: int
    month: int
    amount: int


@dataclass(frozen=True, slots=True, kw_only=True)
class BudgetOneOffOverride:
    """One-off budget override pinned to a specific (year, month)."""

    id: int
    user_id: int
    category_id: int
    year: int
    month: int
    amount: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class NewBudgetOneOffOverride:
    """Insertable fields for a one-off override tier."""

    category_id: int
    year: int
    month: int
    amount: int
