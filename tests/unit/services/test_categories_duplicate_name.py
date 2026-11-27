"""Live category names are unique per user: create and update refuse a duplicate (T-UR00b, F1.6)."""

from __future__ import annotations

import sqlite3

import pytest

from budget_planner.domain.categories import NewCategory, PatchCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.errors import ValidationError
from budget_planner.repositories import categories as categories_repo
from budget_planner.services import categories as categories_svc

USER_ID = 1


@pytest.fixture
def groc_id(conn: sqlite3.Connection) -> int:
    return categories_repo.create(
        conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id


def _count(conn: sqlite3.Connection) -> int:
    return len(categories_repo.list_all(conn, USER_ID, include_deleted=True))


def test_create_refuses_a_live_duplicate_name_and_writes_nothing(
    conn: sqlite3.Connection, groc_id: int
) -> None:
    before = _count(conn)
    with pytest.raises(ValidationError) as err:
        categories_svc.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        )
    assert err.value.fields == {"name": categories_svc.DUPLICATE_NAME_MESSAGE}
    assert _count(conn) == before


def test_update_refuses_another_categorys_name(conn: sqlite3.Connection, groc_id: int) -> None:
    rent = categories_repo.create(
        conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id
    with pytest.raises(ValidationError) as err:
        categories_svc.update(conn, USER_ID, rent, PatchCategory(name="Groceries"))
    assert err.value.fields == {"name": categories_svc.DUPLICATE_NAME_MESSAGE}
    stored = categories_repo.find_by_id(conn, USER_ID, rent)
    assert stored is not None
    assert stored.name == "Rent"


def test_update_allows_the_own_name_and_a_patch_without_a_name(
    conn: sqlite3.Connection, groc_id: int
) -> None:
    same = categories_svc.update(conn, USER_ID, groc_id, PatchCategory(name="Groceries"))
    assert same.name == "Groceries"
    recoloured = categories_svc.update(conn, USER_ID, groc_id, PatchCategory(color="#ef4444"))
    assert recoloured.color == "#ef4444"


def test_create_allows_the_name_of_an_archived_category(
    conn: sqlite3.Connection, groc_id: int
) -> None:
    categories_svc.archive(conn, USER_ID, groc_id)
    again = categories_svc.create(
        conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    )
    assert again.id != groc_id


def test_create_refuses_a_case_variant_across_directions(
    conn: sqlite3.Connection, groc_id: int
) -> None:
    before = _count(conn)
    with pytest.raises(ValidationError) as err:
        categories_svc.create(
            conn, USER_ID, NewCategory(name="groCERies", direction=Direction.INCOME)
        )
    assert err.value.fields == {"name": categories_svc.DUPLICATE_NAME_MESSAGE}
    assert _count(conn) == before


def test_update_refuses_a_case_variant_of_another_name(
    conn: sqlite3.Connection, groc_id: int
) -> None:
    rent = categories_repo.create(
        conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id
    with pytest.raises(ValidationError) as err:
        categories_svc.update(conn, USER_ID, rent, PatchCategory(name="GROCERIES"))
    assert err.value.fields == {"name": categories_svc.DUPLICATE_NAME_MESSAGE}
    stored = categories_repo.find_by_id(conn, USER_ID, rent)
    assert stored is not None
    assert stored.name == "Rent"


def test_update_allows_a_new_case_of_the_own_name(conn: sqlite3.Connection, groc_id: int) -> None:
    renamed = categories_svc.update(conn, USER_ID, groc_id, PatchCategory(name="GROCERIES"))
    assert renamed.name == "GROCERIES"


def test_another_users_case_variant_does_not_block(conn: sqlite3.Connection, groc_id: int) -> None:
    conn.execute("INSERT INTO users (id, name) VALUES (2, 'other')")
    other = categories_svc.create(
        conn, 2, NewCategory(name="groceries", direction=Direction.EXPENSE)
    )
    assert other.name == "groceries"


def test_another_users_same_name_does_not_block(conn: sqlite3.Connection, groc_id: int) -> None:
    conn.execute("INSERT INTO users (id, name) VALUES (2, 'other')")
    other = categories_svc.create(
        conn, 2, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    )
    assert other.name == "Groceries"
