from __future__ import annotations

import sqlite3

import pytest

from budget_planner.domain.preferences import PREF_INCOME_ANCHOR_CATEGORY_ID
from budget_planner.repositories import preferences


def _audit_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT count(*) FROM audit_log").fetchone()[0])


def test_get_returns_none_when_absent(conn: sqlite3.Connection) -> None:
    assert preferences.get(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID) is None


def test_upsert_insert_round_trip(conn: sqlite3.Connection) -> None:
    row = preferences.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, "42")
    assert row.user_id == 1
    assert row.key == PREF_INCOME_ANCHOR_CATEGORY_ID
    assert row.value == "42"
    assert preferences.get(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID) == row


def test_upsert_update_preserves_created_at_and_bumps_updated_at(
    conn: sqlite3.Connection,
) -> None:
    first = preferences.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, "42")
    # strftime('%Y-%m-%dT%H:%M:%fZ') has millisecond precision; force a tick.
    conn.execute("SELECT 1")
    second = preferences.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, "99")
    assert second.id == first.id
    assert second.value == "99"
    assert second.created_at == first.created_at
    assert second.updated_at >= first.updated_at


def test_delete_is_idempotent(conn: sqlite3.Connection) -> None:
    preferences.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, "42")
    preferences.delete(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID)
    assert preferences.get(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID) is None
    # Deleting again does not raise.
    preferences.delete(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID)
    preferences.delete(conn, 1, "nonexistent-key")


def test_unique_user_id_key_enforced(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO user_preferences(user_id, key, value) VALUES (1, 'k', 'a')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO user_preferences(user_id, key, value) VALUES (1, 'k', 'b')")


def test_writes_are_audited_as_user_preference(conn: sqlite3.Connection) -> None:
    before = _audit_count(conn)
    preferences.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, "42")
    preferences.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, "99")
    preferences.delete(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID)
    preferences.delete(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID)  # idempotent: no row, no audit
    rows = conn.execute(
        "SELECT operation, user_id, prev_json, new_json FROM audit_log "
        "WHERE entity_type = 'user_preference' ORDER BY id"
    ).fetchall()
    assert _audit_count(conn) == before + 3
    assert [r["operation"] for r in rows] == ["create", "update", "delete"]
    assert {r["user_id"] for r in rows} == {1}
    assert rows[0]["prev_json"] is None and '"42"' in rows[0]["new_json"]
    assert '"42"' in rows[1]["prev_json"] and '"99"' in rows[1]["new_json"]
    assert '"99"' in rows[2]["prev_json"] and rows[2]["new_json"] is None
