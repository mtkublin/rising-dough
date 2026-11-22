"""Table-driven tests for the generic user-owned CRUD helpers (T-Q260, ADR-0022 amendment)."""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from typing import Any

import pytest

from budget_planner import clock
from budget_planner.repositories import audit
from budget_planner.repositories._shared import (
    OwnedTable,
    find_owned,
    insert_owned,
    list_owned,
    list_recently_deleted_owned,
    soft_delete_found,
    soft_delete_owned,
    undelete_owned,
    update_owned,
)

USER_ID = 1
OTHER_USER_ID = 2
Row = dict[str, Any]

CATEGORIES: OwnedTable[Row] = OwnedTable(
    table="categories",
    entity_type="category",
    columns="id, user_id, name, direction, is_system, color, created_at, updated_at, deleted_at",
    hydrate=dict,
    order_by="name ASC",
)


@pytest.fixture(autouse=True)
def _other_user(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO users(id, name) VALUES (?, 'other')", (OTHER_USER_ID,))


def _make(conn: sqlite3.Connection, user_id: int, name: str) -> Row:
    return insert_owned(conn, CATEGORIES, user_id, {"name": name, "direction": "expense"})


def _audit_ops(conn: sqlite3.Connection, row_id: int) -> list[str]:
    return [e.operation.value for e in audit.list_entries(conn, USER_ID, "category", row_id)]


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"table": "users"}, "not an allowlisted"),
        ({"table": "categories; DROP TABLE users"}, "not an allowlisted"),
        ({"columns": "id, name FROM users --"}, "invalid column list"),
        ({"columns": ""}, "invalid column list"),
        ({"order_by": "name; DROP TABLE x"}, "invalid order_by"),
        ({"order_by": "name SIDEWAYS"}, "invalid order_by"),
    ],
)
def test_spec_rejects_non_literal_sql_fragments(override: dict[str, str], message: str) -> None:
    fields = {"table": "categories", "entity_type": "category", "columns": "id, name"}
    fields.update(override)
    with pytest.raises(ValueError, match=message):
        OwnedTable(
            table=fields["table"],
            entity_type=fields["entity_type"],
            columns=fields["columns"],
            hydrate=dict,
            order_by=fields.get("order_by", "id ASC"),
        )


@pytest.mark.parametrize("bad", ["name = 1 OR 1", "id; --", "Name", ""])
def test_unsafe_column_names_are_rejected_everywhere(conn: sqlite3.Connection, bad: str) -> None:
    made = _make(conn, USER_ID, "Food")
    with pytest.raises(ValueError, match="invalid column name"):
        find_owned(conn, CATEGORIES, USER_ID, {bad: 1})
    with pytest.raises(ValueError, match="invalid column name"):
        list_owned(conn, CATEGORIES, USER_ID, where={bad: 1})
    with pytest.raises(ValueError, match="invalid column name"):
        insert_owned(conn, CATEGORIES, USER_ID, {bad: 1})
    with pytest.raises(ValueError, match="invalid column name"):
        update_owned(conn, CATEGORIES, USER_ID, made["id"], {bad: 1})


def test_insert_owned_stores_owner_and_audits_create(conn: sqlite3.Connection) -> None:
    made = _make(conn, USER_ID, "Food")

    assert made["user_id"] == USER_ID
    assert made["name"] == "Food"
    entries = audit.list_entries(conn, USER_ID, "category", made["id"])
    assert [e.operation.value for e in entries] == ["create"]
    assert entries[0].prev_json is None
    assert json.loads(entries[0].new_json or "{}")["name"] == "Food"
    assert audit.list_entries(conn, OTHER_USER_ID, "category", made["id"]) == []


@pytest.mark.parametrize(
    ("where_key", "include_deleted", "deleted", "expect_found"),
    [
        ("id", False, False, True),
        ("name", False, False, True),
        ("id", False, True, False),
        ("name", False, True, False),
        ("id", True, True, True),
        ("name", True, True, True),
    ],
)
def test_find_owned_honours_soft_delete_flag(
    conn: sqlite3.Connection,
    where_key: str,
    include_deleted: bool,
    deleted: bool,
    expect_found: bool,
) -> None:
    made = _make(conn, USER_ID, "Food")
    if deleted:
        soft_delete_owned(conn, CATEGORIES, USER_ID, made["id"])

    found = find_owned(
        conn, CATEGORIES, USER_ID, {where_key: made[where_key]}, include_deleted=include_deleted
    )

    assert (found is not None) is expect_found
    if found is not None:
        assert found["id"] == made["id"]


