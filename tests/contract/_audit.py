"""Audit-log helpers for contract tests (kept apart from the fixture plugin)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def auth_events(conn: sqlite3.Connection, event: str) -> list[dict[str, Any]]:
    """``auth_event`` audit payloads whose ``event`` equals ``event`` (oldest first)."""
    rows = conn.execute(
        "SELECT new_json FROM audit_log WHERE entity_type = 'auth_event' ORDER BY id"
    ).fetchall()
    payloads = [json.loads(r["new_json"]) for r in rows if r["new_json"]]
    return [p for p in payloads if p.get("event") == event]


def audit_count(conn: sqlite3.Connection, entity_type: str, operation: str | None = None) -> int:
    sql = "SELECT COUNT(*) FROM audit_log WHERE entity_type = ?"
    args: tuple[Any, ...] = (entity_type,)
    if operation:
        sql += " AND operation = ?"
        args = (entity_type, operation)
    return int(conn.execute(sql, args).fetchone()[0])
