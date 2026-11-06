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
    entity_type: str,
    entity_id: int,
) -> list[AuditEntry]:
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM audit_log "
        "WHERE entity_type = ? AND entity_id = ? "
        "ORDER BY changed_at ASC, id ASC",
        (entity_type, entity_id),
    ).fetchall()
    return [_row_to_entry(r) for r in rows]


def recent(conn: sqlite3.Connection, limit: int = 100) -> list[AuditEntry]:
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM audit_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_entry(r) for r in rows]


__all__ = ["list_entries", "recent"]
