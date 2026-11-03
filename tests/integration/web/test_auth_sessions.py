"""T-D02b — ``/auth/sessions``: list + revoke own sessions and passkeys only."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from budget_planner.repositories import sessions as sessions_repo, webauthn as webauthn_repo
from budget_planner.repositories.sessions import session_handle
from budget_planner.web.auth_cookies import SESSION_COOKIE_NAME
from tests.auth_support import issue_session, seed_login_user

pytestmark = pytest.mark.integration


@pytest.fixture
def other_user(conn: sqlite3.Connection) -> int:
    return seed_login_user(conn, user_id=2, email="mallory@example.test")


def _passkey(conn: sqlite3.Connection, user_id: int, label: str, raw: bytes) -> int:
    return webauthn_repo.create_credential(
        conn,
        user_id=user_id,
        credential_id=raw,
        public_key=b"pk",
        sign_count=0,
        label=label,
    ).id


def test_sessions_page_lists_own_sessions_by_handle(
    client: TestClient, session_cookie: tuple[str, str], conn: sqlite3.Connection, other_user: int
) -> None:
    second = issue_session(conn)
    foreign = issue_session(conn, user_id=other_user)
    r = client.get("/auth/sessions")
    assert r.status_code == 200
    html = r.text
    current = session_cookie[1]
    assert session_handle(current) in html
    assert session_handle(second) in html
    assert session_handle(foreign) not in html
    for raw in (current, second, foreign):
        assert raw not in html
    assert "This device" in html
    assert html.count("This device") == 1


def test_sessions_page_lists_own_passkeys(
    client: TestClient, conn: sqlite3.Connection, other_user: int
) -> None:
    _passkey(conn, 1, "My Laptop", b"cred-mine")
    _passkey(conn, other_user, "Mallory Key", b"cred-theirs")
    html = client.get("/auth/sessions").text
    assert "My Laptop" in html
    assert "Mallory Key" not in html


def test_sessions_page_empty_passkeys_state(client: TestClient) -> None:
    assert "No passkeys yet" in client.get("/auth/sessions").text


def test_revoke_other_own_session(client: TestClient, conn: sqlite3.Connection) -> None:
    second = issue_session(conn)
    r = client.post(f"/auth/sessions/{session_handle(second)}/revoke", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/auth/sessions"
    assert sessions_repo.get_session(conn, second) is None
    assert client.get("/accounts", follow_redirects=False).status_code == 200


def test_cannot_revoke_another_users_session(
    client: TestClient, conn: sqlite3.Connection, other_user: int
) -> None:
    foreign = issue_session(conn, user_id=other_user)
    r = client.post(f"/auth/sessions/{session_handle(foreign)}/revoke")
    assert r.status_code == 404
    assert sessions_repo.get_session(conn, foreign) is not None


@pytest.mark.parametrize("handle", ["nothex!!", "0123", "ABCDEF0123456789"])
def test_malformed_handle_is_404(client: TestClient, handle: str) -> None:
    assert client.post(f"/auth/sessions/{handle}/revoke").status_code == 404


def test_unknown_handle_is_404(client: TestClient) -> None:
    unknown = "0" * 16
    assert client.post(f"/auth/sessions/{unknown}/revoke").status_code == 404


def test_revoking_current_session_signs_out(
    client: TestClient, session_cookie: tuple[str, str], conn: sqlite3.Connection
) -> None:
    current = session_cookie[1]
    r = client.post(f"/auth/sessions/{session_handle(current)}/revoke", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/auth/login"
    cleared = [h for h in r.headers.get_list("set-cookie") if h.startswith(SESSION_COOKIE_NAME)]
    assert cleared
    assert "max-age=0" in cleared[0].lower()
    assert sessions_repo.get_session(conn, current) is None


def test_revoke_own_passkey(client: TestClient, conn: sqlite3.Connection) -> None:
    pk = _passkey(conn, 1, "Phone", b"cred-phone")
    r = client.post(f"/auth/passkeys/{pk}/revoke", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/auth/sessions"
    assert webauthn_repo.list_credentials(conn, 1) == ()


def test_cannot_revoke_another_users_passkey(
    client: TestClient, conn: sqlite3.Connection, other_user: int
) -> None:
    pk = _passkey(conn, other_user, "Theirs", b"cred-theirs")
    r = client.post(f"/auth/passkeys/{pk}/revoke")
    assert r.status_code == 404
    assert len(webauthn_repo.list_credentials(conn, other_user)) == 1


def test_sessions_requires_login(anon_client: TestClient) -> None:
    r = anon_client.get("/auth/sessions", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/auth/login?next=%2Fauth%2Fsessions"


def test_app_nav_shows_security_and_sign_out(client: TestClient) -> None:
    html = client.get("/accounts").text
    assert 'href="/auth/sessions"' in html
    assert 'action="/auth/logout"' in html
    assert "owner@example.test" in html
