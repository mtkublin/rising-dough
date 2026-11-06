"""Integration tests for ``GET /debug/audit-tail`` (T-D43)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.services.audit_tail import MAX_TAIL, OTHER_USER, REDACTED


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def _insert(
    db: sqlite3.Connection,
    n: int,
    new_json: str = '{"a": 1}',
    user_id: int | None = 1,
    entity_type: str = "thing",
) -> None:
    for i in range(n):
        db.execute(
            "INSERT INTO audit_log (entity_type, entity_id, changed_at, operation, new_json, "
            "user_id) VALUES (?, ?, '2026-11-03T10:00:00Z', 'create', ?, ?)",
            (entity_type, i, new_json, user_id),
        )
    db.commit()


def test_admin_gets_json_shape(admin_client: TestClient, db: sqlite3.Connection) -> None:
    _insert(db, 3)
    resp = admin_client.get("/debug/audit-tail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == len(body["entries"]) >= 3
    assert set(body["entries"][0]) == {
        "id",
        "entity_type",
        "entity_id",
        "changed_at",
        "operation",
        "prev",
        "new",
        "user_id",
    }
    ids = [e["id"] for e in body["entries"]]
    assert ids == sorted(ids, reverse=True)
    assert resp.headers["cache-control"] == "no-store"


def test_secret_keys_are_redacted(admin_client: TestClient, db: sqlite3.Connection) -> None:
    payload = {
        "email": "x@y.z",
        "password_hash": "$2b$topsecret",  # pragma: allowlist secret
        "n": [{"token": "t"}],
    }
    _insert(db, 1, json.dumps(payload))
    entry = admin_client.get("/debug/audit-tail?n=1").json()["entries"][0]
    assert entry["new"]["email"] == "x@y.z"
    assert entry["new"]["password_hash"] == REDACTED
    assert entry["new"]["n"][0]["token"] == REDACTED
    assert "topsecret" not in json.dumps(entry)


def test_invalid_json_payload_is_redacted(admin_client: TestClient, db: sqlite3.Connection) -> None:
    _insert(db, 1, "not json")
    entry = admin_client.get("/debug/audit-tail?n=1").json()["entries"][0]
    assert entry["new"] == REDACTED


def test_n_is_respected_and_capped(admin_client: TestClient, db: sqlite3.Connection) -> None:
    _insert(db, MAX_TAIL + 20)
    assert admin_client.get("/debug/audit-tail?n=5").json()["count"] == 5
    assert admin_client.get("/debug/audit-tail?n=100000").json()["count"] == MAX_TAIL
    assert admin_client.get("/debug/audit-tail?n=0").json()["count"] == 1


def test_other_users_payload_is_scoped(admin_client: TestClient, db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO users (id, name) VALUES (2, 'user-b')")
    db.commit()
    _insert(db, 1, '{"description": "private-marker"}', user_id=2, entity_type="transactions")
    resp = admin_client.get("/debug/audit-tail?n=1")
    entry = resp.json()["entries"][0]
    assert entry["entity_type"] == "transactions"
    assert entry["user_id"] == 2
    assert entry["prev"] == OTHER_USER
    assert entry["new"] == OTHER_USER
    assert "private-marker" not in resp.text


def test_non_admin_is_404(client: TestClient) -> None:
    assert client.get("/debug/audit-tail").status_code == 404


def test_anonymous_is_not_served(anon_client: TestClient) -> None:
    resp = anon_client.get("/debug/audit-tail", follow_redirects=False)
    assert resp.status_code in {302, 303, 307, 401}
    assert "entries" not in resp.text
