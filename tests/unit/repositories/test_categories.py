from __future__ import annotations

import sqlite3

import pytest

from budget_planner.domain.categories import NewCategory, PatchCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import audit, categories

USER_ID = 1


def test_create_and_list(conn: sqlite3.Connection) -> None:
    created = categories.create(
        conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
    )
    assert categories.find_by_id(conn, USER_ID, created.id) == created
    assert categories.find_by_name(conn, USER_ID, "Food") == created
    names = {c.name for c in categories.list_all(conn, USER_ID)}
    assert "Food" in names
    assert "Transit" in names  # Seeded system category.


def test_seeded_system_categories_present(conn: sqlite3.Connection) -> None:
    transit = categories.find_by_name(conn, USER_ID, "Transit")
    assert transit is not None
    assert transit.is_system is True
    assert transit.direction is Direction.TRANSIT


def test_update_rename(conn: sqlite3.Connection) -> None:
    created = categories.create(
        conn, USER_ID, NewCategory(name="Shopping", direction=Direction.EXPENSE)
    )
    renamed = categories.update(conn, USER_ID, created.id, PatchCategory(name="Shops"))
    assert renamed.name == "Shops"
    assert audit.list_entries(conn, "category", created.id)[-1].operation.value == ("update")


def test_update_missing_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(LookupError):
        categories.update(conn, USER_ID, 999, PatchCategory(name="x"))


def test_soft_delete_and_undelete(conn: sqlite3.Connection) -> None:
    created = categories.create(
        conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    )
    categories.soft_delete(conn, USER_ID, created.id)
    assert categories.find_by_id(conn, USER_ID, created.id) is None

    restored = categories.undelete(conn, USER_ID, created.id)
    assert restored.deleted_at is None
    ops = [e.operation.value for e in audit.list_entries(conn, "category", created.id)]
    assert ops == ["create", "delete", "undelete"]


def test_soft_delete_missing_is_noop(conn: sqlite3.Connection) -> None:
    categories.soft_delete(conn, USER_ID, 999)
    assert audit.list_entries(conn, "category", 999) == []


def test_undelete_missing_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(LookupError):
        categories.undelete(conn, USER_ID, 999)


def test_update_noop_patch(conn: sqlite3.Connection) -> None:
    created = categories.create(
        conn, USER_ID, NewCategory(name="Fuel", direction=Direction.EXPENSE)
    )
    # Patch with no changes still audits as 'update'.
    categories.update(conn, USER_ID, created.id, PatchCategory())
    ops = [e.operation.value for e in audit.list_entries(conn, "category", created.id)]
    assert ops == ["create", "update"]


# -- ADR-0048 color override --------------------------------------------


def test_create_with_color(conn: sqlite3.Connection) -> None:
    created = categories.create(
        conn,
        USER_ID,
        NewCategory(name="Travel", direction=Direction.EXPENSE, color="#a3c2ff"),
    )
    reloaded = categories.find_by_id(conn, USER_ID, created.id)
    assert reloaded is not None
    assert reloaded.color == "#a3c2ff"


def test_create_without_color_defaults_null(conn: sqlite3.Connection) -> None:
    created = categories.create(
        conn, USER_ID, NewCategory(name="Health", direction=Direction.EXPENSE)
    )
    reloaded = categories.find_by_id(conn, USER_ID, created.id)
    assert reloaded is not None
    assert reloaded.color is None


def test_update_set_color(conn: sqlite3.Connection) -> None:
    created = categories.create(
        conn, USER_ID, NewCategory(name="Books", direction=Direction.EXPENSE)
    )
    updated = categories.update(conn, USER_ID, created.id, PatchCategory(color="#112233"))
    assert updated.color == "#112233"


def test_update_clear_color(conn: sqlite3.Connection) -> None:
    created = categories.create(
        conn,
        USER_ID,
        NewCategory(name="Gifts", direction=Direction.EXPENSE, color="#aabbcc"),
    )
    cleared = categories.update(conn, USER_ID, created.id, PatchCategory(clear_color=True))
    assert cleared.color is None


def test_update_color_preserves_name(conn: sqlite3.Connection) -> None:
    created = categories.create(
        conn, USER_ID, NewCategory(name="Pets", direction=Direction.EXPENSE)
    )
    updated = categories.update(conn, USER_ID, created.id, PatchCategory(color="#abcdef"))
    assert updated.name == "Pets"
    assert updated.color == "#abcdef"


def test_create_rejects_invalid_hex(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        categories.create(
            conn,
            USER_ID,
            NewCategory(name="Bad", direction=Direction.EXPENSE, color="not-a-color"),
        )
