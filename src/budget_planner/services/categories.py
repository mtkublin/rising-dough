"""Categories service helpers — archive + restore (T-R44, ADR-0056 §6).

Soft-delete and undelete go through the repository helpers so audit
log entries + request ctx stay in-band (ADR-0019 / ADR-0022). System
categories (``is_system=1``) are protected: archive raises
:class:`SystemCategoryError`. Archive of an already-archived category
raises :class:`CategoryNotFoundError` so the UI can show "stale state".
"""

from __future__ import annotations

import logging
import sqlite3

from budget_planner.domain.categories import Category
from budget_planner.repositories import (
    categories as categories_repo,
    recurring as recurring_repo,
)

logger = logging.getLogger(__name__)


class CategoryNotFoundError(LookupError):
    """Raised when the category id is missing (or already archived)."""


class SystemCategoryError(RuntimeError):
    """Raised when attempting to archive a system (seeded) category."""


class CategoryHasLiveRulesError(RuntimeError):
    """Raised in block-mode when live recurring rules reference the category."""


def _live_rule_refs(conn: sqlite3.Connection, category_id: int) -> int:
    """Count active recurring rules whose category is ``category_id``."""
    return sum(
        1
        for rule in recurring_repo.list_rules(conn, active_only=True)
        if rule.category_id == category_id
    )


def archive(
    conn: sqlite3.Connection,
    category_id: int,
    *,
    block_on_live_rules: bool = False,
) -> Category:
    """Soft-delete a category.

    ``block_on_live_rules=True`` raises :class:`CategoryHasLiveRulesError`
    when any live recurring rule still references the category (T-R71
    block-mode). Warn-mode (default) logs a WARNING and proceeds — history
    stays queryable via ``include_deleted=True`` so overrides and
    historical transactions keep rendering.
    """
    cat = categories_repo.find_by_id(conn, category_id)
    if cat is None:
        raise CategoryNotFoundError(category_id)
    if cat.is_system:
        raise SystemCategoryError(category_id)
    refs = _live_rule_refs(conn, category_id)
    if refs > 0:
        if block_on_live_rules:
            raise CategoryHasLiveRulesError(
                f"category {category_id} is referenced by {refs} live recurring rule(s)"
            )
        logger.warning(
            "archive(category_id=%s) has %s live recurring rule reference(s)",
            category_id,
            refs,
        )
    categories_repo.soft_delete(conn, category_id)
    archived = categories_repo.find_by_id(conn, category_id, include_deleted=True)
    assert archived is not None
    return archived


def restore(conn: sqlite3.Connection, category_id: int) -> Category:
    """Clear ``deleted_at`` on a soft-deleted category.

    Raises :class:`CategoryNotFoundError` on a missing id OR on a category
    that is not currently archived — the latter signals a stale UI
    (double-POST of restore). Returns the hydrated :class:`Category`.
    """
    cat = categories_repo.find_by_id(conn, category_id, include_deleted=True)
    if cat is None:
        raise CategoryNotFoundError(category_id)
    if cat.deleted_at is None:
        raise CategoryNotFoundError(category_id)
    return categories_repo.undelete(conn, category_id)


__all__ = [
    "CategoryHasLiveRulesError",
    "CategoryNotFoundError",
    "SystemCategoryError",
    "archive",
    "restore",
]
