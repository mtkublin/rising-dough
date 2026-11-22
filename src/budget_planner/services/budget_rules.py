"""Budget Rules editor rows and override dispatch (T-Q266, ADR-0031 section 2).

Moved out of the budget router: the router parses the form, this module decides what a parsed
override means and which repository entry point stores it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from budget_planner.domain.budgets import (
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.domain.enums import Direction
from budget_planner.services import budget_overrides, categories as categories_service

OverrideCommand = NewBudgetDefault | NewBudgetRecurringOverride | NewBudgetOneOffOverride


@dataclass(frozen=True, slots=True)
class RulesRow:
    """One row of the Rules editor table (ADR-0031 section 2: category + default)."""

    category_id: int
    category_name: str
    category_direction: Direction
    category_color: str | None
    default_minor: int | None


def rules_rows(conn: sqlite3.Connection, user_id: int) -> tuple[RulesRow, ...]:
    """Per-expense-category rows for the Rules editor, sorted by name.

    Each row carries only the default amount (nullable); recurring and one-off overrides are
    authored on demand via the per-row Override slide-over.
    """
    cats = [
        c
        for c in categories_service.list_all(conn, user_id)
        if not c.is_system and c.direction is Direction.EXPENSE
    ]
    defaults = {d.category_id: d.amount for d in budget_overrides.list_defaults(conn, user_id)}
    rows = [
        RulesRow(
            category_id=cat.id,
            category_name=cat.name,
            category_direction=cat.direction,
            category_color=cat.color,
            default_minor=defaults.get(cat.id),
        )
        for cat in cats
    ]
    rows.sort(key=lambda r: r.category_name.casefold())
    return tuple(rows)


def apply_override(conn: sqlite3.Connection, user_id: int, command: OverrideCommand) -> None:
    """Store one parsed default, recurring or one-off budget amount."""
    if isinstance(command, NewBudgetDefault):
        budget_overrides.set_default(conn, user_id, command)
    elif isinstance(command, NewBudgetRecurringOverride):
        budget_overrides.set_recurring(conn, user_id, command)
    else:
        budget_overrides.set_one_off(conn, user_id, command)
