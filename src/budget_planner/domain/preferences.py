"""User preferences entity + DTOs + known keys (ADR-0025)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final


@dataclass(frozen=True, slots=True, kw_only=True)
class UserPreference:
    """Persisted user preference row."""

    id: int
    user_id: int
    key: str
    value: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class NewUserPreference:
    """Insertable fields for a new preference."""

    key: str
    value: str


PREF_INCOME_ANCHOR_CATEGORY_ID: Final[str] = "income_anchor_category_id"


__all__ = [
    "PREF_INCOME_ANCHOR_CATEGORY_ID",
    "NewUserPreference",
    "UserPreference",
]