def test_find_owned_never_returns_another_users_row(conn: sqlite3.Connection) -> None:
    theirs = _make(conn, OTHER_USER_ID, "Theirs")

    assert find_owned(conn, CATEGORIES, USER_ID, {"id": theirs["id"]}, include_deleted=True) is None
    assert find_owned(conn, CATEGORIES, USER_ID, {"name": "Theirs"}, include_deleted=True) is None
    assert find_owned(conn, CATEGORIES, OTHER_USER_ID, {"id": theirs["id"]}) is not None


def test_find_owned_combines_all_where_columns(conn: sqlite3.Connection) -> None:
    made = _make(conn, USER_ID, "Food")

    assert find_owned(conn, CATEGORIES, USER_ID, {"name": "Food", "direction": "expense"})
    assert find_owned(conn, CATEGORIES, USER_ID, {"name": "Food", "direction": "income"}) is None
    assert find_owned(conn, CATEGORIES, USER_ID, {"name": "Other", "id": made["id"]}) is None


def test_list_owned_orders_filters_and_scopes(conn: sqlite3.Connection) -> None:
    _make(conn, USER_ID, "b")
    gone = _make(conn, USER_ID, "a")
    _make(conn, USER_ID, "c")
    _make(conn, OTHER_USER_ID, "z")
    insert_owned(conn, CATEGORIES, USER_ID, {"name": "inc", "direction": "income"})
    soft_delete_owned(conn, CATEGORIES, USER_ID, gone["id"])

    def mine(**kwargs: Any) -> list[str]:
        # Seeded categories are capitalised; this test's rows are lowercase.
        rows = list_owned(conn, CATEGORIES, USER_ID, **kwargs)
        return [r["name"] for r in rows if r["name"].islower()]

    assert mine() == ["b", "c", "inc"]
    assert mine(include_deleted=True) == ["a", "b", "c", "inc"]
    assert mine(where={"direction": "expense"}) == ["b", "c"]


def test_update_owned_patches_bumps_updated_at_and_audits(conn: sqlite3.Connection) -> None:
    made = _make(conn, USER_ID, "Food")
    conn.execute(
        "UPDATE categories SET updated_at = '2000-01-01T00:00:00.000Z' WHERE id = ?",
        (made["id"],),
    )

    updated = update_owned(
        conn, CATEGORIES, USER_ID, made["id"], {"name": "Meals", "color": "#ffffff"}
    )

    assert (updated["name"], updated["color"]) == ("Meals", "#ffffff")
    assert updated["updated_at"] > "2000-01-01T00:00:00.000Z"
    entries = audit.list_entries(conn, USER_ID, "category", made["id"])
    assert [e.operation.value for e in entries] == ["create", "update"]
    assert json.loads(entries[1].prev_json or "{}")["name"] == "Food"
    assert json.loads(entries[1].new_json or "{}")["name"] == "Meals"


def test_update_owned_empty_patch_audits_without_changing_row(conn: sqlite3.Connection) -> None:
    made = _make(conn, USER_ID, "Food")

    same = update_owned(conn, CATEGORIES, USER_ID, made["id"], {})

    assert same == find_owned(conn, CATEGORIES, USER_ID, {"id": made["id"]})
    assert _audit_ops(conn, made["id"]) == ["create", "update"]


def test_update_owned_reaches_soft_deleted_rows(conn: sqlite3.Connection) -> None:
    made = _make(conn, USER_ID, "Food")
    soft_delete_owned(conn, CATEGORIES, USER_ID, made["id"])

    updated = update_owned(conn, CATEGORIES, USER_ID, made["id"], {"name": "Old"})

    assert updated["name"] == "Old"
    assert updated["deleted_at"] is not None


def test_update_owned_other_users_row_raises_and_leaves_it_untouched(
    conn: sqlite3.Connection,
) -> None:
    theirs = _make(conn, OTHER_USER_ID, "Theirs")

    with pytest.raises(LookupError, match=f"category {theirs['id']} not found"):
        update_owned(conn, CATEGORIES, USER_ID, theirs["id"], {"name": "Mine now"})

    assert find_owned(conn, CATEGORIES, OTHER_USER_ID, {"id": theirs["id"]}) == theirs
    last = audit.list_entries(conn, OTHER_USER_ID, "category", theirs["id"])[-1]
    assert last.operation.value == "create"


def test_update_owned_checks_foreign_keys_after_row_lookup(conn: sqlite3.Connection) -> None:
    made = _make(conn, USER_ID, "Food")

    with pytest.raises(LookupError, match="account 999 not found"):
        update_owned(conn, CATEGORIES, USER_ID, made["id"], {"name": "X"}, account_ids=(999,))

    still = find_owned(conn, CATEGORIES, USER_ID, {"id": made["id"]})
    assert still is not None
    assert still["name"] == "Food"
    assert _audit_ops(conn, made["id"]) == ["create"]


