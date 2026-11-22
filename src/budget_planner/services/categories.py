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
from collections.abc import Callable
from zoneinfo import ZoneInfo

from budget_planner.domain.categories import (
    Category,
    NewCategory,
    PatchCategory,
    new_category_errors,
    patch_category_errors,
)
from budget_planner.domain.enums import Direction
from budget_planner.domain.errors import ValidationError, require_present
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


def expense_categories(
    conn: sqlite3.Connection, user_id: int, *, include_archived: bool = True
) -> list[Category]:
    """Expense-direction categories; archived ones are included by default (actuals selector).

    Archived categories keep their booked transactions in spent, analytics and forecast
    actuals (ADR-0136). Budgets use :func:`budgeted_expense_categories` instead.
    """
    return [
        c
        for c in categories_repo.list_all(conn, user_id, include_deleted=include_archived)
        if c.direction is Direction.EXPENSE
    ]


def expense_category_ids(conn: sqlite3.Connection, user_id: int) -> list[int]:
    """Ids of every expense category, archived included: the actuals selector (ADR-0136)."""
    return [c.id for c in expense_categories(conn, user_id)]


def reserves_budget(category: Category, year: int, month: int, *, display_timezone: str) -> bool:
    """The one budget predicate: does ``category`` reserve budget in ``year``/``month``?

    A live category always does. An archived one (``deleted_at`` set) reserves nothing from
    its archive month onward; earlier months keep it (ADR-0136, T-Q279). The archive month
    is the month of ``deleted_at`` (stored UTC) in ``display_timezone`` (ADR-0007).
    """
    if category.deleted_at is None:
        return True
    archived = category.deleted_at.astimezone(ZoneInfo(display_timezone))
    return (year, month) < (archived.year, archived.month)


def budget_reserver(
    conn: sqlite3.Connection, user_id: int, *, display_timezone: str
) -> Callable[[int, int, int], bool]:
    """Return ``reserves(category_id, year, month)`` over every category, one read.

    For the month loops of the forecast and the batch resolver; an id the user does not own
    is not archived here, so it keeps whatever the caller resolves for it.
    """
    by_id = {c.id: c for c in categories_repo.list_all(conn, user_id, include_deleted=True)}

    def reserves(category_id: int, year: int, month: int) -> bool:
        cat = by_id.get(category_id)
        return cat is None or reserves_budget(cat, year, month, display_timezone=display_timezone)

    return reserves


def budgeted_expense_categories(
    conn: sqlite3.Connection,
    user_id: int,
    year: int,
    month: int,
    *,
    display_timezone: str,
) -> list[Category]:
    """Expense categories that reserve budget in ``year``/``month`` (:func:`reserves_budget`)."""
    return [
        c
        for c in expense_categories(conn, user_id)
        if reserves_budget(c, year, month, display_timezone=display_timezone)
    ]


def budgeted_expense_category_ids(
    conn: sqlite3.Connection,
    user_id: int,
    year: int,
    month: int,
    *,
    display_timezone: str,
) -> list[int]:
    """Ids of :func:`budgeted_expense_categories`."""
    return [
        c.id
        for c in budgeted_expense_categories(
            conn, user_id, year, month, display_timezone=display_timezone
        )
    ]


def _live_rule_refs(conn: sqlite3.Connection, user_id: int, category_id: int) -> int:
    """Count active recurring rules whose category is ``category_id``."""
    return sum(
        1
        for rule in recurring_repo.list_rules(conn, user_id, active_only=True)
        if rule.category_id == category_id
    )


def archive(
    conn: sqlite3.Connection,
    user_id: int,
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
    cat = categories_repo.find_by_id(conn, user_id, category_id)
    if cat is None:
        raise CategoryNotFoundError(category_id)
    if cat.is_system:
        raise SystemCategoryError(category_id)
    refs = _live_rule_refs(conn, user_id, category_id)
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
    categories_repo.soft_delete(conn, user_id, category_id)
    return require_present(
        categories_repo.find_by_id(conn, user_id, category_id, include_deleted=True),
        "archived category",
    )


def restore(conn: sqlite3.Connection, user_id: int, category_id: int) -> Category:
    """Clear ``deleted_at`` on a soft-deleted category."""
    cat = categories_repo.find_by_id(conn, user_id, category_id, include_deleted=True)
    if cat is None:
        raise CategoryNotFoundError(category_id)
    if cat.deleted_at is None:
        raise CategoryNotFoundError(category_id)
    return categories_repo.undelete(conn, user_id, category_id)


def find_by_id(
    conn: sqlite3.Connection, user_id: int, category_id: int, *, include_deleted: bool = False
) -> Category | None:
    """The caller's category, or ``None`` (soft-deleted rows only with ``include_deleted``)."""
    return categories_repo.find_by_id(conn, user_id, category_id, include_deleted=include_deleted)


def find_by_name(
    conn: sqlite3.Connection, user_id: int, name: str, *, include_deleted: bool = False
) -> Category | None:
    """The caller's category with this exact name, or ``None``."""
    return categories_repo.find_by_name(conn, user_id, name, include_deleted=include_deleted)


def list_all(
    conn: sqlite3.Connection, user_id: int, *, include_deleted: bool = False
) -> list[Category]:
    """The caller's categories."""
    return categories_repo.list_all(conn, user_id, include_deleted=include_deleted)


def list_recently_deleted(
    conn: sqlite3.Connection, user_id: int, *, days: int = 90, limit: int = 500
) -> list[Category]:
    """Categories soft-deleted within ``days``, newest first."""
    return categories_repo.list_recently_deleted(conn, user_id, days=days, limit=limit)


def create(conn: sqlite3.Connection, user_id: int, data: NewCategory) -> Category:
    """Create a category; :class:`ValidationError` (nothing written) for a bad field."""
    if errors := new_category_errors(data):
        raise ValidationError(fields=errors)
    return categories_repo.create(conn, user_id, data)


def update(
    conn: sqlite3.Connection, user_id: int, category_id: int, data: PatchCategory
) -> Category:
    """Patch a category; :class:`ValidationError` (nothing written) for a bad field."""
    if errors := patch_category_errors(data):
        raise ValidationError(fields=errors)
    return categories_repo.update(conn, user_id, category_id, data)


def soft_delete(conn: sqlite3.Connection, user_id: int, category_id: int) -> None:
    """Soft-delete one category (row and audit are one repository mutation)."""
    categories_repo.soft_delete(conn, user_id, category_id)


__all__ = [
    "CategoryHasLiveRulesError",
    "CategoryNotFoundError",
    "SystemCategoryError",
    "archive",
    "budget_reserver",
    "budgeted_expense_categories",
    "budgeted_expense_category_ids",
    "create",
    "expense_categories",
    "expense_category_ids",
    "find_by_id",
    "find_by_name",
    "list_all",
    "list_recently_deleted",
    "reserves_budget",
    "restore",
    "soft_delete",
    "update",
]
