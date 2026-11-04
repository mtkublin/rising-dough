"""T-D02b — passkey ceremonies over HTTP with mocked WebAuthn verification.

``begin`` runs the real py_webauthn option generators; ``finish`` swaps the
service call for a stub so no authenticator is needed. The stubs assert the
challenge the router recovered from the signed cookie is exactly the one
``begin`` issued (ADR-0067 §1, ADR-0070 §3).
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.repositories import sessions as sessions_repo
from budget_planner.repositories.sessions import Session
from budget_planner.services import auth as auth_service
from budget_planner.web.auth_cookies import (
    CHALLENGE_COOKIE_NAME,
    CHALLENGE_TTL_SECONDS,
    SESSION_COOKIE_NAME,
    sign_challenge,
    verify_challenge,
)
from tests.auth_support import seed_login_user

pytestmark = pytest.mark.integration

_CREDENTIAL: dict[str, Any] = {"id": "abc", "rawId": "abc", "type": "public-key", "response": {}}


def _set_cookies(resp: Any, name: str) -> list[str]:
    return [h for h in resp.headers.get_list("set-cookie") if h.startswith(f"{name}=")]


def _challenge_from_options(resp: Any) -> str:
    return str(json.loads(resp.text)["challenge"])


def _b64url_to_bytes(text: str) -> bytes:
    import base64  # noqa: PLC0415

    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_begin_returns_options_and_challenge_cookie(anon_client: TestClient) -> None:
    r = anon_client.post("/auth/login/begin")
    assert r.status_code == 200
    options = r.json()
    assert options["userVerification"] == "required"
    assert options.get("allowCredentials", []) == []
    cookies = _set_cookies(r, CHALLENGE_COOKIE_NAME)
    assert len(cookies) == 1
    lowered = cookies[0].lower()
    assert "httponly" in lowered
    assert "samesite=strict" in lowered
    assert f"max-age={CHALLENGE_TTL_SECONDS}" in lowered
    assert "secure" in lowered


def test_login_finish_success_sets_session_and_clears_challenge(
    anon_client: TestClient,
    conn: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = seed_login_user(conn)
    begin = anon_client.post("/auth/login/begin")
    issued = _b64url_to_bytes(_challenge_from_options(begin))
    seen: dict[str, Any] = {}

    def _finish(c: sqlite3.Connection, credential: Any, **kw: Any) -> Session:
        seen["challenge"] = kw["challenge"]
        seen["credential"] = credential
        seen["ctx"] = kw["request_ctx"]
        return sessions_repo.create_session(c, user_id, ip=kw["ip"], user_agent=kw["user_agent"])

    monkeypatch.setattr(auth_service, "authenticate_passkey_finish", _finish)
    r = anon_client.post("/auth/login/finish?next=%2Fledger", json=_CREDENTIAL)
    assert r.status_code == 200, r.text
    assert r.json() == {"redirect": "/ledger"}
    assert seen["challenge"] == issued
    assert seen["credential"] == _CREDENTIAL
    assert len(_set_cookies(r, SESSION_COOKIE_NAME)) == 1
    cleared = _set_cookies(r, CHALLENGE_COOKIE_NAME)
    assert cleared
    assert "max-age=0" in cleared[0].lower()
    assert anon_client.get("/accounts", follow_redirects=False).status_code == 200


def test_login_finish_rejects_open_redirect(
    anon_client: TestClient, conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = seed_login_user(conn)
    anon_client.post("/auth/login/begin")
    monkeypatch.setattr(
        auth_service,
        "authenticate_passkey_finish",
        lambda c, _cred, **_kw: sessions_repo.create_session(c, user_id, ip=None, user_agent=None),
    )
    r = anon_client.post("/auth/login/finish?next=//evil.example", json=_CREDENTIAL)
    assert r.json() == {"redirect": "/today"}


def test_login_finish_failure_is_generic(
    anon_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    anon_client.post("/auth/login/begin")
    monkeypatch.setattr(auth_service, "authenticate_passkey_finish", lambda *_a, **_k: None)
    r = anon_client.post("/auth/login/finish", json=_CREDENTIAL)
    assert r.status_code == 401
    assert r.json() == {"error": "login_failed"}
    assert not _set_cookies(r, SESSION_COOKIE_NAME)
    assert "max-age=0" in _set_cookies(r, CHALLENGE_COOKIE_NAME)[0].lower()


def test_login_finish_without_challenge_cookie_never_verifies(
    anon_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _never(*_a: Any, **_k: Any) -> None:
        raise AssertionError("must not verify without a challenge")

    monkeypatch.setattr(auth_service, "authenticate_passkey_finish", _never)
    r = anon_client.post("/auth/login/finish", json=_CREDENTIAL)
    assert r.status_code == 401
    assert r.json() == {"error": "login_failed"}


def test_login_finish_with_tampered_cookie(
    anon_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    anon_client.post("/auth/login/begin")
    value = anon_client.cookies[CHALLENGE_COOKIE_NAME]
    body, _, sig = value.partition(".")
    anon_client.cookies.delete(CHALLENGE_COOKIE_NAME)
    anon_client.cookies.set(CHALLENGE_COOKIE_NAME, f"{body}.{sig[::-1]}")
    monkeypatch.setattr(
        auth_service,
        "authenticate_passkey_finish",
        lambda *_a, **_k: pytest.fail("tampered cookie must not verify"),
    )
    assert anon_client.post("/auth/login/finish", json=_CREDENTIAL).status_code == 401


@pytest.mark.parametrize("body", ["not json", "[1, 2]"])
def test_login_finish_rejects_non_object_body(anon_client: TestClient, body: str) -> None:
    r = anon_client.post(
        "/auth/login/finish", content=body, headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 400


def test_login_finish_with_real_service_and_garbage_credential(
    anon_client: TestClient, conn: sqlite3.Connection
) -> None:
    anon_client.post("/auth/login/begin")
    r = anon_client.post("/auth/login/finish", json={"garbage": True})
    assert r.status_code == 401
    row = conn.execute(
        "SELECT new_json FROM audit_log WHERE entity_type = 'auth_event' ORDER BY id DESC"
    ).fetchone()
    assert row is not None
    assert "malformed" in row["new_json"]


def test_login_begin_requires_csrf(anon_client: TestClient) -> None:
    r = anon_client.post("/auth/login/begin", headers={"X-CSRF-Token": "nope"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_page_renders(client: TestClient) -> None:
    r = client.get("/settings/security")
    assert r.status_code == 200
    assert "data-passkey-register" in r.text
    assert "/static/js/passkeys.js" in r.text


def test_register_requires_session(anon_client: TestClient) -> None:
    assert anon_client.get("/auth/register", follow_redirects=False).status_code == 302
    r = anon_client.post("/auth/register/begin", headers={"Accept": "application/json"})
    assert r.status_code == 401


def test_register_begin_returns_creation_options(client: TestClient) -> None:
    r = client.post("/auth/register/begin")
    assert r.status_code == 200
    options = r.json()
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["user"]["name"] == "owner@example.test"
    assert _set_cookies(r, CHALLENGE_COOKIE_NAME)


def test_register_finish_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    begin = client.post("/auth/register/begin")
    issued = _b64url_to_bytes(_challenge_from_options(begin))
    seen: dict[str, Any] = {}

    def _finish(_c: sqlite3.Connection, user_id: int, credential: Any, **kw: Any) -> object:
        seen.update(user_id=user_id, credential=credential, **kw)
        return object()

    monkeypatch.setattr(auth_service, "register_passkey_finish", _finish)
    r = client.post(
        "/auth/register/finish",
        json={"label": "  MacBook  " + "x" * 100, "credential": _CREDENTIAL},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"redirect": "/settings/security#passkeys"}
    assert seen["user_id"] == 1
    assert seen["challenge"] == issued
    assert seen["label"].startswith("MacBook")
    assert len(seen["label"]) == 64
    assert seen["request_ctx"].user_id == 1
    assert "max-age=0" in _set_cookies(r, CHALLENGE_COOKIE_NAME)[0].lower()


def test_register_finish_blank_label_defaults(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.post("/auth/register/begin")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        auth_service,
        "register_passkey_finish",
        lambda _c, _u, _cred, **kw: seen.update(kw),
    )
    client.post("/auth/register/finish", json={"label": None, "credential": _CREDENTIAL})
    assert seen["label"] == "Passkey"


def test_register_finish_service_error(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    client.post("/auth/register/begin")

    def _fail(*_a: Any, **_k: Any) -> None:
        raise auth_service.PasskeyRegistrationError("duplicate_credential")

    monkeypatch.setattr(auth_service, "register_passkey_finish", _fail)
    r = client.post("/auth/register/finish", json={"label": "x", "credential": _CREDENTIAL})
    assert r.status_code == 400
    assert r.json() == {"error": "duplicate_credential"}
    assert "max-age=0" in _set_cookies(r, CHALLENGE_COOKIE_NAME)[0].lower()


def test_register_finish_with_real_service_rejects_garbage(client: TestClient) -> None:
    client.post("/auth/register/begin")
    r = client.post("/auth/register/finish", json={"label": "x", "credential": {"id": "nope"}})
    assert r.status_code == 400
    assert r.json() == {"error": "invalid_response"}


def test_register_finish_missing_credential(client: TestClient) -> None:
    client.post("/auth/register/begin")
    r = client.post("/auth/register/finish", json={"label": "x"})
    assert r.status_code == 400
    assert r.json() == {"error": "invalid_response"}


def test_register_finish_rejects_login_challenge(client: TestClient) -> None:
    """A login-purpose challenge cookie cannot complete a registration."""
    client.post("/auth/login/begin")
    r = client.post("/auth/register/finish", json={"label": "x", "credential": _CREDENTIAL})
    assert r.status_code == 400
    assert r.json() == {"error": "challenge_expired"}


# ---------------------------------------------------------------------------
# Challenge envelope
# ---------------------------------------------------------------------------


def test_challenge_round_trip(settings: Settings) -> None:
    value = sign_challenge(settings, purpose="register", user_id=3, challenge=b"\x01\x02")
    env = verify_challenge(settings, value, purpose="register", user_id=3)
    assert env is not None
    assert env.challenge == b"\x01\x02"


@pytest.mark.parametrize(
    ("purpose", "user_id", "age"),
    [
        ("login", 3, 0),  # wrong purpose
        ("register", 4, 0),  # other user
        ("register", 3, CHALLENGE_TTL_SECONDS + 1),  # expired
        ("register", 3, -10),  # issued in the future
    ],
)
def test_challenge_mismatch_rejected(
    settings: Settings, purpose: str, user_id: int, age: int
) -> None:
    now = time.time()
    value = sign_challenge(settings, purpose="register", user_id=3, challenge=b"x", now=now)
    assert (
        verify_challenge(
            settings,
            value,
            purpose=purpose,  # type: ignore[arg-type]
            user_id=user_id,
            now=now + age,
        )
        is None
    )


@pytest.mark.parametrize("value", [None, "", "nodot", "!!!.!!!", "e30.AAAA"])
def test_challenge_garbage_rejected(settings: Settings, value: str | None) -> None:
    assert verify_challenge(settings, value, purpose="login", user_id=None) is None


def test_challenge_signed_with_other_secret_rejected(settings: Settings) -> None:
    other = Settings(_env_file=None, cookie_secret="another-secret-entirely")  # noqa: S106
    value = sign_challenge(other, purpose="login", user_id=None, challenge=b"x")
    assert verify_challenge(settings, value, purpose="login", user_id=None) is None


def test_challenge_valid_signature_bad_payload_rejected(settings: Settings) -> None:
    import base64  # noqa: PLC0415
    import hashlib  # noqa: PLC0415
    import hmac  # noqa: PLC0415

    payload = b'{"p":"login"}'
    mac = hmac.new(
        settings.cookie_secret.encode(), b"passkey-challenge|" + payload, hashlib.sha256
    ).digest()

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    assert (
        verify_challenge(settings, f"{b64(payload)}.{b64(mac)}", purpose="login", user_id=None)
        is None
    )
