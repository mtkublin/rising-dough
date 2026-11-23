# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""Isolation cases for the account-security services: audit, auth, reauth, rate_limit, password_change, users.

User 1 (owner) and user 2 (other) each get a password, sessions and a passkey row; every case asserts that an action
taken as one user changes nothing of the other's, and that soft-deleted users are invisible. Rows are plain
repository-level fixtures: no WebAuthn ceremony is run (the verification itself is covered in ``tests/integration/auth``).
"""

from __future__ import annotations

import base64
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

import pytest

from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import (
    auth_users,
    sessions as sessions_repo,
    webauthn as webauthn_repo,
)
from budget_planner.repositories.users import UserNotFoundError
from budget_planner.services import (
    audit,
    auth,
    password_change,
    rate_limit,
    reauth,
    users,
)
from tests.auth_support import FAKE_HASHER, FakeTokenSource, issue_session, seed_login_user
from tests.unit.services._isolation_registry import covers
from tests.unit.services.conftest import OTHER_ID, OWNER_ID, World

RP = auth.RelyingParty(rp_id="example.test", rp_name="Budget", origin="https://example.test")
CTX = RequestCtx(ip="203.0.113.9", user_id=None, session_id=None, user_agent="pytest")
OWNER_PASSWORD = "owner-password-123"  # noqa: S105  # pragma: allowlist secret
OTHER_PASSWORD = "other-password-456"  # noqa: S105  # pragma: allowlist secret
NEW_PASSWORD = "brand-new-passphrase"  # noqa: S105  # pragma: allowlist secret
OPERATOR_PASSWORD = "operator-chosen-pw"  # noqa: S105  # pragma: allowlist secret
OWNER_CRED = b"\x01\x02\x03\x04"
OTHER_CRED = b"\x09\x08\x07\x06"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _login_users(conn: sqlite3.Connection) -> None:
    seed_login_user(
        conn,
        user_id=OWNER_ID,
        email="owner@example.test",
        password=OWNER_PASSWORD,
        hasher=FAKE_HASHER,
    )
    seed_login_user(
        conn,
        user_id=OTHER_ID,
        email="other@example.test",
        password=OTHER_PASSWORD,
        hasher=FAKE_HASHER,
    )


def _credential(
    conn: sqlite3.Connection, user_id: int, cred_id: bytes
) -> webauthn_repo.WebAuthnCredential:
    return webauthn_repo.create_credential(
        conn,
        user_id=user_id,
        credential_id=cred_id,
        public_key=b"pk",
        sign_count=0,
        label=f"key-{user_id}",
    )


def _hash(conn: sqlite3.Connection, user_id: int) -> str:
    return str(
        conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()[0]
    )


def _audit_events(
    conn: sqlite3.Connection, entity_type: str
) -> list[tuple[int | None, dict[str, Any]]]:
    rows = conn.execute(
        "SELECT user_id, new_json FROM audit_log WHERE entity_type = ? ORDER BY id", (entity_type,)
    ).fetchall()
    return [(r["user_id"], json.loads(r["new_json"]) if r["new_json"] else {}) for r in rows]


def _live_handles(conn: sqlite3.Connection, user_id: int) -> set[str]:
    return {s.handle for s in sessions_repo.list_active_sessions(conn, user_id)}


# --- audit / rate_limit ------------------------------------------------------------------------------------------


@covers("audit.write_audit")
def _case_write_audit(conn: sqlite3.Connection, world: World) -> None:
    for user_id in (OWNER_ID, OTHER_ID):
        audit.write_audit(
            conn,
            entity_type="isolation_probe",
            entity_id=user_id,
            operation="create",
            prev=None,
            new={"n": user_id},
            user_id=user_id,
        )
    rows = conn.execute(
        "SELECT entity_id, user_id, actor_user_id FROM audit_log WHERE entity_type = 'isolation_probe' ORDER BY id"
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        (OWNER_ID, OWNER_ID, OWNER_ID),
        (OTHER_ID, OTHER_ID, OTHER_ID),
    ]
    with pytest.raises(audit.AuditShapeError):
        audit.write_audit(
            conn,
            entity_type="isolation_probe",
            entity_id=1,
            operation="delete",
            prev=None,
            new=None,
            user_id=OWNER_ID,
        )


@covers("rate_limit.audit_throttled")
def _case_audit_throttled(conn: sqlite3.Connection, world: World) -> None:
    rate_limit.audit_throttled(conn, CTX, scope="login", user_id=OWNER_ID)
    rate_limit.audit_throttled(conn, CTX, scope="login", user_id=None, email="x@example.test")
    events = _audit_events(conn, auth.AUTH_EVENT_ENTITY)
    assert events == [
        (OWNER_ID, {"event": "rate_limited", "scope": "login"}),
        (None, {"event": "rate_limited", "scope": "login", "email": "x@example.test"}),
    ]
    assert all(uid != OTHER_ID for uid, _ in events)


@covers("rate_limit.user_identity")
def _case_user_identity(conn: sqlite3.Connection, world: World) -> None:
    assert rate_limit.user_identity(OWNER_ID) == f"user={OWNER_ID}"
    assert rate_limit.user_identity(OWNER_ID) != rate_limit.user_identity(OTHER_ID)


# --- auth: passkeys and sessions ---------------------------------------------------------------------------------


@covers("auth.revoke_user_session")
def _case_revoke_user_session(conn: sqlite3.Connection, world: World) -> None:
    _login_users(conn)
    owner_token = issue_session(conn, user_id=OWNER_ID)
    other_token = issue_session(conn, user_id=OTHER_ID)
    owner_handle = sessions_repo.session_handle(owner_token)
    other_handle = sessions_repo.session_handle(other_token)
    assert auth.revoke_user_session(conn, OTHER_ID, owner_handle) is False  # not user 2's session
    assert _live_handles(conn, OWNER_ID) == {owner_handle}
    assert auth.revoke_user_session(conn, OWNER_ID, owner_handle) is True
    assert _live_handles(conn, OWNER_ID) == set()
    assert _live_handles(conn, OTHER_ID) == {other_handle}
    assert auth.revoke_user_session(conn, OWNER_ID, owner_handle) is False  # already revoked


@covers("auth.revoke_passkey")
def _case_revoke_passkey(conn: sqlite3.Connection, world: World) -> None:
    owner = _credential(conn, OWNER_ID, OWNER_CRED)
    other = _credential(conn, OTHER_ID, OTHER_CRED)
    assert auth.revoke_passkey(conn, OTHER_ID, owner.id) is False
    assert [c.id for c in webauthn_repo.list_credentials(conn, OWNER_ID)] == [owner.id]
    assert auth.revoke_passkey(conn, OWNER_ID, owner.id) is True
    assert webauthn_repo.list_credentials(conn, OWNER_ID) == ()
    assert [c.id for c in webauthn_repo.list_credentials(conn, OTHER_ID)] == [other.id]
    assert auth.revoke_passkey(conn, OWNER_ID, owner.id) is False  # soft-deleted row is gone


def _descriptor_ids(options_json: str, key: str) -> list[str]:
    return [c["id"] for c in json.loads(options_json).get(key, [])]


@covers("auth.register_passkey_begin")
def _case_register_passkey_begin(conn: sqlite3.Connection, world: World) -> None:
    _login_users(conn)
    _credential(conn, OWNER_ID, OWNER_CRED)
    revoked = _credential(conn, OWNER_ID, b"\x0a\x0b\x0c\x0d")
    webauthn_repo.revoke_credential(
        conn, OWNER_ID, revoked.id, reason="user_request", request_ctx=CTX
    )
    owner = auth.register_passkey_begin(conn, OWNER_ID, RP)
    other = auth.register_passkey_begin(conn, OTHER_ID, RP)
    assert _descriptor_ids(owner.options_json, "excludeCredentials") == [_b64(OWNER_CRED)]
    assert _descriptor_ids(other.options_json, "excludeCredentials") == []
    assert json.loads(owner.options_json)["user"]["id"] == _b64(str(OWNER_ID).encode("ascii"))
    with pytest.raises(auth.PasskeyRegistrationError):
        auth.register_passkey_begin(conn, 999, RP)


@covers("auth.register_passkey_finish")
def _case_register_passkey_finish(conn: sqlite3.Connection, world: World) -> None:
    _login_users(conn)
    for user_id, reason in ((999, "unknown_user"), (OTHER_ID, "invalid_response")):
        with pytest.raises(auth.PasskeyRegistrationError) as excinfo:
            auth.register_passkey_finish(conn, user_id, "{}", challenge=b"c", rp=RP, label="junk")
        assert excinfo.value.args == (reason,)
    assert webauthn_repo.list_credentials(conn, OWNER_ID) == ()
    assert webauthn_repo.list_credentials(conn, OTHER_ID) == ()


# --- reauth ------------------------------------------------------------------------------------------------------


@covers("reauth.verify_password_reauth")
def _case_verify_password_reauth(conn: sqlite3.Connection, world: World) -> None:
    _login_users(conn)
    assert (
        reauth.verify_password_reauth(conn, OWNER_ID, OWNER_PASSWORD, ctx=CTX, hasher=FAKE_HASHER)
        is True
    )
    assert (
        reauth.verify_password_reauth(conn, OTHER_ID, OTHER_PASSWORD, ctx=CTX, hasher=FAKE_HASHER)
        is True
    )
    assert (
        reauth.verify_password_reauth(conn, OTHER_ID, OWNER_PASSWORD, ctx=CTX, hasher=FAKE_HASHER)
        is False
    )  # the other account's password
    users.soft_delete_user(conn, OWNER_ID, OTHER_ID)
    assert (
        reauth.verify_password_reauth(conn, OTHER_ID, OTHER_PASSWORD, ctx=CTX, hasher=FAKE_HASHER)
        is False
    )  # tombstoned user
    failures = _audit_events(conn, auth.AUTH_EVENT_ENTITY)
    assert failures == [
        (OTHER_ID, {"event": "reauth_failed", "method": "password", "reason": "bad_password"}),
        (OTHER_ID, {"event": "reauth_failed", "method": "password", "reason": "no_password"}),
    ]


@covers("reauth.attempts_left")
def _case_reauth_attempts_left(conn: sqlite3.Connection, world: World) -> None:
    now = datetime(2026, 11, 15, 12, 0, 10, tzinfo=UTC)
    rules = (rate_limit.RateRule(limit=5, window_seconds=60),)
    identity = rate_limit.user_identity(OWNER_ID)
    for _ in range(2):
        rate_limit.consume(conn, rate_limit.SCOPE_REAUTH, identity, rules, now=now)
    assert reauth.attempts_left(conn, OWNER_ID, rules, now=now) == 3
    assert reauth.attempts_left(conn, OTHER_ID, rules, now=now) == 5  # owner's failures not shared


@covers("reauth.passkey_reauth_begin")
def _case_passkey_reauth_begin(conn: sqlite3.Connection, world: World) -> None:
    _credential(conn, OWNER_ID, OWNER_CRED)
    _credential(conn, OTHER_ID, OTHER_CRED)
    owner = reauth.passkey_reauth_begin(conn, OWNER_ID, RP)
    other = reauth.passkey_reauth_begin(conn, OTHER_ID, RP)
    assert owner is not None
    assert other is not None
    assert _descriptor_ids(owner.options_json, "allowCredentials") == [_b64(OWNER_CRED)]
    assert _descriptor_ids(other.options_json, "allowCredentials") == [_b64(OTHER_CRED)]
    assert reauth.passkey_reauth_begin(conn, 999, RP) is None  # no credentials, no challenge


def _assertion(raw_id: bytes) -> dict[str, Any]:
    return {
        "id": _b64(raw_id),
        "rawId": _b64(raw_id),
        "type": "public-key",
        "response": {
            "clientDataJSON": _b64(b"{}"),
            "authenticatorData": _b64(b"\x00" * 37),
            "signature": _b64(b"sig"),
        },
    }


@covers("reauth.verify_passkey_reauth")
def _case_verify_passkey_reauth(conn: sqlite3.Connection, world: World) -> None:
    _credential(conn, OWNER_ID, OWNER_CRED)
    _credential(conn, OTHER_ID, OTHER_CRED)
    # User 2 presenting user 1's credential id is "unknown": credentials never cross users.
    assert (
        reauth.verify_passkey_reauth(
            conn, OTHER_ID, _assertion(OWNER_CRED), challenge=b"c", rp=RP, ctx=CTX
        )
        is False
    )
    assert (
        reauth.verify_passkey_reauth(conn, OWNER_ID, "not json", challenge=b"c", rp=RP, ctx=CTX)
        is False
    )
    # Its own credential reaches verification, which rejects the junk signature.
    assert (
        reauth.verify_passkey_reauth(
            conn, OWNER_ID, _assertion(OWNER_CRED), challenge=b"c", rp=RP, ctx=CTX
        )
        is False
    )
    reasons = [(uid, e["reason"]) for uid, e in _audit_events(conn, auth.AUTH_EVENT_ENTITY)]
    assert reasons == [
        (OTHER_ID, "unknown_credential"),
        (OWNER_ID, "malformed"),
        (OWNER_ID, "verification_failed"),
    ]


@covers("reauth.complete_reauth")
def _case_complete_reauth(conn: sqlite3.Connection, world: World) -> None:
    _login_users(conn)
    owner_token = issue_session(conn, user_id=OWNER_ID)
    other_token = issue_session(conn, user_id=OTHER_ID)
    issued = reauth.complete_reauth(
        conn, owner_token, OWNER_ID, method=reauth.METHOD_PASSWORD, ctx=CTX
    )
    assert issued is not None
    assert issued.session.user_id == OWNER_ID
    assert issued.token != owner_token
    assert sessions_repo.get_session(conn, owner_token) is None  # the old token stopped resolving
    other_session = sessions_repo.get_session(conn, other_token)
    assert other_session is not None  # user 2's session is untouched
    assert other_session.user_id == OTHER_ID
    assert (
        reauth.complete_reauth(
            conn, "no-such-token", OWNER_ID, method=reauth.METHOD_PASSWORD, ctx=CTX
        )
        is None
    )
    assert _audit_events(conn, auth.AUTH_EVENT_ENTITY) == [
        (OWNER_ID, {"event": "reauth", "method": "password"})
    ]


# --- password_change ---------------------------------------------------------------------------------------------


@covers("password_change.change_own_password")
def _case_change_own_password(conn: sqlite3.Connection, world: World) -> None:
    _login_users(conn)
    owner_current = issue_session(conn, user_id=OWNER_ID)
    owner_old = issue_session(conn, user_id=OWNER_ID)
    other_token = issue_session(conn, user_id=OTHER_ID)
    other_hash = _hash(conn, OTHER_ID)
    req = password_change.PasswordChangeRequest(
        current_password=OWNER_PASSWORD,
        new_password=NEW_PASSWORD,
        confirm_password=NEW_PASSWORD,
    )
    # User 2 cannot rotate with user 1's password: failure, nothing written, user 1's hash untouched.
    owner_hash = _hash(conn, OWNER_ID)
    wrong = password_change.change_own_password(
        conn,
        OTHER_ID,
        req,
        current_session_id=other_token,
        request_ctx=CTX,
        hasher=FAKE_HASHER,
    )
    assert [e.field for e in wrong.errors] == ["current_password"]
    assert (_hash(conn, OWNER_ID), _hash(conn, OTHER_ID)) == (owner_hash, other_hash)
    outcome = password_change.change_own_password(
        conn,
        OWNER_ID,
        req,
        current_session_id=owner_current,
        request_ctx=CTX,
        hasher=FAKE_HASHER,
    )
    assert outcome.errors == ()
    assert outcome.revoked_sessions == 1  # only user 1's other session
    assert _hash(conn, OWNER_ID) != owner_hash
    assert FAKE_HASHER.verify(NEW_PASSWORD, _hash(conn, OWNER_ID))
    assert _hash(conn, OTHER_ID) == other_hash
    assert sessions_repo.get_session(conn, owner_old) is None
    assert sessions_repo.get_session(conn, other_token) is not None
    with pytest.raises(UserNotFoundError):
        password_change.change_own_password(
            conn,
            999,
            req,
            current_session_id=None,
            request_ctx=CTX,
            hasher=FAKE_HASHER,
        )


# --- users (admin) -----------------------------------------------------------------------------------------------


def _draft(email: str, name: str) -> users.UserDraft:
    return users.UserDraft(email=email, name=name, is_admin=False)


@covers("users.get_live_user")
def _case_get_live_user(conn: sqlite3.Connection, world: World) -> None:
    _login_users(conn)
    assert users.get_live_user(conn, OWNER_ID).email == "owner@example.test"
    assert users.get_live_user(conn, OTHER_ID).email == "other@example.test"
    users.soft_delete_user(conn, OWNER_ID, OTHER_ID)
    with pytest.raises(users.UserNotFound):
        users.get_live_user(conn, OTHER_ID)
    assert users.get_live_user(conn, OWNER_ID).id == OWNER_ID


@covers("users.edit_user")
def _case_edit_user(conn: sqlite3.Connection, world: World) -> None:
    _login_users(conn)
    edited = users.edit_user(conn, OWNER_ID, OTHER_ID, _draft("other@example.test", "Renamed"))
    assert (edited.id, edited.email, edited.name) == (OTHER_ID, "other@example.test", "Renamed")
    assert users.get_live_user(conn, OWNER_ID).email == "owner@example.test"
    with pytest.raises(users.UserInputError):  # the email is read-only on edit
        users.edit_user(conn, OWNER_ID, OTHER_ID, _draft("owner@example.test", "x"))
    assert users.get_live_user(conn, OTHER_ID).email == "other@example.test"
    users.soft_delete_user(conn, OWNER_ID, OTHER_ID)
    with pytest.raises(users.UserNotFound):
        users.edit_user(conn, OWNER_ID, OTHER_ID, _draft("again@example.test", "x"))


@covers("users.reset_password")
def _case_reset_password(conn: sqlite3.Connection, world: World) -> None:
    _login_users(conn)
    owner_hash = _hash(conn, OWNER_ID)
    other_token = issue_session(conn, user_id=OTHER_ID)
    owner_token = issue_session(conn, user_id=OWNER_ID)
    user, plaintext = users.reset_password(
        conn, OWNER_ID, OTHER_ID, tokens=FakeTokenSource(), hasher=FAKE_HASHER
    )
    assert user.id == OTHER_ID
    assert FAKE_HASHER.verify(plaintext, _hash(conn, OTHER_ID))
    assert _hash(conn, OWNER_ID) == owner_hash
    assert sessions_repo.get_session(conn, other_token) is None  # target's sessions revoked
    assert sessions_repo.get_session(conn, owner_token) is not None
    with pytest.raises(users.UserNotFound):
        users.reset_password(conn, OWNER_ID, 999, tokens=FakeTokenSource(), hasher=FAKE_HASHER)


@covers("users.set_user_password")
def _case_set_user_password(conn: sqlite3.Connection, world: World) -> None:
    _login_users(conn)
    owner_hash = _hash(conn, OWNER_ID)
    user = users.set_user_password(
        conn,
        OTHER_ID,
        change=users.PasswordChange(password=OPERATOR_PASSWORD, must_change_password=True),
        hasher=FAKE_HASHER,
    )
    assert (user.id, user.must_change_password) == (OTHER_ID, True)
    assert FAKE_HASHER.verify(OPERATOR_PASSWORD, _hash(conn, OTHER_ID))
    assert _hash(conn, OWNER_ID) == owner_hash
    with pytest.raises(UserNotFoundError):
        users.set_user_password(
            conn,
            999,
            change=users.PasswordChange(password=OPERATOR_PASSWORD, must_change_password=True),
            hasher=FAKE_HASHER,
        )


@covers("users.soft_delete_user")
def _case_soft_delete_user(conn: sqlite3.Connection, world: World) -> None:
    _login_users(conn)
    other_token = issue_session(conn, user_id=OTHER_ID)
    owner_token = issue_session(conn, user_id=OWNER_ID)
    deleted = users.soft_delete_user(conn, OWNER_ID, OTHER_ID)
    assert deleted.id == OTHER_ID
    assert auth_users.get_live_by_id(conn, OTHER_ID) is None
    assert auth_users.get_live_by_id(conn, OWNER_ID) is not None
    assert sessions_repo.get_session(conn, other_token) is None
    assert sessions_repo.get_session(conn, owner_token) is not None
    with pytest.raises(users.UserNotFound):
        users.soft_delete_user(
            conn, OWNER_ID, OTHER_ID
        )  # a tombstoned user cannot be deleted twice
    with pytest.raises(users.UserConflict):
        users.soft_delete_user(conn, OWNER_ID, OWNER_ID)
