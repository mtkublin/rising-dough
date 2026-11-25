"""T-D02b/T-D47 — Settings → Security: list + revoke own sessions and passkeys only."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.repositories import sessions as sessions_repo, webauthn as webauthn_repo
from budget_planner.repositories.sessions import session_handle
from budget_planner.web.auth_cookies import SESSION_COOKIE_NAME
from tests.auth_support import issue_session, seed_login_user
from tests.ui_map import _html, settings as ui

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
    client: TestClient,
    session_cookie: tuple[str, str],
    conn: sqlite3.Connection,
    other_user: int,
    settings: Settings,
) -> None:
    second = issue_session(conn)
    foreign = issue_session(conn, user_id=other_user)
    r = client.get("/settings/security")
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
    assert "EXPIRES" in html
    # The page renders expiry in the display timezone (ADR-0007), so derive it the same way.
    expected = (
        (clock.now_in(settings.display_timezone) + timedelta(days=30)).strftime("%d %b").upper()
    )
    assert expected in html  # absolute expiry = created_at + 30 days (ADR-0076)


def test_sessions_page_lists_own_passkeys(
    client: TestClient, conn: sqlite3.Connection, other_user: int
) -> None:
    _passkey(conn, 1, "My Laptop", b"cred-mine")
    _passkey(conn, other_user, "Mallory Key", b"cred-theirs")
    html = client.get("/settings/security").text
    assert "My Laptop" in html
    assert "Mallory Key" not in html


def test_sessions_page_empty_passkeys_state(client: TestClient) -> None:
    assert "No passkeys yet" in client.get("/settings/security").text


def test_revoke_other_own_session(client: TestClient, conn: sqlite3.Connection) -> None:
    second = issue_session(conn)
    r = client.post(f"/auth/sessions/{session_handle(second)}/revoke", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/settings/security#sessions"
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
    assert r.headers["location"] == "/settings/security#passkeys"
    assert webauthn_repo.list_credentials(conn, 1) == ()


def test_cannot_revoke_another_users_passkey(
    client: TestClient, conn: sqlite3.Connection, other_user: int
) -> None:
    pk = _passkey(conn, other_user, "Theirs", b"cred-theirs")
    r = client.post(f"/auth/passkeys/{pk}/revoke")
    assert r.status_code == 404
    assert len(webauthn_repo.list_credentials(conn, other_user)) == 1


def test_sessions_requires_login(anon_client: TestClient) -> None:
    r = anon_client.get("/settings/security", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/auth/login?next=%2Fsettings%2Fsecurity"


def test_app_nav_shows_only_sign_out(client: TestClient) -> None:
    html = client.get("/accounts").text
    assert 'href="/auth/sessions"' not in html
    assert 'href="/settings/password"' not in html
    assert 'action="/auth/logout"' in html
    assert "owner@example.test" in html


def test_security_tab_lists_all_sections_for_non_admin(client: TestClient) -> None:
    html = client.get("/settings/security").text
    assert _html.resolve_one(html, ui.tab("Security"))["aria-selected"] == "true"
    assert 'id="password"' in html
    assert 'id="passkeys"' in html
    assert 'id="sessions"' in html
    assert html.index('id="password"') < html.index('id="passkeys"') < html.index('id="sessions"')
    assert "data-passkey-register" in html
    assert "/static/rd/js/passkeys.js" in html
    assert 'id="tab-users"' not in html


def test_legacy_sessions_get_redirects_to_security_tab(client: TestClient) -> None:
    r = client.get("/auth/sessions", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/settings/security#sessions"


def test_legacy_register_get_redirects_to_security_tab(client: TestClient) -> None:
    r = client.get("/auth/register", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/settings/security#passkeys"


def test_password_get_redirects_to_security_tab_when_not_forced(client: TestClient) -> None:
    r = client.get("/settings/password", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/settings/security#password"


# --- T-UR14: the session and passkey rows on the new shell ----------------------------------------


def test_session_rows_print_the_device_label_and_only_others_ids(
    client: TestClient, conn: sqlite3.Connection, other_user: int
) -> None:
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Gecko/20100101 Firefox/121.0"
    sessions_repo.create_session(conn, 1, ip="83.24.117.9", user_agent=ua)
    sessions_repo.create_session(conn, other_user, ip="9.9.9.9", user_agent=ua)
    html = client.get("/settings/security").text
    sessions = _html.text_of(html, ui.sessions)
    assert "Firefox · macOS" in sessions
    assert "83.24.117.9" in sessions
    assert "9.9.9.9" not in sessions  # the other user's session is absent
    assert _html.count(html, ui.session_signout.inside(ui.sessions)) == 2  # this one + the new one


def test_revoking_another_session_removes_its_row_and_keeps_the_current(
    client: TestClient, conn: sqlite3.Connection, session_cookie: tuple[str, str]
) -> None:
    second = issue_session(conn)
    assert (
        _html.count(client.get("/settings/security").text, ui.session_signout.inside(ui.sessions))
        == 2
    )
    client.post(f"/auth/sessions/{session_handle(second)}/revoke")
    html = client.get("/settings/security").text
    assert _html.count(html, ui.session_signout.inside(ui.sessions)) == 1
    assert session_handle(second) not in html
    assert sessions_repo.get_session(conn, session_cookie[1]) is not None


def test_passkey_rows_list_own_label_and_post_to_the_revoke_route(
    client: TestClient, conn: sqlite3.Connection, other_user: int
) -> None:
    pk = _passkey(conn, 1, "Laptop key", b"cred-laptop")
    _passkey(conn, other_user, "Mallory key", b"cred-mallory")
    html = client.get("/settings/security").text
    assert "Laptop key" in _html.text_of(html, ui.passkeys)
    assert "Mallory key" not in html
    remove = _html.resolve_one(html, ui.passkey_remove("Laptop key"))
    remove_form = remove.find_parent("form")
    assert remove_form is not None
    assert remove_form["action"] == f"/auth/passkeys/{pk}/revoke"
    register = _html.resolve_one(html, ui.add_passkey).find_parent("form")
    assert register is not None
    assert register.has_attr("data-passkey-register")  # the hook rd/js/passkeys.js binds
    assert _html.resolve_one(html, ui.passkey_label)["name"] == "label"


# --- T-UR14 F2: HTMX revoke on the new shell ---------------------------------------------------

HX = {"HX-Request": "true"}


def _audit_rows(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])


def test_hx_session_revoke_swaps_the_row_out_and_flashes(
    client: TestClient, conn: sqlite3.Connection
) -> None:
    second = issue_session(conn)
    audits = _audit_rows(conn)
    r = client.post(f"/auth/sessions/{session_handle(second)}/revoke", headers=HX)
    assert r.status_code == 200
    assert "Signed out" in _html.text_of(r.text, ui.flash_success)
    assert not _html.exists(r.text, ui.session_signout)  # empty row swap
    assert sessions_repo.get_session(conn, second) is None
    assert _audit_rows(conn) > audits


def test_hx_stale_session_revoke_is_a_404_flash_not_json(
    client: TestClient, conn: sqlite3.Connection
) -> None:
    second = issue_session(conn)
    client.post(f"/auth/sessions/{session_handle(second)}/revoke", headers=HX)
    r = client.post(f"/auth/sessions/{session_handle(second)}/revoke", headers=HX)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("text/html")
    assert "Session not found" in _html.text_of(r.text, ui.flash_error)


def test_hx_cannot_revoke_another_users_session(
    client: TestClient, conn: sqlite3.Connection, other_user: int
) -> None:
    foreign = issue_session(conn, user_id=other_user)
    r = client.post(f"/auth/sessions/{session_handle(foreign)}/revoke", headers=HX)
    assert r.status_code == 404
    assert sessions_repo.get_session(conn, foreign) is not None


def test_hx_revoking_the_current_session_redirects_to_login(
    client: TestClient, session_cookie: tuple[str, str], conn: sqlite3.Connection
) -> None:
    current = session_cookie[1]
    r = client.post(f"/auth/sessions/{session_handle(current)}/revoke", headers=HX)
    assert r.headers["hx-redirect"] == "/auth/login"
    assert sessions_repo.get_session(conn, current) is None


def test_hx_passkey_remove_flashes_and_stale_is_404(
    client: TestClient, conn: sqlite3.Connection, other_user: int
) -> None:
    pk = _passkey(conn, 1, "Phone", b"cred-phone")
    foreign = _passkey(conn, other_user, "Theirs", b"cred-theirs")
    audits = _audit_rows(conn)
    r = client.post(f"/auth/passkeys/{pk}/revoke", headers=HX)
    assert r.status_code == 200
    assert "Passkey removed" in _html.text_of(r.text, ui.flash_success)
    assert webauthn_repo.list_credentials(conn, 1) == ()
    assert _audit_rows(conn) > audits
    again = client.post(f"/auth/passkeys/{pk}/revoke", headers=HX)
    assert again.status_code == 404
    assert "Passkey not found" in _html.text_of(again.text, ui.flash_error)
    assert client.post(f"/auth/passkeys/{foreign}/revoke", headers=HX).status_code == 404
    assert len(webauthn_repo.list_credentials(conn, other_user)) == 1
