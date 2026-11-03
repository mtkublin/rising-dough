"""Integration tests for ``services.auth`` (T-D02a, ADR-0033/0061/0067)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse

from budget_planner.config import Settings
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import sessions as sessions_repo, webauthn as webauthn_repo
from budget_planner.services import _passwords, auth
from tests.integration.auth.conftest import PASSWORD

pytestmark = pytest.mark.integration

RP = auth.RelyingParty(rp_id="localhost", rp_name="Test", origin="http://localhost:8000")
RAW_ID = b"\x10\x20\x30\x40"
AuditRows = Callable[[str], list[sqlite3.Row]]


def _login(conn: sqlite3.Connection, email: str, password: str) -> sessions_repo.Session | None:
    return auth.authenticate_password(
        conn, email, password, ip="203.0.113.9", user_agent="pytest/1"
    )


# ---------------------------------------------------------------------------
# Password login
# ---------------------------------------------------------------------------


def test_password_login_happy_path(
    conn: sqlite3.Connection, make_user: Callable[..., int], audit_rows: AuditRows
) -> None:
    uid = make_user()

    session = _login(conn, "  ALICE@Example.TEST ", PASSWORD)

    assert session is not None
    assert session.user_id == uid
    assert session.ip == "203.0.113.9"
    assert sessions_repo.get_session(conn, session.id) is not None
    rows = audit_rows(auth.SESSION_ENTITY)
    assert len(rows) == 1
    row = rows[0]
    assert (row["entity_id"], row["operation"]) == (uid, "create")
    assert row["user_id"] == uid
    assert row["session_id"] == session.handle
    assert row["ip"] == "203.0.113.9"
    assert row["user_agent"] == "pytest/1"
    payload = json.loads(row["new_json"])
    assert payload["method"] == "password"
    assert session.id not in row["new_json"]  # raw bearer id never audited


def test_wrong_password_returns_none_and_audits_failure(
    conn: sqlite3.Connection, make_user: Callable[..., int], audit_rows: AuditRows
) -> None:
    uid = make_user()

    assert _login(conn, "alice@example.test", "wrong") is None

    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    rows = audit_rows(auth.AUTH_EVENT_ENTITY)
    assert len(rows) == 1
    assert rows[0]["entity_id"] == uid
    assert rows[0]["user_id"] == uid
    assert json.loads(rows[0]["new_json"])["reason"] == "bad_password"


def test_unknown_email_runs_dummy_verify_and_audits(
    conn: sqlite3.Connection,
    audit_rows: AuditRows,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    real = _passwords.verify_password

    def _spy(plain: str, hashed: str | None) -> bool:
        calls.append(plain)
        return real(plain, hashed)

    monkeypatch.setattr(auth, "verify_password", _spy)

    assert _login(conn, "ghost@example.test", "whatever") is None

    assert calls == ["whatever"], "dummy bcrypt verify must run for unknown emails"
    rows = audit_rows(auth.AUTH_EVENT_ENTITY)
    assert len(rows) == 1
    assert rows[0]["entity_id"] == 0
    assert rows[0]["user_id"] is None
    payload = json.loads(rows[0]["new_json"])
    assert payload == {
        "event": "login_failed",
        "method": "password",
        "reason": "unknown_email",
        "email": "ghost@example.test",
    }


def test_user_without_password_and_deleted_user_cannot_log_in(
    conn: sqlite3.Connection, make_user: Callable[..., int], audit_rows: AuditRows
) -> None:
    make_user(email="nopw@example.test", password=None)
    make_user(email="gone@example.test", deleted=True)

    assert _login(conn, "nopw@example.test", PASSWORD) is None
    assert _login(conn, "gone@example.test", PASSWORD) is None
    reasons = [json.loads(r["new_json"])["reason"] for r in audit_rows(auth.AUTH_EVENT_ENTITY)]
    assert reasons == ["no_password", "unknown_email"]


def test_explicit_request_ctx_is_used_for_audit(
    conn: sqlite3.Connection, make_user: Callable[..., int], audit_rows: AuditRows
) -> None:
    make_user()
    ctx = RequestCtx(ip="192.0.2.1", user_id=None, session_id=None, user_agent="ctx-ua")
    session = auth.authenticate_password(
        conn, "alice@example.test", PASSWORD, ip="ignored", user_agent="ignored", request_ctx=ctx
    )
    assert session is not None
    row = audit_rows(auth.SESSION_ENTITY)[0]
    assert (row["ip"], row["user_agent"]) == ("192.0.2.1", "ctx-ua")


# ---------------------------------------------------------------------------
# Sessions — logout, revoke, load
# ---------------------------------------------------------------------------


def test_logout_revokes_and_audits(
    conn: sqlite3.Connection, make_user: Callable[..., int], audit_rows: AuditRows
) -> None:
    uid = make_user()
    session = _login(conn, "alice@example.test", PASSWORD)
    assert session is not None

    assert auth.logout(conn, session.id) is True

    assert sessions_repo.get_session(conn, session.id) is None
    assert auth.load_session_user(conn, session.id) is None
    delete_rows = [r for r in audit_rows(auth.SESSION_ENTITY) if r["operation"] == "delete"]
    assert len(delete_rows) == 1
    assert delete_rows[0]["entity_id"] == uid
    assert json.loads(delete_rows[0]["prev_json"]) == {
        "event": "logout",
        "session": session.handle,
    }
    assert auth.logout(conn, session.id) is False  # already revoked
    assert auth.logout(conn, "unknown") is False


def test_revoke_user_session_requires_ownership(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    alice = make_user()
    bob = make_user(email="bob@example.test")
    s = sessions_repo.create_session(conn, alice, ip=None, user_agent=None)

    assert auth.revoke_user_session(conn, bob, s.id) is False
    assert sessions_repo.get_session(conn, s.id) is not None
    assert auth.revoke_user_session(conn, alice, s.id) is True
    assert sessions_repo.get_session(conn, s.id) is None


def test_load_session_user_returns_user_and_touches(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    s = sessions_repo.create_session(conn, uid, ip=None, user_agent=None)

    loaded = auth.load_session_user(conn, s.id)
    assert loaded is not None
    session, user = loaded
    assert session.id == s.id
    assert (user.id, user.email, user.is_admin) == (uid, "alice@example.test", False)
    refreshed = sessions_repo.get_session(conn, s.id)
    assert refreshed is not None
    assert refreshed.last_seen_at >= s.last_seen_at

    assert auth.load_session_user(conn, s.id, touch=False) is not None


# ---------------------------------------------------------------------------
# Passkey registration
# ---------------------------------------------------------------------------


def _registration_json() -> dict[str, Any]:
    rid = bytes_to_base64url(RAW_ID)
    return {
        "id": rid,
        "rawId": rid,
        "type": "public-key",
        "response": {
            "clientDataJSON": "e30",
            "attestationObject": "AAAA",
            "transports": ["internal", "hybrid"],
        },
    }


def _fake_verified_registration(**_: Any) -> SimpleNamespace:
    return SimpleNamespace(credential_id=RAW_ID, credential_public_key=b"pk", sign_count=0)


def test_register_begin_returns_options_and_challenge(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    webauthn_repo.create_credential(
        conn, user_id=uid, credential_id=b"existing", public_key=b"k", sign_count=0
    )

    ch = auth.register_passkey_begin(conn, uid, RP)

    options = json.loads(ch.options_json)
    assert base64url_to_bytes(options["challenge"]) == ch.challenge
    assert len(ch.challenge) >= 16
    assert options["rp"] == {"id": "localhost", "name": "Test"}
    assert options["user"]["name"] == "alice@example.test"
    assert options["authenticatorSelection"]["userVerification"] == "required"
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert [c["id"] for c in options["excludeCredentials"]] == [bytes_to_base64url(b"existing")]


def test_register_begin_unknown_user(conn: sqlite3.Connection) -> None:
    with pytest.raises(auth.PasskeyRegistrationError) as exc:
        auth.register_passkey_begin(conn, 9999, RP)
    assert exc.value.reason == "unknown_user"


def test_register_finish_persists_credential(
    conn: sqlite3.Connection,
    make_user: Callable[..., int],
    audit_rows: AuditRows,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid = make_user()
    seen: dict[str, Any] = {}

    def _verify(**kwargs: Any) -> SimpleNamespace:
        seen.update(kwargs)
        return _fake_verified_registration()

    monkeypatch.setattr(auth, "verify_registration_response", _verify)

    cred = auth.register_passkey_finish(
        conn, uid, json.dumps(_registration_json()), challenge=b"chal", rp=RP, label=" Mac "
    )

    assert seen["expected_challenge"] == b"chal"
    assert seen["expected_rp_id"] == "localhost"
    assert seen["expected_origin"] == "http://localhost:8000"
    assert seen["require_user_verification"] is True
    assert cred.credential_id == RAW_ID
    assert cred.public_key == b"pk"
    assert cred.label == "Mac"
    assert cred.transports == ("internal", "hybrid")
    rows = audit_rows(webauthn_repo.ENTITY_TYPE)
    assert len(rows) == 1
    assert rows[0]["user_id"] == uid


def test_register_finish_rejects_duplicate(
    conn: sqlite3.Connection, make_user: Callable[..., int], monkeypatch: pytest.MonkeyPatch
) -> None:
    uid = make_user()
    monkeypatch.setattr(auth, "verify_registration_response", _fake_verified_registration)
    auth.register_passkey_finish(conn, uid, _registration_json(), challenge=b"c", rp=RP, label="a")
    with pytest.raises(auth.PasskeyRegistrationError) as exc:
        auth.register_passkey_finish(
            conn, uid, _registration_json(), challenge=b"c", rp=RP, label="b"
        )
    assert exc.value.reason == "duplicate_credential"


def test_register_finish_invalid_response_and_unknown_user(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    # Real verifier: the fake attestation cannot pass.
    with pytest.raises(auth.PasskeyRegistrationError) as exc:
        auth.register_passkey_finish(
            conn, uid, _registration_json(), challenge=b"c", rp=RP, label="x"
        )
    assert exc.value.reason == "invalid_response"
    with pytest.raises(auth.PasskeyRegistrationError) as exc2:
        auth.register_passkey_finish(
            conn, 9999, _registration_json(), challenge=b"c", rp=RP, label="x"
        )
    assert exc2.value.reason == "unknown_user"


def test_revoke_passkey_scoped_to_owner(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    alice = make_user()
    bob = make_user(email="bob@example.test")
    cred = webauthn_repo.create_credential(
        conn, user_id=alice, credential_id=b"x", public_key=b"k", sign_count=0
    )
    assert auth.revoke_passkey(conn, bob, cred.id) is False
    assert auth.revoke_passkey(conn, alice, cred.id) is True


# ---------------------------------------------------------------------------
# Passkey login
# ---------------------------------------------------------------------------


def _assertion_json(raw_id: bytes = RAW_ID) -> str:
    rid = bytes_to_base64url(raw_id)
    return json.dumps(
        {
            "id": rid,
            "rawId": rid,
            "type": "public-key",
            "response": {"clientDataJSON": "e30", "authenticatorData": "AAAA", "signature": "AQ"},
        }
    )


@pytest.fixture
def passkey_user(conn: sqlite3.Connection, make_user: Callable[..., int]) -> int:
    uid = make_user()
    webauthn_repo.create_credential(
        conn, user_id=uid, credential_id=RAW_ID, public_key=b"pk", sign_count=5
    )
    return uid


def _finish(
    conn: sqlite3.Connection, payload: str | dict[str, Any] | None = None
) -> sessions_repo.Session | None:
    return auth.authenticate_passkey_finish(
        conn,
        _assertion_json() if payload is None else payload,
        challenge=b"chal",
        rp=RP,
        ip="203.0.113.1",
        user_agent="ua",
    )


def test_authenticate_begin_is_usernameless() -> None:
    ch = auth.authenticate_passkey_begin(RP)
    options = json.loads(ch.options_json)
    assert base64url_to_bytes(options["challenge"]) == ch.challenge
    assert options["rpId"] == "localhost"
    assert options["userVerification"] == "required"
    assert options.get("allowCredentials", []) == []


def test_authenticate_finish_happy_path(
    conn: sqlite3.Connection,
    passkey_user: int,
    audit_rows: AuditRows,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def _verify(**kwargs: Any) -> SimpleNamespace:
        seen.update(kwargs)
        return SimpleNamespace(new_sign_count=6)

    monkeypatch.setattr(auth, "verify_authentication_response", _verify)

    session = _finish(conn)

    assert session is not None
    assert session.user_id == passkey_user
    assert seen["credential_public_key"] == b"pk"
    assert seen["credential_current_sign_count"] == 0
    assert seen["require_user_verification"] is True
    stored = webauthn_repo.get_by_credential_id(conn, RAW_ID)
    assert stored is not None
    assert stored.sign_count == 6
    assert stored.last_used_at is not None
    login = audit_rows(auth.SESSION_ENTITY)[0]
    assert json.loads(login["new_json"])["method"] == "passkey"


def test_authenticate_finish_sign_count_regression_revokes_credential(
    conn: sqlite3.Connection,
    passkey_user: int,
    audit_rows: AuditRows,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth, "verify_authentication_response", lambda **_: SimpleNamespace(new_sign_count=5)
    )

    assert _finish(conn) is None

    assert webauthn_repo.get_by_credential_id(conn, RAW_ID) is None
    cred_rows = audit_rows(webauthn_repo.ENTITY_TYPE)
    assert cred_rows[-1]["operation"] == "delete"
    assert json.loads(cred_rows[-1]["prev_json"])["reason"] == "sign_count_regression"
    failure = audit_rows(auth.AUTH_EVENT_ENTITY)[-1]
    assert json.loads(failure["new_json"])["reason"] == "sign_count_regression"
    assert failure["entity_id"] == passkey_user


def test_authenticate_finish_verification_failure(
    conn: sqlite3.Connection,
    passkey_user: int,
    audit_rows: AuditRows,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(**_: Any) -> None:
        raise InvalidAuthenticationResponse("bad signature")

    monkeypatch.setattr(auth, "verify_authentication_response", _boom)

    assert _finish(conn) is None
    assert webauthn_repo.get_by_credential_id(conn, RAW_ID) is not None  # not revoked
    assert json.loads(audit_rows(auth.AUTH_EVENT_ENTITY)[-1]["new_json"])["reason"] == (
        "verification_failed"
    )


def test_authenticate_finish_real_verifier_rejects_forgery(
    conn: sqlite3.Connection, passkey_user: int
) -> None:
    assert _finish(conn) is None


def test_authenticate_finish_unknown_and_malformed(
    conn: sqlite3.Connection, passkey_user: int, audit_rows: AuditRows
) -> None:
    assert _finish(conn, _assertion_json(b"nope")) is None
    assert _finish(conn, "garbage") is None
    reasons = [json.loads(r["new_json"])["reason"] for r in audit_rows(auth.AUTH_EVENT_ENTITY)]
    assert reasons == ["unknown_credential", "malformed"]


def test_authenticate_finish_deleted_user(
    conn: sqlite3.Connection, passkey_user: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        auth, "verify_authentication_response", lambda **_: SimpleNamespace(new_sign_count=9)
    )
    conn.execute(
        "UPDATE users SET deleted_at = '2026-01-01T00:00:00Z' WHERE id = ?", (passkey_user,)
    )
    assert _finish(conn) is None


@pytest.mark.parametrize(
    ("stored", "new", "regressed"),
    [(0, 0, False), (0, 1, False), (5, 6, False), (5, 5, True), (5, 0, True), (5, 4, True)],
)
def test_sign_count_regressed(stored: int, new: int, regressed: bool) -> None:
    assert auth.sign_count_regressed(stored, new) is regressed


def test_relying_party_from_settings() -> None:
    settings = Settings(
        _env_file=None,
        webauthn_rp_id="budget.example.com",
        webauthn_rp_name="RD",
        webauthn_origin="https://budget.example.com",
    )
    assert auth.relying_party_from_settings(settings) == auth.RelyingParty(
        rp_id="budget.example.com", rp_name="RD", origin="https://budget.example.com"
    )
    assert auth.relying_party_from_settings().rp_id == "localhost"
