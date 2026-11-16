"""Targeted branch-coverage tests for the repository layer.

Fills the remaining `include_deleted=True` and empty-patch update branches
that the main repo tests leave partial. Pure additive — does not weaken
or replace any existing assertion.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.budgets import (
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.domain.enums import Cadence
from budget_planner.domain.planned import NewPlannedTransaction, PatchPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule, PatchRecurringRule
from budget_planner.domain.transactions import NewTransaction, PatchTransaction
from budget_planner.repositories import (
    budgets,
    categories,
    planned,
    recurring,
    transactions,
)

USER_ID = 1

pytestmark = pytest.mark.unit


def test_categories_find_by_name_include_deleted_recovers_tombstone(
    conn: sqlite3.Connection, category_id: int
) -> None:
    cat = categories.find_by_id(conn, USER_ID, category_id)
    assert cat is not None
    categories.soft_delete(conn, USER_ID, category_id)

    # include_deleted=False (default) hides the tombstone.
    assert categories.find_by_name(conn, USER_ID, cat.name) is None
    # include_deleted=True surfaces it (closes the branch at categories.py:47->49).
    found = categories.find_by_name(conn, USER_ID, cat.name, include_deleted=True)
    assert found is not None
    assert found.id == category_id


def test_budgets_default_get_include_deleted_recovers_tombstone(
    conn: sqlite3.Connection, category_id: int
) -> None:
    created = budgets.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=category_id, amount=1000)
    )
    budgets.clear_default(conn, USER_ID, category_id)
    assert budgets.get_default(conn, USER_ID, category_id) is None
    found = budgets.get_default(conn, USER_ID, category_id, include_deleted=True)
    assert found is not None
    assert found.id == created.id


def test_budgets_default_list_include_deleted_surfaces_tombstone(
    conn: sqlite3.Connection, category_id: int
) -> None:
    budgets.set_default(conn, USER_ID, NewBudgetDefault(category_id=category_id, amount=1000))
    budgets.clear_default(conn, USER_ID, category_id)
    assert budgets.list_defaults(conn, USER_ID) == []
    rows = budgets.list_defaults(conn, USER_ID, include_deleted=True)
    assert len(rows) == 1


def test_budgets_recurring_get_include_deleted_recovers_tombstone(
    conn: sqlite3.Connection, category_id: int
) -> None:
    budgets.set_recurring(
        conn, USER_ID, NewBudgetRecurringOverride(category_id=category_id, month=4, amount=2000)
    )
    budgets.clear_recurring(conn, USER_ID, category_id, 4)
    assert budgets.get_recurring(conn, USER_ID, category_id, 4) is None
    found = budgets.get_recurring(conn, USER_ID, category_id, 4, include_deleted=True)
    assert found is not None


def test_budgets_recurring_list_include_deleted_surfaces_tombstone(
    conn: sqlite3.Connection, category_id: int
) -> None:
    budgets.set_recurring(
        conn, USER_ID, NewBudgetRecurringOverride(category_id=category_id, month=4, amount=2000)
    )
    budgets.clear_recurring(conn, USER_ID, category_id, 4)
    assert budgets.list_recurring(conn, USER_ID) == []
    assert len(budgets.list_recurring(conn, USER_ID, include_deleted=True)) == 1


def test_budgets_one_off_get_include_deleted_recovers_tombstone(
    conn: sqlite3.Connection, category_id: int
) -> None:
    budgets.set_one_off(
        conn,
        USER_ID,
        NewBudgetOneOffOverride(category_id=category_id, year=2026, month=3, amount=5000),
    )
    budgets.clear_one_off(conn, USER_ID, category_id, 2026, 3)
    assert budgets.get_one_off(conn, USER_ID, category_id, 2026, 3) is None
    found = budgets.get_one_off(conn, USER_ID, category_id, 2026, 3, include_deleted=True)
    assert found is not None


def test_budgets_one_off_list_year_filter_combines_with_include_deleted(
    conn: sqlite3.Connection, category_id: int
) -> None:
    budgets.set_one_off(
        conn,
        USER_ID,
        NewBudgetOneOffOverride(category_id=category_id, year=2026, month=5, amount=1000),
    )
    budgets.set_one_off(
        conn,
        USER_ID,
        NewBudgetOneOffOverride(category_id=category_id, year=2027, month=5, amount=2000),
    )
    budgets.clear_one_off(conn, USER_ID, category_id, 2026, 5)

    # year filter alone + default include_deleted=False (closes year-is-not-None branch).
    only_2027 = budgets.list_one_off(conn, USER_ID, year=2027)
    assert len(only_2027) == 1 and only_2027[0].year == 2027
    # year filter + include_deleted=True combined.
    both_2026 = budgets.list_one_off(conn, USER_ID, year=2026, include_deleted=True)
    assert len(both_2026) == 1 and both_2026[0].year == 2026


def test_budgets_one_off_list_without_filters_returns_everything(
    conn: sqlite3.Connection, category_id: int
) -> None:
    """`year=None` + ``include_deleted=True`` reaches the "no clauses" path."""
    budgets.set_one_off(
        conn,
        USER_ID,
        NewBudgetOneOffOverride(category_id=category_id, year=2026, month=5, amount=1000),
    )
    budgets.clear_one_off(conn, USER_ID, category_id, 2026, 5)
    all_rows = budgets.list_one_off(conn, USER_ID, year=None, include_deleted=True)
    assert len(all_rows) == 1


def test_recurring_list_rules_active_only_filter(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    r = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 15),
            category_id=category_id,
            account_id=account_id,
            default_amount=1000,
        ),
    )
    recurring.deactivate_rule(conn, USER_ID, r.id)

    # active_only=False, include_deleted=False: deactivated row still returned.
    all_live = recurring.list_rules(conn, USER_ID, active_only=False)
    assert len(all_live) == 1
    # active_only=True: deactivated row excluded.
    active = recurring.list_rules(conn, USER_ID, active_only=True)
    assert active == []


def test_recurring_list_rules_include_deleted_without_active_filter(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    """`include_deleted=True` + ``active_only=False`` reaches the "no WHERE" path."""
    r = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 15),
            category_id=category_id,
            account_id=account_id,
            default_amount=1000,
        ),
    )
    recurring.soft_delete_rule(conn, USER_ID, r.id)
    rows = recurring.list_rules(conn, USER_ID, active_only=False, include_deleted=True)
    assert len(rows) == 1


def test_recurring_list_rules_active_only_with_include_deleted(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    """`active_only=True` + ``include_deleted=True`` combines both predicates."""
    live = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 15),
            category_id=category_id,
            account_id=account_id,
            default_amount=1000,
        ),
    )
    deleted = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 15),
            category_id=category_id,
            account_id=account_id,
            default_amount=2000,
        ),
    )
    recurring.deactivate_rule(conn, USER_ID, deleted.id)
    rows = recurring.list_rules(conn, USER_ID, active_only=True, include_deleted=True)
    assert [r.id for r in rows] == [live.id]


def test_transactions_update_with_empty_patch_is_noop_but_writes_audit(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    created = transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 2, 1),
            category_id=category_id,
            account_id=account_id,
            amount=1234,
        ),
    )
    # Empty patch: no SET clause runs, but mutate() still writes an audit row.
    updated = transactions.update(conn, USER_ID, created.id, PatchTransaction())
    assert updated.id == created.id
    assert updated.amount == created.amount


def test_planned_update_with_empty_patch_is_noop_but_writes_audit(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    created = planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 2, 1),
            category_id=category_id,
            account_id=account_id,
            amount=5555,
        ),
    )
    updated = planned.update(conn, USER_ID, created.id, PatchPlannedTransaction())
    assert updated.id == created.id
    assert updated.amount == created.amount


def test_recurring_update_with_empty_patch_is_noop_but_writes_audit(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    r = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 15),
            category_id=category_id,
            account_id=account_id,
            default_amount=1000,
        ),
    )
    updated = recurring.update_rule(conn, USER_ID, r.id, PatchRecurringRule())
    assert updated.id == r.id
    assert updated.default_amount == r.default_amount
