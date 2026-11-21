"""Audit log reader — the writer lives in `_shared.write_audit`."""

from __future__ import annotations

import sqlite3

from budget_planner.domain.audit import AuditEntry
from budget_planner.domain.enums import AuditOperation
from budget_planner.repositories._shared import parse_dt_required

_COLUMNS = (
    "id, entity_type, entity_id, changed_at, operation, prev_json, new_json, user_id, actor_user_id"
)


def _row_to_entry(row: sqlite3.Row) -> AuditEntry:
    return AuditEntry(
        id=row["id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        changed_at=parse_dt_required(row["changed_at"]),
        operation=AuditOperation(row["operation"]),
        prev_json=row["prev_json"],
        new_json=row["new_json"],
        user_id=row["user_id"],
        actor_user_id=row["actor_user_id"],
    )


def list_entries(
    conn: sqlite3.Connection,
    user_id: int | None,
    entity_type: str,
    entity_id: int,
) -> list[AuditEntry]:
    """Audit rows of one entity owned by ``user_id`` (``None``: ownerless system rows)."""
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM audit_log "
        "WHERE user_id IS ? AND entity_type = ? AND entity_id = ? "
        "ORDER BY changed_at ASC, id ASC",
        (user_id, entity_type, entity_id),
    ).fetchall()
    return [_row_to_entry(r) for r in rows]


def recent(conn: sqlite3.Connection, limit: int = 100, *, user_id: int | None) -> list[AuditEntry]:
    """Newest audit rows; ``user_id`` scopes to one owner, ``None`` is the explicit cross-user tail.

    The cross-user form exists only for the debug audit tail, whose service masks other users'
    payloads (ADR-0019 amendment 2026-11-21, T-Q268).
    """
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM audit_log WHERE (? IS NULL OR user_id = ?) "
        "ORDER BY id DESC LIMIT ?",
        (user_id, user_id, limit),
    ).fetchall()
    return [_row_to_entry(r) for r in rows]


def find_entry(conn: sqlite3.Connection, user_id: int, audit_id: int) -> AuditEntry | None:
    """One audit row by id, only if it belongs to ``user_id`` (T-Q228)."""
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM audit_log WHERE id = ? AND user_id = ?",
        (audit_id, user_id),
    ).fetchone()
    return _row_to_entry(row) if row is not None else None


def latest_entry_id(
    conn: sqlite3.Connection, user_id: int, entity_type: str, entity_id: int
) -> int | None:
    """Id of the newest audit row of one entity written for ``user_id`` (T-Q228)."""
    row = conn.execute(
        "SELECT MAX(id) AS id FROM audit_log "
        "WHERE user_id IS ? AND entity_type = ? AND entity_id = ?",
        (user_id, entity_type, entity_id),
    ).fetchone()
    return None if row is None or row["id"] is None else int(row["id"])


__all__ = ["find_entry", "latest_entry_id", "list_entries", "recent"]
