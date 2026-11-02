"""Income anchor preference service (ADR-0025).

Validates direction + liveness at the service boundary so repositories stay
dumb and downstream callers (budget service, web router) can trust the
preference payload.
"""

from __future__ import annotations

import logging
import sqlite3

from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.domain.preferences import PREF_INCOME_ANCHOR_CATEGORY_ID
from budget_planner.repositories import (
    categories as categories_repo,
    preferences as preferences_repo,
)

_logger = logging.getLogger(__name__)


class InvalidAnchorCategoryError(ValueError):
    """Raised when the caller tries to pin the anchor to an invalid category."""


def get_income_anchor_category_id(conn: sqlite3.Connection, user_id: int = 1) -> int | None:
    """Return the stored anchor category id, or ``None`` if unset / corrupt."""
    row = preferences_repo.get(conn, user_id, PREF_INCOME_ANCHOR_CATEGORY_ID)
    if row is None:
        return None
    try:
        return int(row.value)
    except ValueError:
        _logger.warning(
            "corrupt income_anchor_category_id value=%r (user_id=%s)",
            row.value,
            user_id,
        )
        return None


def set_income_anchor_category_id(
    conn: sqlite3.Connection,
    user_id: int,
    category_id: int | None,
) -> None:
    """Set or clear the income anchor.

    ``category_id = None`` clears the preference (row deleted).
    Rejects categories that do not exist, are soft-deleted, or whose direction
    is not INCOME.
    """
    if category_id is None:
        preferences_repo.delete(conn, user_id, PREF_INCOME_ANCHOR_CATEGORY_ID)
        return
    category = categories_repo.find_by_id(conn, category_id)
    if category is None:
        raise InvalidAnchorCategoryError(f"category {category_id} not found or soft-deleted")
    if category.direction is not Direction.INCOME:
        raise InvalidAnchorCategoryError(
            f"category {category_id} direction={category.direction.value}; "
            "income anchor requires direction=income"
        )
    preferences_repo.upsert(conn, user_id, PREF_INCOME_ANCHOR_CATEGORY_ID, str(category_id))


def resolve_income_anchor_category(conn: sqlite3.Connection, user_id: int = 1) -> Category | None:
    """Return the live anchor Category or ``None`` if unset / stale.

    Permissive: a stored id that no longer resolves (soft-deleted or direction
    flipped under its feet) returns ``None`` and the stale row stays — the
    user may rebind later. The web layer never sees an exception from this.
    """
    anchor_id = get_income_anchor_category_id(conn, user_id)
    if anchor_id is None:
        return None
    category = categories_repo.find_by_id(conn, anchor_id)
    if category is None:
        _logger.debug(
            "income anchor category_id=%s resolves to None (soft-deleted or missing)",
            anchor_id,
        )
        return None
    if category.direction is not Direction.INCOME:
        _logger.debug(
            "income anchor category_id=%s direction=%s (expected income)",
            anchor_id,
            category.direction.value,
        )
        return None
    return category


__all__ = [
    "InvalidAnchorCategoryError",
    "get_income_anchor_category_id",
    "resolve_income_anchor_category",
    "set_income_anchor_category_id",
]
