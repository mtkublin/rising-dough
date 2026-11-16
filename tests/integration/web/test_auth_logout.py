"""T-D02b — ``POST /auth/logout`` revokes the session and clears the cookie."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from budget_planner.repositories import sessions as sessions_repo
from budget_planner.web.auth_cookies import SESSION_COOKIE_NAME

pytestmark = pytest.mark.integration


def test_logout_revokes_session_and_clears_cookie(
    client: TestClient, session_cookie: tuple[str, str], conn: sqlite3.Connection
) -> None:
    _name, session_id = session_cookie
    r = client.post("/auth/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/auth/login"
    cleared = [h for h in r.headers.get_list("set-cookie") if h.startswith(SESSION_COOKIE_NAME)]
    assert len(cleared) == 1
    assert "max-age=0" in cleared[0].lower()
    assert sessions_repo.get_session(conn, session_id) is None
    audit = conn.execute(
        "SELECT prev_json FROM audit_log WHERE entity_type = 'session' AND operation = 'delete'"
    ).fetchone()
    assert audit is not None
    assert session_id not in audit["prev_json"]


def test_after_logout_protected_pages_redirect(client: TestClient) -> None:
    client.post("/auth/logout")
    r = client.get("/accounts", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login")


def test_logout_requires_session(anon_client: TestClient) -> None:
    r = anon_client.post("/auth/logout", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login")


def test_logout_requires_csrf(client: TestClient, session_cookie: tuple[str, str]) -> None:
    r = client.post("/auth/logout", headers={"X-CSRF-Token": "forged"}, follow_redirects=False)
    assert r.status_code == 403
