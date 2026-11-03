from __future__ import annotations

import sqlite3

import pytest

from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.preferences import PREF_INCOME_ANCHOR_CATEGORY_ID
from budget_planner.repositories import (
    categories as categories_repo,
    preferences as preferences_repo,
)
from budget_planner.services import preferences as preferences_service
from budget_planner.services.preferences import InvalidAnchorCategoryError

USER_ID = 1


def _mk_category(conn: sqlite3.Connection, name: str, direction: Direction) -> int:
    return categories_repo.create(conn, USER_ID, NewCategory(name=name, direction=direction)).id


def test_get_returns_none_when_unset(conn: sqlite3.Connection) -> None:
    assert preferences_service.get_income_anchor_category_id(conn, USER_ID) is None


def test_get_returns_int_when_set(conn: sqlite3.Connection) -> None:
    cid = _mk_category(conn, "Salary", Direction.INCOME)
    preferences_service.set_income_anchor_category_id(conn, 1, cid)
    assert preferences_service.get_income_anchor_category_id(conn, USER_ID) == cid


def test_get_returns_none_when_stored_value_is_corrupt(
    conn: sqlite3.Connection,
) -> None:
    preferences_repo.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, "not-an-int")
    assert preferences_service.get_income_anchor_category_id(conn, USER_ID) is None


def test_set_persists_round_trip(conn: sqlite3.Connection) -> None:
    cid = _mk_category(conn, "Salary", Direction.INCOME)
    preferences_service.set_income_anchor_category_id(conn, 1, cid)
    row = preferences_repo.get(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID)
    assert row is not None
    assert row.value == str(cid)


def test_set_none_clears(conn: sqlite3.Connection) -> None:
    cid = _mk_category(conn, "Salary", Direction.INCOME)
    preferences_service.set_income_anchor_category_id(conn, 1, cid)
    preferences_service.set_income_anchor_category_id(conn, 1, None)
    assert preferences_repo.get(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID) is None


def test_set_clear_when_already_absent_is_noop(conn: sqlite3.Connection) -> None:
    preferences_service.set_income_anchor_category_id(conn, 1, None)
    assert preferences_repo.get(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID) is None


def test_set_rejects_unknown_category(conn: sqlite3.Connection) -> None:
    with pytest.raises(InvalidAnchorCategoryError):
        preferences_service.set_income_anchor_category_id(conn, 1, 9999)


def test_set_rejects_soft_deleted_category(conn: sqlite3.Connection) -> None:
    cid = _mk_category(conn, "Salary", Direction.INCOME)
    categories_repo.soft_delete(conn, USER_ID, cid)
    with pytest.raises(InvalidAnchorCategoryError):
        preferences_service.set_income_anchor_category_id(conn, 1, cid)


@pytest.mark.parametrize(
    "direction",
    [Direction.EXPENSE, Direction.TRANSIT, Direction.ADJUSTMENT],
)
def test_set_rejects_wrong_direction(conn: sqlite3.Connection, direction: Direction) -> None:
    cid = _mk_category(conn, f"NotIncome-{direction.value}", direction)
    with pytest.raises(InvalidAnchorCategoryError):
        preferences_service.set_income_anchor_category_id(conn, 1, cid)


def test_resolve_returns_category_when_live(conn: sqlite3.Connection) -> None:
    cid = _mk_category(conn, "Salary", Direction.INCOME)
    preferences_service.set_income_anchor_category_id(conn, 1, cid)
    resolved = preferences_service.resolve_income_anchor_category(conn, USER_ID)
    assert resolved is not None
    assert resolved.id == cid
    assert resolved.name == "Salary"


def test_resolve_returns_none_when_unset(conn: sqlite3.Connection) -> None:
    assert preferences_service.resolve_income_anchor_category(conn, USER_ID) is None


def test_resolve_returns_none_when_soft_deleted(conn: sqlite3.Connection) -> None:
    cid = _mk_category(conn, "Salary", Direction.INCOME)
    preferences_service.set_income_anchor_category_id(conn, 1, cid)
    categories_repo.soft_delete(conn, USER_ID, cid)
    assert preferences_service.resolve_income_anchor_category(conn, USER_ID) is None
    # Stale row stays — observability per ADR-0025.
    assert preferences_repo.get(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID) is not None


def test_resolve_returns_none_when_direction_changed_underneath(
    conn: sqlite3.Connection,
) -> None:
    cid = _mk_category(conn, "Salary", Direction.INCOME)
    preferences_service.set_income_anchor_category_id(conn, 1, cid)
    # Direction is immutable via public API (ADR-0008). Defence in depth: a
    # rogue direct SQL update must not break the resolver.
    conn.execute("UPDATE categories SET direction = 'expense' WHERE id = ?", (cid,))
    assert preferences_service.resolve_income_anchor_category(conn, USER_ID) is None
