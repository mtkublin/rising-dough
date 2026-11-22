"""Budget default and override entry points for the web layer (T-Q241, T-Q285, ADR-0142).

Each write validates the amount and month (``domain.budgets.override_errors``) before the one
repository mutation (row and audit are atomic); a bad value raises ``ValidationError`` and writes
nothing. Reads are thin typed wrappers.
"""

from __future__ import annotations

import sqlite3

from budget_planner.domain.budgets import (
    BudgetDefault,
    BudgetOneOffOverride,
    BudgetRecurringOverride,
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
    override_errors,
)
from budget_planner.domain.errors import ValidationError
from budget_planner.repositories import budgets as budgets_repo


def _validate_override(*, amount: int, month: int | None = None) -> None:
    if errors := override_errors(amount=amount, month=month):
        raise ValidationError(fields=errors)


def get_default(
    conn: sqlite3.Connection, user_id: int, category_id: int, *, include_deleted: bool = False
) -> BudgetDefault | None:
    """The category's default budget row, or ``None``."""
    return budgets_repo.get_default(conn, user_id, category_id, include_deleted=include_deleted)


def list_defaults(
    conn: sqlite3.Connection, user_id: int, *, include_deleted: bool = False
) -> list[BudgetDefault]:
    """Every default budget row of the caller."""
    return budgets_repo.list_defaults(conn, user_id, include_deleted=include_deleted)


def set_default(conn: sqlite3.Connection, user_id: int, data: NewBudgetDefault) -> BudgetDefault:
    """Set a category's default budget (amount not negative)."""
    _validate_override(amount=data.amount)
    return budgets_repo.set_default(conn, user_id, data)


def set_recurring(
    conn: sqlite3.Connection, user_id: int, data: NewBudgetRecurringOverride
) -> BudgetRecurringOverride:
    """Set a month-of-year override (amount not negative, month 1 to 12)."""
    _validate_override(amount=data.amount, month=data.month)
    return budgets_repo.set_recurring(conn, user_id, data)


def set_one_off(
    conn: sqlite3.Connection, user_id: int, data: NewBudgetOneOffOverride
) -> BudgetOneOffOverride:
    """Set a single-month override (amount not negative, month 1 to 12)."""
    _validate_override(amount=data.amount, month=data.month)
    return budgets_repo.set_one_off(conn, user_id, data)


__all__ = [
    "get_default",
    "list_defaults",
    "set_default",
    "set_one_off",
    "set_recurring",
]
