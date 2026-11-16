"""Unit tests for the owner-scoped audit tail (T-D54, ADR-0078 section 1)."""

from __future__ import annotations

import json
import sqlite3

from budget_planner.services.audit_tail import OTHER_USER, REDACTED, audit_tail

VIEWER = 1
OTHER = 2


def _row(
    conn: sqlite3.Connection,
    *,
    user_id: int | None,
    actor_user_id: int | None = None,
    new: object = None,
    prev: object = None,
) -> None:
    conn.execute(
        "INSERT INTO audit_log (entity_type, entity_id, changed_at, operation, prev_json, "
        "new_json, user_id, actor_user_id) VALUES ('thing', 1, '2026-11-03T10:00:00Z', "
        "'update', ?, ?, ?, ?)",
        (
            None if prev is None else json.dumps(prev),
            None if new is None else json.dumps(new),
            user_id,
            actor_user_id,
        ),
    )
    conn.commit()


def _ensure_users(conn: sqlite3.Connection) -> None:
    for uid in (VIEWER, OTHER):
        conn.execute("INSERT OR IGNORE INTO users (id, name) VALUES (?, ?)", (uid, f"u{uid}"))
    conn.commit()


def test_own_row_shows_payloads(conn: sqlite3.Connection) -> None:
    _ensure_users(conn)
    _row(conn, user_id=VIEWER, new={"a": 1}, prev={"a": 0})
    entry = audit_tail(conn, VIEWER, 1)[0]
    assert entry["new"] == {"a": 1}
    assert entry["prev"] == {"a": 0}
    assert entry["user_id"] == VIEWER


def test_other_users_row_is_masked(conn: sqlite3.Connection) -> None:
    _ensure_users(conn)
    _row(conn, user_id=OTHER, new={"amount": 5}, prev={"amount": 4})
    entry = audit_tail(conn, VIEWER, 1)[0]
    assert entry["new"] == OTHER_USER
    assert entry["prev"] == OTHER_USER
    assert entry["user_id"] == OTHER
    assert entry["entity_type"] == "thing"


def test_null_user_row_owned_by_actor(conn: sqlite3.Connection) -> None:
    _ensure_users(conn)
    _row(conn, user_id=None, actor_user_id=VIEWER, new={"x": 1})
    _row(conn, user_id=None, actor_user_id=OTHER, new={"x": 2})
    _row(conn, user_id=None, actor_user_id=None, new={"x": 3})
    rows = audit_tail(conn, VIEWER, 3)
    assert [r["new"] for r in rows] == [OTHER_USER, OTHER_USER, {"x": 1}]


def test_secret_scrubbing_unchanged_for_own_rows(conn: sqlite3.Connection) -> None:
    _ensure_users(conn)
    _row(conn, user_id=VIEWER, new={"password_hash": "h", "ok": 1})
    entry = audit_tail(conn, VIEWER, 1)[0]
    assert entry["new"] == {"password_hash": REDACTED, "ok": 1}
