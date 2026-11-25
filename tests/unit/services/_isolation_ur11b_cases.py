"""Isolation cases for the month-override reads, clears and removal (T-UR11b).

Same world and conventions as ``_isolation_crud_cases.py``: a user never reads or clears the
other user's one-off or recurring override.
"""

from __future__ import annotations

import sqlite3

from budget_planner.domain.budgets import NewBudgetOneOffOverride, NewBudgetRecurringOverride
from budget_planner.services import budget_overrides, budget_rules
from tests.unit.services._isolation_registry import covers
from tests.unit.services.conftest import OTHER_ID, OWNER_ID, World

_YEAR = 2026
_MONTH = 3
_OWNER_AMOUNT = 90
_OTHER_AMOUNT = 170


def _seed_one_off(conn: sqlite3.Connection, world: World) -> None:
    for user_id, category, amount in (
        (OWNER_ID, world.owner.category_id, _OWNER_AMOUNT),
        (OTHER_ID, world.other.category_id, _OTHER_AMOUNT),
    ):
        budget_overrides.set_one_off(
            conn,
            user_id,
            NewBudgetOneOffOverride(category_id=category, year=_YEAR, month=_MONTH, amount=amount),
        )


def _seed_recurring(conn: sqlite3.Connection, world: World) -> None:
    for user_id, category, amount in (
        (OWNER_ID, world.owner.category_id, _OWNER_AMOUNT),
        (OTHER_ID, world.other.category_id, _OTHER_AMOUNT),
    ):
        budget_overrides.set_recurring(
            conn,
            user_id,
            NewBudgetRecurringOverride(category_id=category, month=_MONTH, amount=amount),
        )


@covers("budget_overrides.get_one_off")
def _case_get_one_off(conn: sqlite3.Connection, world: World) -> None:
    _seed_one_off(conn, world)
    own = budget_overrides.get_one_off(conn, OWNER_ID, world.owner.category_id, _YEAR, _MONTH)
    assert own is not None and own.amount == _OWNER_AMOUNT
    other = budget_overrides.get_one_off(conn, OTHER_ID, world.other.category_id, _YEAR, _MONTH)
    assert other is not None and other.amount == _OTHER_AMOUNT
    assert (
        budget_overrides.get_one_off(conn, OWNER_ID, world.other.category_id, _YEAR, _MONTH) is None
    )
    assert (
        budget_overrides.get_one_off(conn, OTHER_ID, world.owner.category_id, _YEAR, _MONTH) is None
    )


@covers("budget_overrides.get_recurring")
def _case_get_recurring(conn: sqlite3.Connection, world: World) -> None:
    _seed_recurring(conn, world)
    own = budget_overrides.get_recurring(conn, OWNER_ID, world.owner.category_id, _MONTH)
    assert own is not None and own.amount == _OWNER_AMOUNT
    other = budget_overrides.get_recurring(conn, OTHER_ID, world.other.category_id, _MONTH)
    assert other is not None and other.amount == _OTHER_AMOUNT
    assert budget_overrides.get_recurring(conn, OWNER_ID, world.other.category_id, _MONTH) is None
    assert budget_overrides.get_recurring(conn, OTHER_ID, world.owner.category_id, _MONTH) is None


@covers("budget_overrides.clear_one_off")
def _case_clear_one_off(conn: sqlite3.Connection, world: World) -> None:
    _seed_one_off(conn, world)
    budget_overrides.clear_one_off(conn, OTHER_ID, world.owner.category_id, _YEAR, _MONTH)
    assert (
        budget_overrides.get_one_off(conn, OWNER_ID, world.owner.category_id, _YEAR, _MONTH)
        is not None
    )
    budget_overrides.clear_one_off(conn, OWNER_ID, world.owner.category_id, _YEAR, _MONTH)
    assert (
        budget_overrides.get_one_off(conn, OWNER_ID, world.owner.category_id, _YEAR, _MONTH) is None
    )
    kept = budget_overrides.get_one_off(conn, OTHER_ID, world.other.category_id, _YEAR, _MONTH)
    assert kept is not None and kept.amount == _OTHER_AMOUNT


@covers("budget_overrides.clear_recurring")
def _case_clear_recurring(conn: sqlite3.Connection, world: World) -> None:
    _seed_recurring(conn, world)
    budget_overrides.clear_recurring(conn, OTHER_ID, world.owner.category_id, _MONTH)
    assert (
        budget_overrides.get_recurring(conn, OWNER_ID, world.owner.category_id, _MONTH) is not None
    )
    budget_overrides.clear_recurring(conn, OWNER_ID, world.owner.category_id, _MONTH)
    assert budget_overrides.get_recurring(conn, OWNER_ID, world.owner.category_id, _MONTH) is None
    kept = budget_overrides.get_recurring(conn, OTHER_ID, world.other.category_id, _MONTH)
    assert kept is not None and kept.amount == _OTHER_AMOUNT


@covers("budget_rules.remove_override")
def _case_remove_override(conn: sqlite3.Connection, world: World) -> None:
    _seed_one_off(conn, world)
    _seed_recurring(conn, world)
    cat = world.owner.category_id
    budget_rules.remove_override(conn, OTHER_ID, cat, month=_MONTH, year=_YEAR)
    budget_rules.remove_override(conn, OTHER_ID, cat, month=_MONTH, year=None)
    assert budget_overrides.get_one_off(conn, OWNER_ID, cat, _YEAR, _MONTH) is not None
    assert budget_overrides.get_recurring(conn, OWNER_ID, cat, _MONTH) is not None
    budget_rules.remove_override(conn, OWNER_ID, cat, month=_MONTH, year=_YEAR)
    assert budget_overrides.get_one_off(conn, OWNER_ID, cat, _YEAR, _MONTH) is None
    assert budget_overrides.get_recurring(conn, OWNER_ID, cat, _MONTH) is not None
    budget_rules.remove_override(conn, OWNER_ID, cat, month=_MONTH, year=None)
    assert budget_overrides.get_recurring(conn, OWNER_ID, cat, _MONTH) is None
    other_cat = world.other.category_id
    assert budget_overrides.get_one_off(conn, OTHER_ID, other_cat, _YEAR, _MONTH) is not None
    assert budget_overrides.get_recurring(conn, OTHER_ID, other_cat, _MONTH) is not None