def test_soft_delete_owned_stamps_row_and_audits_delete(conn: sqlite3.Connection) -> None:
    made = _make(conn, USER_ID, "Food")

    soft_delete_owned(conn, CATEGORIES, USER_ID, made["id"])

    gone = find_owned(conn, CATEGORIES, USER_ID, {"id": made["id"]}, include_deleted=True)
    assert gone is not None
    assert gone["deleted_at"] is not None
    entries = audit.list_entries(conn, USER_ID, "category", made["id"])
    assert [e.operation.value for e in entries] == ["create", "delete"]
    assert json.loads(entries[1].prev_json or "{}")["deleted_at"] is None
    assert entries[1].new_json is None


def test_soft_delete_owned_is_a_silent_noop_for_missing_deleted_and_foreign_rows(
    conn: sqlite3.Connection,
) -> None:
    theirs = _make(conn, OTHER_USER_ID, "Theirs")
    mine = _make(conn, USER_ID, "Mine")
    soft_delete_owned(conn, CATEGORIES, USER_ID, mine["id"])
    before = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]

    soft_delete_owned(conn, CATEGORIES, USER_ID, 99999)
    soft_delete_owned(conn, CATEGORIES, USER_ID, mine["id"])
    soft_delete_owned(conn, CATEGORIES, USER_ID, theirs["id"])

    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == before
    assert find_owned(conn, CATEGORIES, OTHER_USER_ID, {"id": theirs["id"]}) is not None


def test_soft_delete_found_never_touches_other_users_row(conn: sqlite3.Connection) -> None:
    theirs = _make(conn, OTHER_USER_ID, "Theirs")

    soft_delete_found(conn, CATEGORIES, USER_ID, theirs["id"], theirs)

    assert find_owned(conn, CATEGORIES, OTHER_USER_ID, {"id": theirs["id"]}) is not None


def test_undelete_owned_restores_and_audits(conn: sqlite3.Connection) -> None:
    made = _make(conn, USER_ID, "Food")
    soft_delete_owned(conn, CATEGORIES, USER_ID, made["id"])

    restored = undelete_owned(conn, CATEGORIES, USER_ID, made["id"])

    assert restored["deleted_at"] is None
    entries = audit.list_entries(conn, USER_ID, "category", made["id"])
    assert [e.operation.value for e in entries] == ["create", "delete", "undelete"]
    assert json.loads(entries[2].prev_json or "{}")["deleted_at"] is not None
    assert json.loads(entries[2].new_json or "{}")["deleted_at"] is None


def test_undelete_owned_unknown_or_foreign_row_raises(conn: sqlite3.Connection) -> None:
    theirs = _make(conn, OTHER_USER_ID, "Theirs")
    soft_delete_owned(conn, CATEGORIES, OTHER_USER_ID, theirs["id"])

    with pytest.raises(LookupError, match="category 99999 not found"):
        undelete_owned(conn, CATEGORIES, USER_ID, 99999)
    with pytest.raises(LookupError, match=f"category {theirs['id']} not found"):
        undelete_owned(conn, CATEGORIES, USER_ID, theirs["id"])

    assert find_owned(conn, CATEGORIES, OTHER_USER_ID, {"id": theirs["id"]}) is None


def test_list_recently_deleted_owned_window_order_limit_and_scope(
    conn: sqlite3.Connection,
) -> None:
    now = clock.utc_now()
    for name, days in {"recent": 1, "older": 10, "ancient": 200}.items():
        row = _make(conn, USER_ID, name)
        stamp = clock.iso_utc(now - timedelta(days=days))
        conn.execute("UPDATE categories SET deleted_at = ? WHERE id = ?", (stamp, row["id"]))
    _make(conn, USER_ID, "live")
    theirs = _make(conn, OTHER_USER_ID, "theirs")
    conn.execute(
        "UPDATE categories SET deleted_at = ? WHERE id = ?",
        (clock.iso_utc(now - timedelta(days=1)), theirs["id"]),
    )

    def names(**kwargs: int) -> list[str]:
        return [r["name"] for r in list_recently_deleted_owned(conn, CATEGORIES, USER_ID, **kwargs)]

    assert names() == ["recent", "older"]
    assert names(days=5) == ["recent"]
    assert names(days=365) == ["recent", "older", "ancient"]
    assert names(days=365, limit=1) == ["recent"]
