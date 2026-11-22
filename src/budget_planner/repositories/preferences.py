"""User preferences repository (ADR-0025).

Preference writes are audited as ``user_preference`` through
:func:`_shared.mutate` (ADR-0019 amendment 2026-11-21, T-Q228, Q-049).

## User-scoping discipline (T-D16 / ADR-0061 §5)

Every function takes ``user_id`` as the first positional arg after ``conn``;
every SELECT / UPDATE / DELETE carries ``user_id = :user_id``. The
``tests/architecture/test_user_id_filter.py`` static test backstops the rule.
"""

from __future__ import annotations

import sqlite3

from budget_planner.domain.preferences import UserPreference
from budget_planner.repositories._shared import mutate, parse_dt_required

_COLS = "id, user_id, key, value, created_at, updated_at"


def _row_to_preference(row: sqlite3.Row) -> UserPreference:
    return UserPreference(
        id=row["id"],
        user_id=row["user_id"],
        key=row["key"],
        value=row["value"],
        created_at=parse_dt_required(row["created_at"]),
        updated_at=parse_dt_required(row["updated_at"]),
    )


def get(conn: sqlite3.Connection, user_id: int, key: str) -> UserPreference | None:
    row = conn.execute(
        f"SELECT {_COLS} FROM user_preferences WHERE user_id = ? AND key = ?",
        (user_id, key),
    ).fetchone()
    return _row_to_preference(row) if row is not None else None


def upsert(conn: sqlite3.Connection, user_id: int, key: str, value: str) -> UserPreference:
    prev = get(conn, user_id, key)

    def _upsert_action(c: sqlite3.Connection) -> tuple[int, UserPreference]:
        c.execute(
            "INSERT INTO user_preferences(user_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET "
            "value = excluded.value, "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
            (user_id, key, value),
        )
        row = c.execute(
            f"SELECT {_COLS} FROM user_preferences WHERE user_id = ? AND key = ?",
            (user_id, key),
        ).fetchone()
        pref = _row_to_preference(row)
        return pref.id, pref

    return mutate(
        conn,
        entity_type="user_preference",
        operation="create" if prev is None else "update",
        prev=prev,
        action=_upsert_action,
        user_id=user_id,
    )


def delete(conn: sqlite3.Connection, user_id: int, key: str) -> None:
    prev = get(conn, user_id, key)
    if prev is None:
        return

    def _delete_action(c: sqlite3.Connection) -> tuple[int, None]:
        c.execute(
            "DELETE FROM user_preferences WHERE user_id = ? AND key = ?",
            (user_id, key),
        )
        return prev.id, None

    mutate(
        conn,
        entity_type="user_preference",
        operation="delete",
        prev=prev,
        action=_delete_action,
        user_id=user_id,
    )


__all__ = ["delete", "get", "upsert"]
