"""T-D18 — ``/settings/password`` + ``MustChangePasswordMiddleware`` (ADR-0074)."""

from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from budget_planner.repositories import sessions as sessions_repo
from budget_planner.services import _passwords
from budget_planner.web.middleware.must_change_password import password_url
from tests.auth_support import TEST_PASSWORD, issue_session

pytestmark = pytest.mark.integration

NEW_PASSWORD = "a-brand-new-passphrase"  # noqa: S105  # pragma: allowlist secret
HX = {"HX-Request": "true", "HX-Current-URL": "https://testserver/ledger?month=2026-10"}
JSON_ACCEPT = {"Accept": "application/json"}


def _form(
    current: str = TEST_PASSWORD, new: str = NEW_PASSWORD, confirm: str | None = None
) -> dict[str, str]:
    return {
        "current_password": current,
        "new_password": new,
        "confirm_password": new if confirm is None else confirm,
    }


def _flag(conn: sqlite3.Connection, value: int = 1) -> None:
    conn.execute("UPDATE users SET must_change_password = ? WHERE id = 1", (value,))


def _user(conn: sqlite3.Connection) -> sqlite3.Row:
    row: sqlite3.Row = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
    return row


@pytest.fixture
def forced(client: TestClient, conn: sqlite3.Connection) -> TestClient:
    _flag(conn)
    return client


# --- page -------------------------------------------------------------------


def test_get_renders_form(client: TestClient) -> None:
    r = client.get("/settings/security")
    assert r.status_code == 200
    html = r.text
    assert "Change password" in html
    for name in ("current_password", "new_password", "confirm_password"):
        assert f'name="{name}"' in html
    assert 'autocomplete="new-password"' in html
    assert "Your password needs rotating" not in html


def test_get_forced_shows_banner(forced: TestClient) -> None:
    html = forced.get("/settings/password").text
    assert "Your password needs rotating" in html
    assert "Sign out instead" in html


