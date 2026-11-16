from __future__ import annotations

import sqlite3

from budget_planner.domain.budgets import (
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.repositories import audit, budgets

USER_ID = 1


def test_set_and_clear_default(conn: sqlite3.Connection, category_id: int) -> None:
    created = budgets.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=category_id, amount=5000)
    )
    assert created.amount == 5000
    assert budgets.get_default(conn, USER_ID, category_id) == created
    assert budgets.list_defaults(conn, USER_ID) == [created]

    updated = budgets.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=category_id, amount=7000)
    )
    assert updated.amount == 7000

    budgets.clear_default(conn, USER_ID, category_id)
    assert budgets.get_default(conn, USER_ID, category_id) is None
    # Clearing again is a no-op.
    budgets.clear_default(conn, USER_ID, category_id)

    ops = [e.operation.value for e in audit.list_entries(conn, "budget_default", created.id)]
    assert ops == ["create", "update", "delete"]


def test_set_and_clear_recurring(conn: sqlite3.Connection, category_id: int) -> None:
    created = budgets.set_recurring(
        conn,
        USER_ID,
        NewBudgetRecurringOverride(category_id=category_id, month=12, amount=2000),
    )
    assert created.month == 12
    assert budgets.get_recurring(conn, USER_ID, category_id, 12) == created
    assert budgets.list_recurring(conn, USER_ID) == [created]

    budgets.set_recurring(
        conn,
        USER_ID,
        NewBudgetRecurringOverride(category_id=category_id, month=12, amount=3000),
    )
    assert budgets.get_recurring(conn, USER_ID, category_id, 12).amount == 3000  # type: ignore[union-attr]

    budgets.clear_recurring(conn, USER_ID, category_id, 12)
    assert budgets.get_recurring(conn, USER_ID, category_id, 12) is None
    budgets.clear_recurring(conn, USER_ID, category_id, 11)  # no-op


def test_set_and_clear_one_off(conn: sqlite3.Connection, category_id: int) -> None:
    created = budgets.set_one_off(
        conn,
        USER_ID,
        NewBudgetOneOffOverride(category_id=category_id, year=2026, month=1, amount=1000),
    )
    assert budgets.get_one_off(conn, USER_ID, category_id, 2026, 1) == created
    assert budgets.list_one_off(conn, USER_ID, year=2026) == [created]
    assert budgets.list_one_off(conn, USER_ID) == [created]

    bumped = budgets.set_one_off(
        conn,
        USER_ID,
        NewBudgetOneOffOverride(category_id=category_id, year=2026, month=1, amount=1500),
    )
    assert bumped.id == created.id

    budgets.clear_one_off(conn, USER_ID, category_id, 2026, 1)
    assert budgets.get_one_off(conn, USER_ID, category_id, 2026, 1) is None
    budgets.clear_one_off(conn, USER_ID, category_id, 2026, 2)  # no-op
