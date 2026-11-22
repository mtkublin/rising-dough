"""T-Q289 — CSRF token bound to the session (ADR-0065 amendment 2026-11-22)."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from budget_planner.adapters.entropy import SecretsTokenSource
from budget_planner.config import Settings
from budget_planner.web.app import create_app
from budget_planner.web.csrf_token import mint_token, verify_token
from budget_planner.web.middleware.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from tests.auth_support import TEST_EMAIL, TEST_PASSWORD, issue_session, seed_login_user

pytestmark = pytest.mark.integration

SECRET = "s" * 32  # pragma: allowlist secret
SESSION_COOKIE = "__Host-session"
TOKENS = SecretsTokenSource()


@pytest.fixture
def app_client(_migrated: Settings) -> TestClient:
    app = create_app(settings=_migrated)

    @app.post("/_test/echo", response_class=PlainTextResponse)
    def _echo() -> PlainTextResponse:
        return PlainTextResponse("ok")

    return TestClient(app, base_url="https://testserver")


def _signed_in(c: TestClient, session_id: str) -> str:
    c.cookies.clear()
    c.cookies.set(SESSION_COOKIE, session_id)
    assert c.get("/health").status_code == 200
    return c.cookies[CSRF_COOKIE_NAME]


def test_token_binding_unit() -> None:
    token = mint_token(SECRET, "sess-a", TOKENS)
    assert verify_token(SECRET, token, "sess-a")
    assert not verify_token(SECRET, token, "sess-b")
    assert not verify_token(SECRET, token, None)
    assert not verify_token("t" * 32, token, "sess-a")
    assert not verify_token(SECRET, "", "sess-a")
    pre = mint_token(SECRET, None, TOKENS)
    assert verify_token(SECRET, pre, None)
    assert not verify_token(SECRET, pre, "sess-a")


def test_token_from_session_a_refused_on_session_b(
    app_client: TestClient, conn: sqlite3.Connection
) -> None:
    seed_login_user(conn)
    a, b = issue_session(conn), issue_session(conn)
    token_a = _signed_in(app_client, a)
    ok = app_client.post("/_test/echo", headers={CSRF_HEADER_NAME: token_a})
    assert (ok.status_code, ok.text) == (200, "ok")
    app_client.cookies.clear()
    app_client.cookies.set(SESSION_COOKIE, b)
    app_client.cookies.set(CSRF_COOKIE_NAME, token_a)
    r = app_client.post("/_test/echo", headers={CSRF_HEADER_NAME: token_a})
    assert (r.status_code, r.json()) == (403, {"detail": "invalid_csrf"})


def test_logout_rotates_and_old_token_refused(
    app_client: TestClient, _migrated: Settings, conn: sqlite3.Connection
) -> None:
    seed_login_user(conn)
    old = _signed_in(app_client, issue_session(conn))
    r = app_client.post("/auth/logout", headers={CSRF_HEADER_NAME: old}, follow_redirects=False)
    assert r.status_code == 303
    new = app_client.cookies[CSRF_COOKIE_NAME]
    assert new != old
    assert verify_token(_migrated.resolve().cookie_secret, new, None)
    replay = app_client.post(
        "/auth/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={CSRF_HEADER_NAME: old},
        follow_redirects=False,
    )
    assert replay.status_code == 403


def test_pre_session_login_works_and_login_rotates(
    app_client: TestClient, _migrated: Settings, conn: sqlite3.Connection
) -> None:
    seed_login_user(conn)
    app_client.get("/auth/login")
    pre = app_client.cookies[CSRF_COOKIE_NAME]
    secret = _migrated.resolve().cookie_secret
    assert verify_token(secret, pre, None)
    r = app_client.post(
        "/auth/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={CSRF_HEADER_NAME: pre},
        follow_redirects=False,
    )
    assert r.status_code == 303
    post = app_client.cookies[CSRF_COOKIE_NAME]
    assert post != pre
    assert verify_token(secret, post, app_client.cookies[SESSION_COOKIE])
    stale = app_client.post("/_test/echo", headers={CSRF_HEADER_NAME: pre})
    assert stale.status_code == 403
    fresh = app_client.post("/_test/echo", headers={CSRF_HEADER_NAME: post})
    assert fresh.status_code == 200


def test_pre_session_token_refused_for_signed_in_session(
    app_client: TestClient, _migrated: Settings, conn: sqlite3.Connection
) -> None:
    seed_login_user(conn)
    pre = mint_token(_migrated.resolve().cookie_secret, None, TOKENS)
    app_client.cookies.set(SESSION_COOKIE, issue_session(conn))
    app_client.cookies.set(CSRF_COOKIE_NAME, pre)
    r = app_client.post("/_test/echo", headers={CSRF_HEADER_NAME: pre})
    assert r.status_code == 403


def test_empty_csrf_cookie_is_reminted(app_client: TestClient) -> None:
    app_client.cookies.set(CSRF_COOKIE_NAME, "")
    r = app_client.get("/auth/login")
    assert CSRF_COOKIE_NAME in r.headers.get("set-cookie", "")
    minted = r.headers["set-cookie"].split(f"{CSRF_COOKIE_NAME}=", 1)[1].split(";", 1)[0]
    assert len(minted) == 65


@pytest.mark.parametrize("bad", ["x" * 65, "bad id with spaces", "a/b", ""])
def test_unsafe_request_id_is_replaced(app_client: TestClient, bad: str) -> None:
    r = app_client.get("/health", headers={"X-Request-Id": bad})
    echoed = r.headers["x-request-id"]
    assert echoed != bad
    assert len(echoed) == 12


def test_static_asset_never_touches_the_csrf_cookie(
    app_client: TestClient, conn: sqlite3.Connection
) -> None:
    seed_login_user(conn)
    token = _signed_in(app_client, issue_session(conn))
    r = app_client.get("/static/csrf.js")
    assert r.status_code == 200
    assert CSRF_COOKIE_NAME not in r.headers.get("set-cookie", "")
    assert app_client.cookies[CSRF_COOKIE_NAME] == token


def test_rotation_response_echoes_the_fresh_token_header(
    app_client: TestClient, conn: sqlite3.Connection
) -> None:
    seed_login_user(conn)
    old = _signed_in(app_client, issue_session(conn))
    r = app_client.post("/auth/logout", headers={CSRF_HEADER_NAME: old}, follow_redirects=False)
    echoed = r.headers[CSRF_HEADER_NAME]
    assert echoed == app_client.cookies[CSRF_COOKIE_NAME]
    assert echoed != old