def test_get_htmx_returns_fragment(forced: TestClient) -> None:
    r = forced.get("/settings/password", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert r.text.lstrip().startswith("<form")
    assert "<html" not in r.text


def test_get_carries_safe_next(forced: TestClient) -> None:
    html = forced.get("/settings/password?next=/ledger").text
    assert 'name="next" value="/ledger"' in html
    html = forced.get("/settings/password?next=https://evil.test/").text
    assert 'name="next" value="/today"' in html


def test_settings_and_nav_do_not_link_to_password(client: TestClient) -> None:
    html = client.get("/settings").text
    assert 'href="/settings/password"' not in html
    assert 'href="/settings/security"' in html


def test_forced_user_cannot_open_security_tab(forced: TestClient) -> None:
    r = forced.get("/settings/security", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/settings/password?next=%2Fsettings%2Fsecurity"


def test_forced_user_cannot_open_other_settings(forced: TestClient) -> None:
    r = forced.get("/settings", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/settings/password")


def test_forced_page_is_standalone(forced: TestClient) -> None:
    r = forced.get("/settings/password")
    assert r.status_code == 200
    assert 'id="tab-security"' not in r.text
    assert 'id="passkeys"' not in r.text


def test_anonymous_redirected_to_login(anon_client: TestClient) -> None:
    r = anon_client.get("/settings/password", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login")


# --- POST -------------------------------------------------------------------


def test_post_success_rotates_and_revokes_others(
    forced: TestClient, conn: sqlite3.Connection, session_cookie: tuple[str, str]
) -> None:
    other = issue_session(conn)
    r = forced.post(
        "/settings/password", data={**_form(), "next": "/ledger"}, follow_redirects=False
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/ledger"
    row = _user(conn)
    assert row["must_change_password"] == 0
    assert _passwords.verify_password(NEW_PASSWORD, row["password_hash"])
    assert sessions_repo.get_session(conn, session_cookie[1]) is not None
    assert sessions_repo.get_session(conn, other) is None
    # Flag cleared → the next request is served normally.
    assert forced.get("/accounts", follow_redirects=False).status_code == 200


def test_post_success_htmx_uses_hx_redirect(client: TestClient) -> None:
    r = client.post("/settings/password", data=_form(), headers={"HX-Request": "true"})
    assert r.status_code == 204
    assert r.headers["HX-Redirect"] == "/settings/security"


def test_post_success_next_password_path_falls_back_to_root(forced: TestClient) -> None:
    r = forced.post(
        "/settings/password",
        data={**_form(), "next": "/settings/password"},
        follow_redirects=False,
    )
    assert r.headers["location"] == "/today"


def test_post_wrong_current_audits_and_keeps_state(
    forced: TestClient, conn: sqlite3.Connection
) -> None:
    before = _user(conn)["password_hash"]
    r = forced.post(
        "/settings/password",
        data=_form(current="definitely-wrong"),
        headers={"User-Agent": "audit-ua"},
    )
    assert r.status_code == 422
    assert "That isn&#39;t your current password." in r.text or "isn't your current" in r.text
    assert 'aria-invalid="true"' in r.text
    assert "definitely-wrong" not in r.text
    row = _user(conn)
    assert row["password_hash"] == before
    assert row["must_change_password"] == 1
    audit = conn.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'auth_event' ORDER BY id DESC"
    ).fetchone()
    assert json.loads(audit["new_json"])["event"] == "password_change_failed"
    assert audit["user_id"] == 1
    assert audit["user_agent"] == "audit-ua"
    assert audit["ip"] is not None
    assert audit["session_id"] is not None


@pytest.mark.parametrize(
    ("form", "snippet"),
    [
        (_form(confirm="something-else-entirely"), "don"),
        (_form(new="short"), "at least 12"),
        (_form(new="z" * 73), "72 bytes"),
        (_form(new=TEST_PASSWORD), "different from your current"),
    ],
)
def test_post_policy_errors_render_inline(
    client: TestClient, conn: sqlite3.Connection, form: dict[str, str], snippet: str
) -> None:
    before = _user(conn)["password_hash"]
    r = client.post("/settings/password", data=form)
    assert r.status_code == 422
    assert snippet in r.text
    assert "<html" in r.text
    assert 'id="tab-security"' in r.text
    assert _user(conn)["password_hash"] == before


def test_post_error_htmx_returns_fragment(client: TestClient) -> None:
    r = client.post("/settings/password", data=_form(new="short"), headers={"HX-Request": "true"})
    assert r.status_code == 422
    assert r.text.lstrip().startswith("<form")
    assert 'id="pw-summary"' in r.text


def test_post_requires_csrf(anon_client: TestClient, session_cookie: tuple[str, str]) -> None:
    raw = TestClient(anon_client.app, base_url="https://testserver")
    raw.cookies.set(*session_cookie)
    r = raw.post("/settings/password", data=_form())
    assert r.status_code == 403


# --- forced redirect ----------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/accounts", "/ledger?month=2026-10", "/auth/sessions"])
def test_forced_html_redirect(forced: TestClient, path: str) -> None:
    r = forced.get(path, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == password_url(path)
    assert r.headers["location"].startswith("/settings/password")


def test_forced_redirect_carries_next(forced: TestClient) -> None:
    r = forced.get("/accounts", follow_redirects=False)
    assert r.headers["location"] == "/settings/password?next=%2Faccounts"


def test_forced_htmx_gets_hx_redirect(forced: TestClient) -> None:
    r = forced.get("/accounts", headers=HX, follow_redirects=False)
    assert r.status_code == 403
    assert r.headers["HX-Redirect"] == "/settings/password?next=%2Fledger%3Fmonth%3D2026-10"
    assert r.json() == {"error": "password_change_required", "location": "/settings/password"}


def test_forced_htmx_foreign_current_url_drops_next(forced: TestClient) -> None:
    headers = {"HX-Request": "true", "HX-Current-URL": "https://evil.test/x"}
    r = forced.get("/accounts", headers=headers)
    assert r.headers["HX-Redirect"] == "/settings/password"


def test_forced_json_gets_403(forced: TestClient) -> None:
    r = forced.get("/accounts", headers=JSON_ACCEPT, follow_redirects=False)
    assert r.status_code == 403
    assert r.json()["error"] == "password_change_required"


def test_forced_post_elsewhere_is_blocked(forced: TestClient) -> None:
    r = forced.post("/auth/sessions/0000000000000000/revoke", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/settings/password")


@pytest.mark.parametrize("path", ["/health", "/healthz", "/static/auth.css", "/settings/password"])
def test_forced_exempt_paths(forced: TestClient, path: str) -> None:
    r = forced.get(path, follow_redirects=False)
    assert r.status_code != 302


def test_forced_ready_is_exempt(forced: TestClient) -> None:
    r = forced.get("/ready", follow_redirects=False)
    assert "location" not in r.headers


def test_forced_logout_is_exempt(forced: TestClient, session_cookie: tuple[str, str]) -> None:
    r = forced.post("/auth/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/auth/login"


def test_unflagged_user_is_not_redirected(client: TestClient) -> None:
    assert client.get("/accounts", follow_redirects=False).status_code == 200


def test_anonymous_not_affected_by_rotation_gate(anon_client: TestClient) -> None:
    r = anon_client.get("/accounts", follow_redirects=False)
    assert r.headers["location"].startswith("/auth/login")
