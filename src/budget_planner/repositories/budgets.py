"""Budget tier repositories (defaults + recurring + one-off; ADR-0014)."""

from __future__ import annotations

import sqlite3

from budget_planner.domain.budgets import (
    BudgetDefault,
    BudgetOneOffOverride,
    BudgetRecurringOverride,
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.repositories._shared import mutate, parse_dt, parse_dt_required

_DEFAULT_COLS = "id, user_id, category_id, amount, created_at, updated_at, deleted_at"
_RECURRING_COLS = "id, user_id, category_id, month, amount, created_at, updated_at, deleted_at"
_ONE_OFF_COLS = "id, user_id, category_id, year, month, amount, created_at, updated_at, deleted_at"


def _row_to_default(row: sqlite3.Row) -> BudgetDefault:
    return BudgetDefault(
        id=row["id"],
        user_id=row["user_id"],
        category_id=row["category_id"],
        amount=row["amount"],
        created_at=parse_dt_required(row["created_at"]),
        updated_at=parse_dt_required(row["updated_at"]),
        deleted_at=parse_dt(row["deleted_at"]),
    )


def _row_to_recurring(row: sqlite3.Row) -> BudgetRecurringOverride:
    return BudgetRecurringOverride(
        id=row["id"],
        user_id=row["user_id"],
        category_id=row["category_id"],
        month=row["month"],
        amount=row["amount"],
        created_at=parse_dt_required(row["created_at"]),
        updated_at=parse_dt_required(row["updated_at"]),
        deleted_at=parse_dt(row["deleted_at"]),
    )


def _row_to_one_off(row: sqlite3.Row) -> BudgetOneOffOverride:
    return BudgetOneOffOverride(
        id=row["id"],
        user_id=row["user_id"],
        category_id=row["category_id"],
        year=row["year"],
        month=row["month"],
        amount=row["amount"],
        created_at=parse_dt_required(row["created_at"]),
        updated_at=parse_dt_required(row["updated_at"]),
        deleted_at=parse_dt(row["deleted_at"]),
    )


# ---------------------------------------------------------------------------
# defaults
# ---------------------------------------------------------------------------
def get_default(
    conn: sqlite3.Connection,
    category_id: int,
    *,
    include_deleted: bool = False,
) -> BudgetDefault | None:
    sql = f"SELECT {_DEFAULT_COLS} FROM budget_defaults WHERE category_id = ?"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    row = conn.execute(sql, (category_id,)).fetchone()
    return _row_to_default(row) if row is not None else None


def list_defaults(
    conn: sqlite3.Connection, *, include_deleted: bool = False
) -> list[BudgetDefault]:
    sql = f"SELECT {_DEFAULT_COLS} FROM budget_defaults"
    if not include_deleted:
        sql += " WHERE deleted_at IS NULL"
    sql += " ORDER BY category_id ASC"
    return [_row_to_default(r) for r in conn.execute(sql).fetchall()]


def set_default(conn: sqlite3.Connection, data: NewBudgetDefault) -> BudgetDefault:
    existing = get_default(conn, data.category_id)
    prev = existing

    def _action(c: sqlite3.Connection) -> tuple[int, BudgetDefault]:
        if existing is None:
            cursor = c.execute(
                "INSERT INTO budget_defaults(user_id, category_id, amount) VALUES (?, ?, ?)",
                (data.user_id, data.category_id, data.amount),
            )
            new_id = int(cursor.lastrowid or 0)
        else:
            c.execute(
                "UPDATE budget_defaults SET amount = ?, "
                "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
                "WHERE id = ?",
                (data.amount, existing.id),
            )
            new_id = existing.id
        row = c.execute(
            f"SELECT {_DEFAULT_COLS} FROM budget_defaults WHERE id = ?", (new_id,)
        ).fetchone()
        return new_id, _row_to_default(row)

    return mutate(
        conn,
        entity_type="budget_default",
        operation="update" if prev is not None else "create",
        prev=prev,
        action=_action,
    )


def clear_default(conn: sqlite3.Connection, category_id: int) -> None:
    prev = get_default(conn, category_id)
    if prev is None:
        return

    def _action(c: sqlite3.Connection) -> tuple[int, None]:
        c.execute(
            "UPDATE budget_defaults "
            "SET deleted_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')), "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ?",
            (prev.id,),
        )
        return prev.id, None

    mutate(
        conn,
        entity_type="budget_default",
        operation="delete",
        prev=prev,
        action=_action,
    )


# ---------------------------------------------------------------------------
# recurring overrides
# ---------------------------------------------------------------------------
def get_recurring(
    conn: sqlite3.Connection,
    category_id: int,
    month: int,
    *,
    include_deleted: bool = False,
) -> BudgetRecurringOverride | None:
    sql = (
        f"SELECT {_RECURRING_COLS} FROM budget_recurring_overrides "
        "WHERE category_id = ? AND month = ?"
    )
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    row = conn.execute(sql, (category_id, month)).fetchone()
    return _row_to_recurring(row) if row is not None else None


def list_recurring(
    conn: sqlite3.Connection, *, include_deleted: bool = False
) -> list[BudgetRecurringOverride]:
    sql = f"SELECT {_RECURRING_COLS} FROM budget_recurring_overrides"
    if not include_deleted:
        sql += " WHERE deleted_at IS NULL"
    sql += " ORDER BY category_id ASC, month ASC"
    return [_row_to_recurring(r) for r in conn.execute(sql).fetchall()]


def set_recurring(
    conn: sqlite3.Connection, data: NewBudgetRecurringOverride
) -> BudgetRecurringOverride:
    existing = get_recurring(conn, data.category_id, data.month)
    prev = existing

    def _action(c: sqlite3.Connection) -> tuple[int, BudgetRecurringOverride]:
        if existing is None:
            cursor = c.execute(
                "INSERT INTO budget_recurring_overrides("
                "user_id, category_id, month, amount) VALUES (?, ?, ?, ?)",
                (data.user_id, data.category_id, data.month, data.amount),
            )
            new_id = int(cursor.lastrowid or 0)
        else:
            c.execute(
                "UPDATE budget_recurring_overrides SET amount = ?, "
                "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
                "WHERE id = ?",
                (data.amount, existing.id),
            )
            new_id = existing.id
        row = c.execute(
            f"SELECT {_RECURRING_COLS} FROM budget_recurring_overrides WHERE id = ?",
            (new_id,),
        ).fetchone()
        return new_id, _row_to_recurring(row)

    return mutate(
        conn,
        entity_type="budget_recurring_override",
        operation="update" if prev is not None else "create",
        prev=prev,
        action=_action,
    )


def clear_recurring(conn: sqlite3.Connection, category_id: int, month: int) -> None:
    prev = get_recurring(conn, category_id, month)
    if prev is None:
        return

    def _action(c: sqlite3.Connection) -> tuple[int, None]:
        c.execute(
            "UPDATE budget_recurring_overrides "
            "SET deleted_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')), "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ?",
            (prev.id,),
        )
        return prev.id, None

    mutate(
        conn,
        entity_type="budget_recurring_override",
        operation="delete",
        prev=prev,
        action=_action,
    )


# ---------------------------------------------------------------------------
# one-off overrides
# ---------------------------------------------------------------------------
def get_one_off(
    conn: sqlite3.Connection,
    category_id: int,
    year: int,
    month: int,
    *,
    include_deleted: bool = False,
) -> BudgetOneOffOverride | None:
    sql = (
        f"SELECT {_ONE_OFF_COLS} FROM budget_one_off_overrides "
        "WHERE category_id = ? AND year = ? AND month = ?"
    )
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    row = conn.execute(sql, (category_id, year, month)).fetchone()
    return _row_to_one_off(row) if row is not None else None


def list_one_off(
    conn: sqlite3.Connection,
    *,
    year: int | None = None,
    include_deleted: bool = False,
) -> list[BudgetOneOffOverride]:
    sql = f"SELECT {_ONE_OFF_COLS} FROM budget_one_off_overrides"
    clauses: list[str] = []
    params: list[object] = []
    if year is not None:
        clauses.append("year = ?")
        params.append(year)
    if not include_deleted:
        clauses.append("deleted_at IS NULL")
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY year ASC, month ASC, category_id ASC"
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_one_off(r) for r in rows]


