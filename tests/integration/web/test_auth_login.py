"""T-D02b — password login: happy path, generic failure, cookie flags, ``next``."""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest
from fastapi.testclient import TestClient

from budget_planner.repositories import sessions as sessions_repo
from budget_planner.web.auth_cookies import SESSION_COOKIE_NAME, safe_next
from budget_planner.web.routers.auth import GENERIC_LOGIN_ERROR
from tests.auth_support import TEST_EMAIL, TEST_PASSWORD, seed_login_user

pytestmark = pytest.mark.integration

_LIFETIME_SECONDS = 14 * 86_400


@pytest.fixture
def login_user(conn: sqlite3.Connection) -> int:
    return seed_login_user(conn)


def _login(client: TestClient, email: str, password: str, next_path: str = "/") -> Any:
    return client.post(
        "/auth/login",
        data={"email": email, "password": password, "next": next_path},
        follow_redirects=False,
    )


def _set_cookie_headers(resp: Any) -> list[str]:
    return list(resp.headers.get_list("set-cookie"))


def _session_set_cookie(resp: Any) -> str:
    matches = [h for h in _set_cookie_headers(resp) if h.startswith(f"{SESSION_COOKIE_NAME}=")]
    assert len(matches) == 1, _set_cookie_headers(resp)
    return matches[0]


def test_login_page_renders_without_app_nav(anon_client: TestClient) -> None:
    r = anon_client.get("/auth/login")
    assert r.status_code == 200
    assert 'name="_csrf_token"' in r.text
    assert "data-passkey-login" in r.text
    assert 'aria-label="Primary navigation"' not in r.text
    assert "/static/js/passkeys.js" in r.text
    assert "<script>" not in r.text  # no inline script (CSP)


def test_password_login_happy_path_sets_session_cookie(
    anon_client: TestClient, login_user: int, conn: sqlite3.Connection
) -> None:
    r = _login(anon_client, TEST_EMAIL, TEST_PASSWORD)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    cookie = _session_set_cookie(r)
    lowered = cookie.lower()
    assert "httponly" in lowered
    assert "secure" in lowered
    assert "samesite=lax" in lowered
    assert "path=/" in lowered
    assert "domain" not in lowered
    assert f"max-age={_LIFETIME_SECONDS}" in lowered
    session_id = cookie.split(";", 1)[0].split("=", 1)[1]
    live = sessions_repo.get_session(conn, session_id)
    assert live is not None
    assert live.user_id == login_user
    # The session works for a protected page.
    assert anon_client.get("/accounts", follow_redirects=False).status_code == 200


def test_login_email_is_case_insensitive(anon_client: TestClient, login_user: int) -> None:
    r = _login(anon_client, TEST_EMAIL.upper(), TEST_PASSWORD)
    assert r.status_code == 303


@pytest.mark.parametrize(
    ("email", "password"),
    [
        (TEST_EMAIL, "wrong-password"),
        ("nobody@example.test", TEST_PASSWORD),
        ("", ""),
        (TEST_EMAIL, ""),
    ],
)
def test_login_failure_is_generic(
    anon_client: TestClient, login_user: int, email: str, password: str
) -> None:
    r = _login(anon_client, email, password)
    assert r.status_code == 401
    assert GENERIC_LOGIN_ERROR.replace("'", "&#39;") in r.text
    assert not any(h.startswith(f"{SESSION_COOKIE_NAME}=") for h in _set_cookie_headers(r))


def test_wrong_password_and_unknown_email_render_identically(
    anon_client: TestClient, login_user: int
) -> None:
    same_email = "x@example.test"
    wrong_pw = _login(anon_client, TEST_EMAIL, "nope")
    unknown = _login(anon_client, same_email, "nope")
    assert wrong_pw.status_code == unknown.status_code == 401
    # Only the echoed email differs between the two bodies.
    assert wrong_pw.text.replace(TEST_EMAIL, "E") == unknown.text.replace(same_email, "E")


def test_login_redirects_to_safe_next(anon_client: TestClient, login_user: int) -> None:
    r = _login(anon_client, TEST_EMAIL, TEST_PASSWORD, next_path="/ledger?tab=planned")
    assert r.status_code == 303
    assert r.headers["location"] == "/ledger?tab=planned"


@pytest.mark.parametrize(
    "evil",
    [
        "https://evil.example/",
        "//evil.example/",
        "/\\evil.example",
        "/ok\\..",
        "javascript:alert(1)",
        "evil",
        "/auth/login",
        "/auth/login/finish",
        "/x\r\nSet-Cookie: a=b",
    ],
)
def test_login_rejects_open_redirect(anon_client: TestClient, login_user: int, evil: str) -> None:
    r = _login(anon_client, TEST_EMAIL, TEST_PASSWORD, next_path=evil)
    assert r.status_code == 303
    assert r.headers["location"] == "/"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "/"),
        ("", "/"),
        ("/today", "/today"),
        ("/plan?tab=year#x", "/plan?tab=year#x"),
        ("//evil", "/"),
        ("http://evil/", "/"),
        ("/\x7f", "/"),
        ("/auth/login?next=/x", "/"),
        ("/auth/sessions", "/auth/sessions"),
    ],
)
def test_safe_next(value: str | None, expected: str) -> None:
    assert safe_next(value) == expected


def test_login_page_redirects_when_already_signed_in(client: TestClient) -> None:
    r = client.get("/auth/login?next=/ledger", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/ledger"


def test_login_page_keeps_next_in_form(anon_client: TestClient) -> None:
    r = anon_client.get("/auth/login?next=%2Fplan")
    assert 'name="next" value="/plan"' in r.text


def test_login_revokes_previously_presented_session(
    client: TestClient, session_cookie: tuple[str, str], conn: sqlite3.Connection
) -> None:
    _name, old_session = session_cookie
    r = _login(client, TEST_EMAIL, TEST_PASSWORD)
    assert r.status_code == 303
    assert sessions_repo.get_session(conn, old_session) is None
    new_cookie = _session_set_cookie(r)
    assert old_session not in new_cookie


def test_login_writes_audit_rows(
    anon_client: TestClient, login_user: int, conn: sqlite3.Connection
) -> None:
    _login(anon_client, TEST_EMAIL, "bad")
    _login(anon_client, TEST_EMAIL, TEST_PASSWORD)
    rows = conn.execute(
        "SELECT entity_type, ip, user_agent, session_id FROM audit_log "
        "WHERE entity_type IN ('auth_event', 'session') ORDER BY id"
    ).fetchall()
    assert [r["entity_type"] for r in rows] == ["auth_event", "session"]
    assert all(r["ip"] for r in rows)
