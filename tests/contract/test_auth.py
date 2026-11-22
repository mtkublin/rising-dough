"""Auth route contracts: login, logout, re-auth, passkeys, sessions (T-UT04a, ADR-0106 section 1).

Each test pins status, redirect target, HX-* / JSON shape, CSRF enforcement,
session requirement and the audit / DB effect. Markup is not asserted here.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.repositories import sessions as sessions_repo, webauthn as webauthn_repo
from budget_planner.web.auth_cookies import CHALLENGE_COOKIE_NAME, SESSION_COOKIE_NAME
from tests.auth_support import TEST_EMAIL, TEST_PASSWORD, seed_login_user
from tests.contract._audit import audit_count, auth_events
from tests.contract.conftest import covers

pytest_plugins = ["tests.contract._support"]

WINDOW_MINUTES = 10
WRONG = "not-the-password"  # pragma: allowlist secret
JSON = {"Accept": "application/json"}
HX = {"HX-Request": "true", "HX-Current-URL": "https://testserver/settings/security"}
CREDENTIAL: dict[str, Any] = {"id": "abc", "rawId": "abc", "type": "public-key", "response": {}}
STALE_URL = "/auth/reauth?next=%2Fsettings%2Fsecurity"
PAGE = {"Referer": "https://testserver/settings/security"}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'web.sqlite').as_posix()}",
        session_reauth_window_minutes=WINDOW_MINUTES,
        rate_limit_login_per_minute=2,
        rate_limit_login_per_hour=50,
        rate_limit_login_ip_per_hour=50,
        rate_limit_passkey_login_per_minute=2,
        rate_limit_passkey_login_per_hour=50,
        rate_limit_register_per_minute=4,
        rate_limit_register_per_hour=50,
        rate_limit_reauth_per_minute=3,
        rate_limit_reauth_per_hour=50,
    )


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _go_stale(client: TestClient) -> None:
    """Move the re-auth clock past the window so the login counts as stale."""
    later = datetime.now(UTC) + timedelta(minutes=WINDOW_MINUTES + 1)
    client.app.state.reauth_clock = _Clock(later)  # type: ignore[attr-defined]


def _set_cookies(resp: Any, name: str) -> list[str]:
    return [h for h in resp.headers.get_list("set-cookie") if h.startswith(f"{name}=")]


def _location(resp: Any) -> str:
    return str(resp.headers["location"])


def _is_login_redirect(resp: Any) -> bool:
    return resp.status_code == 302 and _location(resp).startswith("/auth/login")


@pytest.fixture
def login_user(db: sqlite3.Connection) -> int:
    return seed_login_user(db)


def _post_login(
    c: TestClient, email: str, password: str, next_path: str = "/today", **kw: Any
) -> Any:
    return c.post(
        "/auth/login",
        data={"email": email, "password": password, "next": next_path},
        follow_redirects=False,
        **kw,
    )


# ---------------------------------------------------------------------------
# GET /auth/login, POST /auth/login
# ---------------------------------------------------------------------------


@covers("GET /auth/login")
def test_login_form_is_public_and_redirects_signed_in_users(
    anon_client: TestClient, client: TestClient
) -> None:
    r = anon_client.get("/auth/login")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    r = client.get("/auth/login?next=/ledger", follow_redirects=False)
    assert (r.status_code, _location(r)) == (303, "/ledger")
    # An open redirect target is neutralised to the landing page.
    r = client.get("/auth/login?next=//evil.example", follow_redirects=False)
    assert (r.status_code, _location(r)) == (303, "/today")


@covers("POST /auth/login")
def test_password_login_success_sets_session_and_audits(
    anon_client: TestClient, login_user: int, db: sqlite3.Connection
) -> None:
    r = _post_login(anon_client, TEST_EMAIL, TEST_PASSWORD, "/plan")
    assert (r.status_code, _location(r)) == (303, "/plan")
    cookie = _set_cookies(r, SESSION_COOKIE_NAME)
    assert len(cookie) == 1
    assert {"httponly", "secure", "samesite=lax"} <= set(
        cookie[0].lower().replace(" ", "").split(";")
    )
    token = cookie[0].split(";", 1)[0].split("=", 1)[1]
    live = sessions_repo.get_session(db, token)
    assert live is not None
    assert live.user_id == login_user
    assert audit_count(db, "session", "create") == 1
    assert anon_client.get("/accounts", follow_redirects=False).status_code == 200


@covers("POST /auth/login")
@pytest.mark.parametrize(
    ("email", "password"),
    [(TEST_EMAIL, WRONG), ("nobody@example.test", TEST_PASSWORD), ("", ""), (TEST_EMAIL, "")],
)
def test_password_login_failure_is_generic_401_without_session(
    anon_client: TestClient, login_user: int, db: sqlite3.Connection, email: str, password: str
) -> None:
    r = _post_login(anon_client, email, password)
    assert r.status_code == 401
    assert not _set_cookies(r, SESSION_COOKIE_NAME)
    assert audit_count(db, "session", "create") == 0


@covers("POST /auth/login")
def test_password_login_unsafe_next_falls_back_to_today(
    anon_client: TestClient, login_user: int
) -> None:
    r = _post_login(anon_client, TEST_EMAIL, TEST_PASSWORD, "https://evil.example/")
    assert (r.status_code, _location(r)) == (303, "/today")


@covers("POST /auth/login")
def test_password_login_requires_csrf_token(
    anon_client: TestClient, login_user: int, db: sqlite3.Connection
) -> None:
    r = _post_login(anon_client, TEST_EMAIL, TEST_PASSWORD, headers={"X-CSRF-Token": "forged"})
    assert r.status_code == 403
    assert not _set_cookies(r, SESSION_COOKIE_NAME)
    assert audit_count(db, "session", "create") == 0


@covers("POST /auth/login")
def test_password_login_is_rate_limited_with_retry_after(
    anon_client: TestClient, login_user: int, db: sqlite3.Connection
) -> None:
    assert [_post_login(anon_client, TEST_EMAIL, WRONG).status_code for _ in range(2)] == [401, 401]
    html = _post_login(anon_client, TEST_EMAIL, TEST_PASSWORD)
    assert html.status_code == 429
    assert int(html.headers["retry-after"]) >= 1
    assert not _set_cookies(html, SESSION_COOKIE_NAME)
    as_json = _post_login(anon_client, TEST_EMAIL, TEST_PASSWORD, headers=JSON)
    assert (as_json.status_code, as_json.json()) == (429, {"error": "rate_limited"})
    assert "retry-after" in as_json.headers
    as_hx = _post_login(anon_client, TEST_EMAIL, TEST_PASSWORD, headers=HX)
    assert as_hx.status_code == 429
    assert as_hx.json() == {"error": "rate_limited"}
    assert auth_events(db, "rate_limited")[-1]["scope"].startswith("login")


# ---------------------------------------------------------------------------
# POST /auth/login/begin, POST /auth/login/finish
# ---------------------------------------------------------------------------


@covers("POST /auth/login/begin")
def test_passkey_login_begin_issues_options_and_challenge_cookie(
    anon_client: TestClient,
) -> None:
    r = anon_client.post("/auth/login/begin")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["userVerification"] == "required"
    cookie = _set_cookies(r, CHALLENGE_COOKIE_NAME)
    assert len(cookie) == 1
    assert "httponly" in cookie[0].lower()


@covers("POST /auth/login/begin", "POST /auth/login/finish")
def test_passkey_login_requires_csrf_token(anon_client: TestClient) -> None:
    bad = {"X-CSRF-Token": "forged"}
    assert anon_client.post("/auth/login/begin", headers=bad).status_code == 403
    assert anon_client.post("/auth/login/finish", headers=bad, json=CREDENTIAL).status_code == 403


@covers("POST /auth/login/finish")
def test_passkey_login_finish_failures_are_generic_json(anon_client: TestClient) -> None:
    # No challenge cookie at all: never verifies, never sets a session.
    r = anon_client.post("/auth/login/finish", json=CREDENTIAL)
    assert (r.status_code, r.json()) == (401, {"error": "login_failed"})
    assert not _set_cookies(r, SESSION_COOKIE_NAME)
    # A garbage assertion against a real challenge fails the same way.
    anon_client.post("/auth/login/begin")
    r = anon_client.post("/auth/login/finish", json=CREDENTIAL)
    assert (r.status_code, r.json()) == (401, {"error": "login_failed"})
    assert not _set_cookies(r, SESSION_COOKIE_NAME)
    # Challenge cookie is consumed on every outcome.
    assert "max-age=0" in _set_cookies(r, CHALLENGE_COOKIE_NAME)[0].lower()


@covers("POST /auth/login/finish")
@pytest.mark.parametrize("body", ["not json", "[1, 2]"])
def test_passkey_login_finish_rejects_non_object_body(anon_client: TestClient, body: str) -> None:
    r = anon_client.post(
        "/auth/login/finish", content=body, headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 400
    assert r.json() == {"detail": "invalid_json"}


@covers("POST /auth/login/finish")
def test_passkey_login_finish_is_rate_limited(
    anon_client: TestClient, db: sqlite3.Connection
) -> None:
    codes = [anon_client.post("/auth/login/finish", json=CREDENTIAL).status_code for _ in range(3)]
    assert codes == [401, 401, 429]
    r = anon_client.post("/auth/login/finish", json=CREDENTIAL)
    assert (r.status_code, r.json()) == (429, {"error": "rate_limited"})
    assert int(r.headers["retry-after"]) >= 1
    assert auth_events(db, "rate_limited")[-1]["scope"].startswith("passkey_login")


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


@covers("POST /auth/logout")
def test_logout_revokes_session_clears_cookie_and_audits(
    client: TestClient, session_cookie: tuple[str, str], db: sqlite3.Connection
) -> None:
    r = client.post("/auth/logout", follow_redirects=False)
    assert (r.status_code, _location(r)) == (303, "/auth/login")
    assert "max-age=0" in _set_cookies(r, SESSION_COOKIE_NAME)[0].lower()
    assert r.headers["clear-site-data"] == '"cache", "storage"'
    assert sessions_repo.get_session(db, session_cookie[1]) is None
    assert audit_count(db, "session", "delete") == 1
    assert _is_login_redirect(client.get("/accounts", follow_redirects=False))


@covers("POST /auth/logout")
def test_logout_requires_session_and_csrf(
    anon_client: TestClient,
    client: TestClient,
    session_cookie: tuple[str, str],
    db: sqlite3.Connection,
) -> None:
    assert _is_login_redirect(anon_client.post("/auth/logout", follow_redirects=False))
    forged = client.post("/auth/logout", headers={"X-CSRF-Token": "forged"}, follow_redirects=False)
    assert forged.status_code == 403
    assert sessions_repo.get_session(db, session_cookie[1]) is not None


# ---------------------------------------------------------------------------
# GET /auth/register, GET /auth/sessions (legacy redirects)
# ---------------------------------------------------------------------------


@covers("GET /auth/register")
def test_register_form_redirects_to_settings_security(
    client: TestClient, anon_client: TestClient
) -> None:
    r = client.get("/auth/register", follow_redirects=False)
    assert (r.status_code, _location(r)) == (303, "/settings/security#passkeys")
    assert _is_login_redirect(anon_client.get("/auth/register", follow_redirects=False))


@covers("GET /auth/sessions")
def test_sessions_page_redirects_to_settings_security(
    client: TestClient, anon_client: TestClient
) -> None:
    r = client.get("/auth/sessions", follow_redirects=False)
    assert (r.status_code, _location(r)) == (303, "/settings/security#sessions")
    assert _is_login_redirect(anon_client.get("/auth/sessions", follow_redirects=False))


# ---------------------------------------------------------------------------
# POST /auth/register/begin, POST /auth/register/finish
# ---------------------------------------------------------------------------


@covers("POST /auth/register/begin")
def test_register_begin_issues_creation_options_for_fresh_session(client: TestClient) -> None:
    r = client.post("/auth/register/begin")
    assert r.status_code == 200
    assert r.json()["authenticatorSelection"]["residentKey"] == "required"
    assert len(_set_cookies(r, CHALLENGE_COOKIE_NAME)) == 1


@covers("POST /auth/register/begin", "POST /auth/register/finish")
def test_register_requires_session_and_csrf(anon_client: TestClient, client: TestClient) -> None:
    for path in ("/auth/register/begin", "/auth/register/finish"):
        anon = anon_client.post(path, headers=JSON)
        assert (anon.status_code, anon.json()) == (401, {"error": "unauthorized"})
        forged = client.post(path, headers={"X-CSRF-Token": "forged"}, json={})
        assert forged.status_code == 403


@covers("POST /auth/register/begin", "POST /auth/register/finish")
def test_register_requires_recent_auth_in_each_response_shape(client: TestClient) -> None:
    _go_stale(client)
    for path in ("/auth/register/begin", "/auth/register/finish"):
        html = client.post(
            path, json={"label": "x", "credential": {}}, headers=PAGE, follow_redirects=False
        )
        assert (html.status_code, _location(html)) == (303, STALE_URL)
        hx = client.post(path, json={"label": "x", "credential": {}}, headers=HX)
        assert hx.status_code == 403
        assert hx.headers["hx-redirect"] == STALE_URL
        as_json = client.post(path, json={"label": "x", "credential": {}}, headers={**JSON, **PAGE})
        assert as_json.status_code == 403
        assert as_json.json()["error"] == "reauth_required"
        assert as_json.json()["redirect"] == STALE_URL


@covers("POST /auth/register/finish")
def test_register_finish_rejects_bad_input_without_storing_a_passkey(
    client: TestClient, db: sqlite3.Connection
) -> None:
    # No challenge issued yet.
    r = client.post("/auth/register/finish", json={"label": "x", "credential": CREDENTIAL})
    assert (r.status_code, r.json()) == (400, {"error": "challenge_expired"})
    client.post("/auth/register/begin")
    r = client.post("/auth/register/finish", json={"label": "x"})
    assert (r.status_code, r.json()) == (400, {"error": "invalid_response"})
    client.post("/auth/register/begin")
    r = client.post("/auth/register/finish", json={"label": "x", "credential": {"id": "nope"}})
    assert (r.status_code, r.json()) == (400, {"error": "invalid_response"})
    assert not webauthn_repo.list_credentials(db, 1)
    client.post("/auth/register/begin")
    bad = client.post(
        "/auth/register/finish", content="nope", headers={"Content-Type": "application/json"}
    )
    assert (bad.status_code, bad.json()) == (400, {"detail": "invalid_json"})


@covers("POST /auth/register/finish")
def test_register_finish_is_rate_limited_per_user(
    client: TestClient, db: sqlite3.Connection
) -> None:
    # A fixed instant keeps the five posts inside one rate-limit window on a loaded machine.
    fixed = datetime(2026, 11, 3, 12, 0, 10, tzinfo=UTC)
    client.app.state.rate_limit_clock = lambda: fixed  # type: ignore[attr-defined]
    codes = [
        client.post(
            "/auth/register/finish", json={"label": "x", "credential": CREDENTIAL}
        ).status_code
        for _ in range(4)
    ]
    assert codes == [400] * 4
    r = client.post("/auth/register/finish", json={"label": "x", "credential": CREDENTIAL})
    assert (r.status_code, r.json()) == (429, {"error": "rate_limited"})
    assert int(r.headers["retry-after"]) >= 1
    assert auth_events(db, "rate_limited")[-1]["scope"] == "passkey_register"


# ---------------------------------------------------------------------------
# Revoke one session by handle
# ---------------------------------------------------------------------------


@covers("POST /auth/sessions/{handle}/revoke")
def test_revoke_other_session_redirects_to_security_and_audits(
    client: TestClient, db: sqlite3.Connection
) -> None:
    other = sessions_repo.create_session(db, 1, ip=None, user_agent="other")
    r = client.post(f"/auth/sessions/{other.session.handle}/revoke", follow_redirects=False)
    assert (r.status_code, _location(r)) == (303, "/settings/security#sessions")
    assert sessions_repo.get_session(db, other.token) is None
    assert audit_count(db, "session", "delete") == 1


@covers("POST /auth/sessions/{handle}/revoke")
def test_revoke_current_session_signs_out(
    client: TestClient, session_cookie: tuple[str, str], db: sqlite3.Connection
) -> None:
    handle = sessions_repo.session_handle(session_cookie[1])
    r = client.post(f"/auth/sessions/{handle}/revoke", follow_redirects=False)
    assert (r.status_code, _location(r)) == (303, "/auth/login")
    assert "max-age=0" in _set_cookies(r, SESSION_COOKIE_NAME)[0].lower()
    assert r.headers["clear-site-data"] == '"cache", "storage"'
    assert sessions_repo.get_session(db, session_cookie[1]) is None


@covers("POST /auth/sessions/{handle}/revoke")
def test_revoke_session_rejects_unknown_foreign_and_malformed_handles(
    client: TestClient, db: sqlite3.Connection
) -> None:
    foreign_user = seed_login_user(db, user_id=2, email="mallory@example.test")
    foreign = sessions_repo.create_session(db, foreign_user, ip=None, user_agent="x")
    for handle in ("0" * 16, foreign.session.handle, "not-a-handle"):
        r = client.post(f"/auth/sessions/{handle}/revoke", follow_redirects=False)
        assert r.status_code == 404, handle
    assert sessions_repo.get_session(db, foreign.token) is not None


@covers("POST /auth/sessions/{handle}/revoke")
def test_revoke_other_session_requires_session_csrf_and_recent_auth(
    client: TestClient, anon_client: TestClient, db: sqlite3.Connection
) -> None:
    other = sessions_repo.create_session(db, 1, ip=None, user_agent="other")
    path = f"/auth/sessions/{other.session.handle}/revoke"
    assert _is_login_redirect(anon_client.post(path, follow_redirects=False))
    assert client.post(path, headers={"X-CSRF-Token": "forged"}).status_code == 403
    _go_stale(client)
    stale = client.post(path, headers=PAGE, follow_redirects=False)
    assert (stale.status_code, _location(stale)) == (303, STALE_URL)
    assert sessions_repo.get_session(db, other.token) is not None


# ---------------------------------------------------------------------------
# Revoke one passkey by id
# ---------------------------------------------------------------------------


def _passkey(db: sqlite3.Connection, user_id: int, raw: bytes) -> int:
    return webauthn_repo.create_credential(
        db, user_id=user_id, credential_id=raw, public_key=b"pk", sign_count=0, label="k"
    ).id


@covers("POST /auth/passkeys/{credential_id}/revoke")
def test_revoke_passkey_soft_deletes_own_credential_and_audits(
    client: TestClient, db: sqlite3.Connection
) -> None:
    mine = _passkey(db, 1, b"mine")
    before = audit_count(db, webauthn_repo.ENTITY_TYPE, "delete")
    r = client.post(f"/auth/passkeys/{mine}/revoke", follow_redirects=False)
    assert (r.status_code, _location(r)) == (303, "/settings/security#passkeys")
    assert not webauthn_repo.list_credentials(db, 1)
    assert audit_count(db, webauthn_repo.ENTITY_TYPE, "delete") == before + 1


@covers("POST /auth/passkeys/{credential_id}/revoke")
def test_revoke_passkey_rejects_foreign_unknown_and_malformed_ids(
    client: TestClient, db: sqlite3.Connection
) -> None:
    other = seed_login_user(db, user_id=2, email="mallory@example.test")
    theirs = _passkey(db, other, b"theirs")
    assert client.post(f"/auth/passkeys/{theirs}/revoke").status_code == 404
    assert client.post("/auth/passkeys/99999/revoke").status_code == 404
    assert client.post("/auth/passkeys/abc/revoke").status_code == 422
    assert len(webauthn_repo.list_credentials(db, other)) == 1


@covers("POST /auth/passkeys/{credential_id}/revoke")
def test_revoke_passkey_requires_session_csrf_and_recent_auth(
    client: TestClient, anon_client: TestClient, db: sqlite3.Connection
) -> None:
    mine = _passkey(db, 1, b"mine")
    path = f"/auth/passkeys/{mine}/revoke"
    assert _is_login_redirect(anon_client.post(path, follow_redirects=False))
    assert client.post(path, headers={"X-CSRF-Token": "forged"}).status_code == 403
    _go_stale(client)
    stale = client.post(path, headers=PAGE, follow_redirects=False)
    assert (stale.status_code, _location(stale)) == (303, STALE_URL)
    assert len(webauthn_repo.list_credentials(db, 1)) == 1


# ---------------------------------------------------------------------------
# GET/POST /auth/reauth, POST /auth/reauth/begin, POST /auth/reauth/finish
# ---------------------------------------------------------------------------


@covers("GET /auth/reauth")
def test_reauth_form_requires_a_session(client: TestClient, anon_client: TestClient) -> None:
    r = client.get("/auth/reauth?next=/settings/users")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert _is_login_redirect(anon_client.get("/auth/reauth", follow_redirects=False))


@covers("POST /auth/reauth")
def test_reauth_password_success_rotates_session_and_audits(
    client: TestClient, session_cookie: tuple[str, str], db: sqlite3.Connection
) -> None:
    _go_stale(client)
    r = client.post(
        "/auth/reauth",
        data={"password": TEST_PASSWORD, "next": "/settings/users"},
        follow_redirects=False,
    )
    assert (r.status_code, _location(r)) == (303, "/settings/users")
    rotated = _set_cookies(r, SESSION_COOKIE_NAME)[0].split(";", 1)[0].split("=", 1)[1]
    assert rotated != session_cookie[1]
    assert sessions_repo.get_session(db, session_cookie[1]) is None
    assert auth_events(db, "reauth")[-1]["method"] == "password"


@covers("POST /auth/reauth")
def test_reauth_password_failure_is_401_audited_and_keeps_session(
    client: TestClient, session_cookie: tuple[str, str], db: sqlite3.Connection
) -> None:
    r = client.post("/auth/reauth", data={"password": WRONG, "next": "/today"})
    assert r.status_code == 401
    # The session is not rotated: any re-issued cookie carries the same token.
    assert all(f"={session_cookie[1]};" in c for c in _set_cookies(r, SESSION_COOKIE_NAME))
    assert sessions_repo.get_session(db, session_cookie[1]) is not None
    failed = auth_events(db, "reauth_failed")[-1]
    assert (failed["method"], failed["reason"]) == ("password", "bad_password")


@covers("POST /auth/reauth")
def test_reauth_password_never_redirects_back_into_reauth_or_offsite(client: TestClient) -> None:
    for target in ("/auth/reauth?next=/x", "https://evil.example/"):
        r = client.post(
            "/auth/reauth", data={"password": TEST_PASSWORD, "next": target}, follow_redirects=False
        )
        assert (r.status_code, _location(r)) == (303, "/today")


@covers("POST /auth/reauth")
def test_reauth_password_requires_session_and_csrf(
    client: TestClient, anon_client: TestClient
) -> None:
    assert _is_login_redirect(
        anon_client.post("/auth/reauth", data={"password": TEST_PASSWORD}, follow_redirects=False)
    )
    forged = client.post(
        "/auth/reauth", data={"password": TEST_PASSWORD}, headers={"X-CSRF-Token": "forged"}
    )
    assert forged.status_code == 403


@covers("POST /auth/reauth")
def test_reauth_password_is_rate_limited_in_each_response_shape(
    client: TestClient, db: sqlite3.Connection
) -> None:
    codes = [client.post("/auth/reauth", data={"password": WRONG}).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
    html = client.post("/auth/reauth", data={"password": TEST_PASSWORD}, follow_redirects=False)
    assert html.status_code == 429
    assert int(html.headers["retry-after"]) >= 1
    as_json = client.post("/auth/reauth", data={"password": WRONG}, headers=JSON)
    assert (as_json.status_code, as_json.json()) == (429, {"error": "rate_limited"})
    as_hx = client.post("/auth/reauth", data={"password": WRONG}, headers=HX)
    assert (as_hx.status_code, as_hx.json()) == (429, {"error": "rate_limited"})
    assert auth_events(db, "rate_limited")[-1]["scope"] == "reauth"


@covers("POST /auth/reauth/begin")
def test_reauth_begin_needs_a_passkey_and_a_session(
    client: TestClient, anon_client: TestClient, db: sqlite3.Connection
) -> None:
    r = client.post("/auth/reauth/begin")
    assert (r.status_code, r.json()) == (400, {"error": "no_passkeys"})
    _passkey(db, 1, b"mine")
    r = client.post("/auth/reauth/begin")
    assert r.status_code == 200
    assert r.json()["allowCredentials"]
    assert len(_set_cookies(r, CHALLENGE_COOKIE_NAME)) == 1
    anon = anon_client.post("/auth/reauth/begin", headers=JSON)
    assert (anon.status_code, anon.json()) == (401, {"error": "unauthorized"})
    assert client.post("/auth/reauth/begin", headers={"X-CSRF-Token": "forged"}).status_code == 403


@covers("POST /auth/reauth/finish")
def test_reauth_finish_failures_are_json_and_consume_the_challenge(
    client: TestClient, db: sqlite3.Connection
) -> None:
    r = client.post("/auth/reauth/finish", json=CREDENTIAL)  # no challenge cookie
    assert (r.status_code, r.json()) == (401, {"error": "reauth_failed"})
    bad = client.post(
        "/auth/reauth/finish", content="nope", headers={"Content-Type": "application/json"}
    )
    assert (bad.status_code, bad.json()) == (400, {"detail": "invalid_json"})
    _passkey(db, 1, b"mine")
    client.post("/auth/reauth/begin")
    r = client.post("/auth/reauth/finish", json=CREDENTIAL)
    assert (r.status_code, r.json()) == (401, {"error": "reauth_failed"})
    assert "max-age=0" in _set_cookies(r, CHALLENGE_COOKIE_NAME)[0].lower()
    assert not auth_events(db, "reauth")


@covers("POST /auth/reauth/finish")
def test_reauth_finish_requires_session_csrf_and_is_rate_limited(
    client: TestClient, anon_client: TestClient
) -> None:
    anon = anon_client.post("/auth/reauth/finish", headers=JSON, json=CREDENTIAL)
    assert anon.status_code == 401
    forged = client.post("/auth/reauth/finish", headers={"X-CSRF-Token": "forged"}, json=CREDENTIAL)
    assert forged.status_code == 403
    codes = [client.post("/auth/reauth/finish", json=CREDENTIAL).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
    last = client.post("/auth/reauth/finish", json=CREDENTIAL)
    assert last.json() == {"error": "rate_limited"}
    assert int(last.headers["retry-after"]) >= 1