def set_one_off(conn: sqlite3.Connection, data: NewBudgetOneOffOverride) -> BudgetOneOffOverride:
    existing = get_one_off(conn, data.category_id, data.year, data.month)
    prev = existing

    def _action(c: sqlite3.Connection) -> tuple[int, BudgetOneOffOverride]:
        if existing is None:
            cursor = c.execute(
                "INSERT INTO budget_one_off_overrides("
                "user_id, category_id, year, month, amount) VALUES (?, ?, ?, ?, ?)",
                (data.user_id, data.category_id, data.year, data.month, data.amount),
            )
            new_id = int(cursor.lastrowid or 0)
        else:
            c.execute(
                "UPDATE budget_one_off_overrides SET amount = ?, "
                "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
                "WHERE id = ?",
                (data.amount, existing.id),
            )
            new_id = existing.id
        row = c.execute(
            f"SELECT {_ONE_OFF_COLS} FROM budget_one_off_overrides WHERE id = ?",
            (new_id,),
        ).fetchone()
        return new_id, _row_to_one_off(row)

    return mutate(
        conn,
        entity_type="budget_one_off_override",
        operation="update" if prev is not None else "create",
        prev=prev,
        action=_action,
    )


def clear_one_off(
    conn: sqlite3.Connection,
    category_id: int,
    year: int,
    month: int,
) -> None:
    prev = get_one_off(conn, category_id, year, month)
    if prev is None:
        return

    def _action(c: sqlite3.Connection) -> tuple[int, None]:
        c.execute(
            "UPDATE budget_one_off_overrides "
            "SET deleted_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')), "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ?",
            (prev.id,),
        )
        return prev.id, None

    mutate(
        conn,
        entity_type="budget_one_off_override",
        operation="delete",
        prev=prev,
        action=_action,
    )


__all__ = [
    "clear_default",
    "clear_one_off",
    "clear_recurring",
    "get_default",
    "get_one_off",
    "get_recurring",
    "list_defaults",
    "list_one_off",
    "list_recurring",
    "set_default",
    "set_one_off",
    "set_recurring",
]
