"""Rehash a verified password at the configured bcrypt cost (T-Q313, ADR-0074 amendment)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from typing import cast

import pytest

from budget_planner.adapters.bcrypt_hasher import BcryptHasher
from budget_planner.repositories import sessions as sessions_repo, users as users_repo
from budget_planner.services import auth
from tests.integration.auth.conftest import PASSWORD

pytestmark = pytest.mark.integration

OLD = BcryptHasher(rounds=4)
NEW = BcryptHasher(rounds=5)
AuditRows = Callable[[str], list[sqlite3.Row]]


def _seed(conn: sqlite3.Connection, email: str, hashed: str, *, must_change: int = 0) -> int:
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash, must_change_password) VALUES (?, ?, ?, ?)",
        (email.split("@", maxsplit=1)[0], email, hashed, must_change),
    )
    return int(cur.lastrowid or 0)


def _row(conn: sqlite3.Connection, uid: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    assert row is not None
    return cast(sqlite3.Row, row)


def _login(
    conn: sqlite3.Connection, email: str, password: str
) -> sessions_repo.IssuedSession | None:
    return auth.authenticate_password(
        conn, email, password, ip="203.0.113.9", user_agent="pytest/1", hasher=NEW
    )


def _rehash_audit(audit_rows: AuditRows) -> list[sqlite3.Row]:
    return [r for r in audit_rows("users") if "password_rehash" in r["new_json"]]


def test_old_cost_hash_is_upgraded_on_login(
    conn: sqlite3.Connection, audit_rows: AuditRows
) -> None:
    uid = _seed(conn, "a@example.test", OLD.hash(PASSWORD), must_change=1)
    other_hash = OLD.hash("other-password-123")
    other = _seed(conn, "b@example.test", other_hash)
    before = _row(conn, uid)

    issued = _login(conn, "a@example.test", PASSWORD)

    assert issued is not None and issued.session.user_id == uid
    after = _row(conn, uid)
    assert after["password_hash"].startswith("$2b$05$")
    assert after["password_hash"] != before["password_hash"]
    assert NEW.verify(PASSWORD, after["password_hash"]) is True
    assert after["must_change_password"] == 1  # not a rotation
    assert _row(conn, other)["password_hash"] == other_hash
    rows = _rehash_audit(audit_rows)
    assert len(rows) == 1 and rows[0]["entity_id"] == uid
    payload = json.loads(rows[0]["new_json"])
    assert payload["action"] == "password_rehash"
    assert "password_hash" not in payload
    assert PASSWORD not in rows[0]["new_json"]
    live = conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (uid,)).fetchone()[0]
    assert live == 1  # only the new login session; nothing revoked


def test_same_cost_login_leaves_hash_and_audit_alone(
    conn: sqlite3.Connection, audit_rows: AuditRows
) -> None:
    stored = NEW.hash(PASSWORD)
    uid = _seed(conn, "a@example.test", stored)

    assert _login(conn, "a@example.test", PASSWORD) is not None

    assert _row(conn, uid)["password_hash"] == stored
    assert _rehash_audit(audit_rows) == []


def test_wrong_password_never_rehashes(conn: sqlite3.Connection, audit_rows: AuditRows) -> None:
    stored = OLD.hash(PASSWORD)
    uid = _seed(conn, "a@example.test", stored)

    assert _login(conn, "a@example.test", "wrong-password-xyz") is None

    assert _row(conn, uid)["password_hash"] == stored
    assert _rehash_audit(audit_rows) == []


def test_rehash_failure_does_not_fail_login(
    conn: sqlite3.Connection, audit_rows: AuditRows, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored = OLD.hash(PASSWORD)
    uid = _seed(conn, "a@example.test", stored)

    def _boom(*_a: object, **_k: object) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(users_repo, "rehash_password", _boom)

    issued = _login(conn, "a@example.test", PASSWORD)

    assert issued is not None and issued.session.user_id == uid
    assert _row(conn, uid)["password_hash"] == stored
    assert _rehash_audit(audit_rows) == []
