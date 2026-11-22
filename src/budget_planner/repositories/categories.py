"""Category repository — pure CRUD functions over the `categories` table.

## User-scoping discipline (T-D16 / ADR-0061 §5)

Every function takes ``user_id`` as the first positional arg after ``conn``;
every SELECT / UPDATE / DELETE carries ``user_id = :user_id``; the
``tests/architecture/test_user_id_filter.py`` static test backstops the rule.
"""

from __future__ import annotations

import sqlite3

from budget_planner.domain.categories import Category, NewCategory, PatchCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories._shared import (
    OwnedTable,
    find_owned,
    insert_owned,
    list_owned,
    list_recently_deleted_owned,
    parse_dt,
    parse_dt_required,
    soft_delete_owned,
    undelete_owned,
    update_owned,
)

_COLUMNS = "id, user_id, name, direction, is_system, color, created_at, updated_at, deleted_at"


def _row_to_category(row: sqlite3.Row) -> Category:
    return Category(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        direction=Direction(row["direction"]),
        is_system=bool(row["is_system"]),
        color=row["color"],
        created_at=parse_dt_required(row["created_at"]),
        updated_at=parse_dt_required(row["updated_at"]),
        deleted_at=parse_dt(row["deleted_at"]),
    )


_CATEGORIES: OwnedTable[Category] = OwnedTable(
    table="categories",
    entity_type="category",
    columns=_COLUMNS,
    hydrate=_row_to_category,
    order_by="name ASC",
)


def find_by_id(
    conn: sqlite3.Connection,
    user_id: int,
    category_id: int,
    *,
    include_deleted: bool = False,
) -> Category | None:
    return find_owned(
        conn, _CATEGORIES, user_id, {"id": category_id}, include_deleted=include_deleted
    )


def list_recently_deleted(
    conn: sqlite3.Connection, user_id: int, *, days: int = 90, limit: int = 500
) -> list[Category]:
    """T-R70 — soft-deleted (archived) categories within the last `days` days."""
    return list_recently_deleted_owned(conn, _CATEGORIES, user_id, days=days, limit=limit)


def find_by_name(
    conn: sqlite3.Connection,
    user_id: int,
    name: str,
    *,
    include_deleted: bool = False,
) -> Category | None:
    return find_owned(conn, _CATEGORIES, user_id, {"name": name}, include_deleted=include_deleted)


def list_all(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    include_deleted: bool = False,
) -> list[Category]:
    return list_owned(conn, _CATEGORIES, user_id, include_deleted=include_deleted)


def create(conn: sqlite3.Connection, user_id: int, data: NewCategory) -> Category:
    return insert_owned(
        conn,
        _CATEGORIES,
        user_id,
        {
            "name": data.name,
            "direction": data.direction.value,
            "is_system": int(data.is_system),
            "color": data.color,
        },
    )


def update(
    conn: sqlite3.Connection,
    user_id: int,
    category_id: int,
    data: PatchCategory,
) -> Category:
    return update_owned(conn, _CATEGORIES, user_id, category_id, data.as_dict())


def soft_delete(conn: sqlite3.Connection, user_id: int, category_id: int) -> None:
    soft_delete_owned(conn, _CATEGORIES, user_id, category_id)


def undelete(conn: sqlite3.Connection, user_id: int, category_id: int) -> Category:
    return undelete_owned(conn, _CATEGORIES, user_id, category_id)


__all__ = [
    "create",
    "find_by_id",
    "find_by_name",
    "list_all",
    "list_recently_deleted",
    "soft_delete",
    "undelete",
    "update",
]
