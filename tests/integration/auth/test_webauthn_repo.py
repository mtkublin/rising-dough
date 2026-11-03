"""Integration tests for ``repositories.webauthn`` (T-D02a, ADR-0067)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import webauthn as repo

pytestmark = pytest.mark.integration

CRED_ID = b"\x01\x02\x03\x04"
PUBKEY = b"\xa5\x01\x02"


def _create(
    conn: sqlite3.Connection, user_id: int, cred_id: bytes = CRED_ID, **kw: Any
) -> repo.WebAuthnCredential:
    return repo.create_credential(
        conn,
        user_id=user_id,
        credential_id=cred_id,
        public_key=PUBKEY,
        sign_count=0,
        **kw,
    )


def test_create_and_lookup_round_trip(
    conn: sqlite3.Connection,
    make_user: Callable[..., int],
    audit_rows: Callable[[str], list[sqlite3.Row]],
) -> None:
    uid = make_user()
    ctx = RequestCtx(ip="198.51.100.1", user_id=uid, session_id="h", user_agent="ua")
    cred = _create(conn, uid, transports=("internal", "hybrid"), label="Laptop", request_ctx=ctx)

    assert cred.credential_id == CRED_ID
    assert cred.public_key == PUBKEY
    assert cred.transports == ("internal", "hybrid")
    assert cred.label == "Laptop"
    assert cred.deleted_at is None
    assert repo.get_by_credential_id(conn, CRED_ID) == cred
    assert repo.list_credentials(conn, uid) == (cred,)

    rows = audit_rows(repo.ENTITY_TYPE)
    assert len(rows) == 1
    assert rows[0]["operation"] == "create"
    assert rows[0]["entity_id"] == cred.id
    assert rows[0]["ip"] == "198.51.100.1"
    payload = json.loads(rows[0]["new_json"])
    assert payload["credential_id"] == "AQIDBA"
    assert "public_key" not in payload


def test_duplicate_credential_id_rejected(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    _create(conn, uid)
    with pytest.raises(sqlite3.IntegrityError):
        _create(conn, uid)


def test_list_is_scoped_by_user(conn: sqlite3.Connection, make_user: Callable[..., int]) -> None:
    alice = make_user()
    bob = make_user(email="bob@example.test")
    _create(conn, alice, b"a")
    _create(conn, bob, b"b")
    assert [c.credential_id for c in repo.list_credentials(conn, alice)] == [b"a"]
    assert repo.list_credentials(conn, alice)[0].transports == ()


def test_update_sign_count_sets_last_used(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    cred = _create(conn, uid)
    when = datetime(2026, 11, 3, 9, 30, tzinfo=UTC)
    repo.update_sign_count(conn, cred.id, 7, now=when)
    updated = repo.get_by_credential_id(conn, CRED_ID)
    assert updated is not None
    assert updated.sign_count == 7
    assert updated.last_used_at == when

    repo.update_sign_count(conn, cred.id, 8)
    again = repo.get_by_credential_id(conn, CRED_ID)
    assert again is not None
    assert again.sign_count == 8


def test_revoke_soft_deletes_and_audits(
    conn: sqlite3.Connection,
    make_user: Callable[..., int],
    audit_rows: Callable[[str], list[sqlite3.Row]],
) -> None:
    uid = make_user()
    cred = _create(conn, uid)

    assert repo.revoke_credential(conn, cred.id, user_id=uid, reason="lost") is True

    assert repo.get_by_credential_id(conn, CRED_ID) is None
    assert repo.list_credentials(conn, uid) == ()
    deleted = repo.list_credentials(conn, uid, include_deleted=True)
    assert len(deleted) == 1
    assert deleted[0].deleted_at is not None
    rows = audit_rows(repo.ENTITY_TYPE)
    assert [r["operation"] for r in rows] == ["create", "delete"]
    assert json.loads(rows[1]["prev_json"])["reason"] == "lost"
    assert rows[1]["new_json"] is None

    assert repo.revoke_credential(conn, cred.id) is False  # already gone


def test_revoke_refuses_other_users_credential(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    alice = make_user()
    bob = make_user(email="bob@example.test")
    cred = _create(conn, alice)
    assert repo.revoke_credential(conn, cred.id, user_id=bob) is False
    assert repo.revoke_credential(conn, 9999) is False
    assert repo.get_by_credential_id(conn, CRED_ID) is not None
