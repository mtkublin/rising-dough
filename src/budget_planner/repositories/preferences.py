"""User preferences repository (ADR-0025).

Preferences skip the ``audit_log`` by design — they are UI state, not domain
mutations. The functions still wrap each write in :func:`_shared.transaction`
to keep the "repository owns the transaction" invariant from ADR-0022.
"""

from __future__ import annotations

import sqlite3

from budget_planner.domain.preferences import UserPreference
from budget_planner.repositories._shared import parse_dt_required, transaction

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
    with transaction(conn):
        conn.execute(
            "INSERT INTO user_preferences(user_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET "
            "value = excluded.value, "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
            (user_id, key, value),
        )
        row = conn.execute(
            f"SELECT {_COLS} FROM user_preferences WHERE user_id = ? AND key = ?",
            (user_id, key),
        ).fetchone()
    return _row_to_preference(row)


def delete(conn: sqlite3.Connection, user_id: int, key: str) -> None:
    with transaction(conn):
        conn.execute(
            "DELETE FROM user_preferences WHERE user_id = ? AND key = ?",
            (user_id, key),
        )


__all__ = ["delete", "get", "upsert"]
