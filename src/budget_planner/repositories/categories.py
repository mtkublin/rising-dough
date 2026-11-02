"""Category repository — pure CRUD functions over the `categories` table."""

from __future__ import annotations

import sqlite3

from budget_planner.domain.categories import Category, NewCategory, PatchCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories._shared import mutate, parse_dt, parse_dt_required

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


def find_by_id(
    conn: sqlite3.Connection,
    category_id: int,
    *,
    include_deleted: bool = False,
) -> Category | None:
    sql = f"SELECT {_COLUMNS} FROM categories WHERE id = ?"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    row = conn.execute(sql, (category_id,)).fetchone()
    return _row_to_category(row) if row is not None else None


def list_recently_deleted(
    conn: sqlite3.Connection, *, days: int = 90, limit: int = 500
) -> list[Category]:
    """T-R70 — soft-deleted (archived) categories within the last `days` days."""
    sql = (
        f"SELECT {_COLUMNS} FROM categories "
        "WHERE deleted_at IS NOT NULL "
        "AND deleted_at > datetime('now', ?) "
        "ORDER BY deleted_at DESC "
        "LIMIT ?"
    )
    rows = conn.execute(sql, (f"-{days} days", limit)).fetchall()
    return [_row_to_category(r) for r in rows]


def find_by_name(
    conn: sqlite3.Connection,
    name: str,
    *,
    include_deleted: bool = False,
) -> Category | None:
    sql = f"SELECT {_COLUMNS} FROM categories WHERE name = ?"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    row = conn.execute(sql, (name,)).fetchone()
    return _row_to_category(row) if row is not None else None


def list_all(
    conn: sqlite3.Connection,
    *,
    include_deleted: bool = False,
) -> list[Category]:
    sql = f"SELECT {_COLUMNS} FROM categories"
    if not include_deleted:
        sql += " WHERE deleted_at IS NULL"
    sql += " ORDER BY name ASC"
    return [_row_to_category(r) for r in conn.execute(sql).fetchall()]


def create(conn: sqlite3.Connection, data: NewCategory) -> Category:
    def _action(c: sqlite3.Connection) -> tuple[int, Category]:
        cursor = c.execute(
            "INSERT INTO categories(user_id, name, direction, is_system, color) "
            "VALUES (?, ?, ?, ?, ?)",
            (data.user_id, data.name, data.direction.value, int(data.is_system), data.color),
        )
        new_id = int(cursor.lastrowid or 0)
        created = find_by_id(c, new_id)
        assert created is not None
        return new_id, created

    return mutate(conn, entity_type="category", operation="create", prev=None, action=_action)


def update(
    conn: sqlite3.Connection,
    category_id: int,
    data: PatchCategory,
) -> Category:
    prev = find_by_id(conn, category_id, include_deleted=True)
    if prev is None:
        raise LookupError(f"category {category_id} not found")
    changes = data.as_dict()

    def _action(c: sqlite3.Connection) -> tuple[int, Category]:
        if changes:
            sets = [f"{field} = ?" for field in changes]
            sets.append("updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))")
            c.execute(
                f"UPDATE categories SET {', '.join(sets)} WHERE id = ?",
                (*changes.values(), category_id),
            )
        updated = find_by_id(c, category_id, include_deleted=True)
        assert updated is not None
        return category_id, updated

    return mutate(conn, entity_type="category", operation="update", prev=prev, action=_action)


def soft_delete(conn: sqlite3.Connection, category_id: int) -> None:
    prev = find_by_id(conn, category_id)
    if prev is None:
        return

    def _action(c: sqlite3.Connection) -> tuple[int, None]:
        c.execute(
            "UPDATE categories SET deleted_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')), "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ? AND deleted_at IS NULL",
            (category_id,),
        )
        return category_id, None

    mutate(conn, entity_type="category", operation="delete", prev=prev, action=_action)


def undelete(conn: sqlite3.Connection, category_id: int) -> Category:
    prev = find_by_id(conn, category_id, include_deleted=True)
    if prev is None:
        raise LookupError(f"category {category_id} not found")

    def _action(c: sqlite3.Connection) -> tuple[int, Category]:
        c.execute(
            "UPDATE categories SET deleted_at = NULL, "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ?",
            (category_id,),
        )
        restored = find_by_id(c, category_id)
        assert restored is not None
        return category_id, restored

    return mutate(conn, entity_type="category", operation="undelete", prev=prev, action=_action)


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
