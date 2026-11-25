"""Settings pages: tabs, close, security (T-UT04e, ADR-0106 section 1).

Bodies are inspected only through the UI map. Password change lives in
``test_settings_password.py``, the admin roster in ``test_settings_users.py``.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from tests.auth_support import issue_session
from tests.contract.conftest import covers
from tests.contract.web_helpers_t_ut04e import HX, make_category
from tests.ui_map import _html, settings as ui

pytest_plugins = ["tests.contract.web_support_t_ut04e"]  # client, admin_client, anon_client, db

TAB_NAMES = ("Categories", "Currency & FX", "Preferences", "Security")


def _selected_tabs(html: str) -> list[str]:
    return [
        _html.accessible_name(t)
        for t in _html.resolve(html, ui.tab_any)
        if t.get("aria-selected") == "true"
    ]


# --- GET /settings ---------------------------------------------------------


@covers("GET /settings")
def test_default_tab_is_categories_with_groups_and_anchor(
    client: TestClient, _migrated: Settings
) -> None:
    cat = make_category(_migrated)
    r = client.get("/settings")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert _html.text_of(r.text, ui.heading) == "Categories"
    assert _selected_tabs(r.text) == ["Categories"]
    assert _html.exists(r.text, ui.new_category)
    assert _html.exists(r.text, ui.category_slot)
    assert _html.exists(r.text, ui.income_anchor)
    assert _html.exists(r.text, ui.category_row(cat))
    assert _html.exists(r.text, ui.edit_category(cat))
    assert _html.exists(r.text, ui.archive_category(cat))


@covers("GET /settings")
def test_tab_strip_lists_member_tabs_without_users(client: TestClient) -> None:
    r = client.get("/settings")
    for name in TAB_NAMES:
        assert _html.exists(r.text, ui.tab(name)), name
    assert not _html.exists(r.text, ui.tab("Users"))
    assert _html.resolve_one(r.text, ui.tab("Security"))["href"] == "/settings/security"


@covers("GET /settings")
def test_tab_strip_shows_users_tab_for_admins(admin_client: TestClient) -> None:
    r = admin_client.get("/settings")
    assert _html.resolve_one(r.text, ui.tab("Users"))["href"] == "/settings/users"


@covers("GET /settings")
def test_system_categories_are_locked(client: TestClient, db: sqlite3.Connection) -> None:
    system = db.execute("SELECT id FROM categories WHERE is_system = 1 LIMIT 1").fetchone()[0]
    r = client.get("/settings")
    assert _html.exists(r.text, ui.category_row(system))
    assert not _html.exists(r.text, ui.edit_category(system))
    assert not _html.exists(r.text, ui.archive_category(system))


@covers("GET /settings")
def test_fx_tab_shows_cache_or_empty_state(client: TestClient) -> None:
    r = client.get("/settings?tab=fx")
    assert r.status_code == 200
    assert _html.text_of(r.text, ui.heading) == "Currency & FX"
    assert _selected_tabs(r.text) == ["Currency & FX"]
    assert _html.exists(r.text, ui.fx_heading)
    assert "No FX rates cached yet" in _html.text_of(r.text, ui.panel)


@covers("GET /settings")
def test_prefs_tab_shows_base_currency_and_timezone(client: TestClient, settings: Settings) -> None:
    r = client.get("/settings?tab=prefs")
    assert r.status_code == 200
    assert _selected_tabs(r.text) == ["Preferences"]
    assert _html.exists(r.text, ui.preferences_heading)
    panel = _html.text_of(r.text, ui.panel)
    assert settings.base_currency in panel
    assert settings.display_timezone in panel


@covers("GET /settings")
def test_unknown_tab_is_422_and_empty_tab_is_categories(client: TestClient) -> None:
    assert client.get("/settings?tab=bogus").status_code == 422
    r = client.get("/settings?tab=")
    assert r.status_code == 200
    assert _selected_tabs(r.text) == ["Categories"]


@covers("GET /settings")
def test_htmx_request_gets_the_new_shell_page(
    client: TestClient, _migrated: Settings, db: sqlite3.Connection
) -> None:
    # ADR-0152: the slide-over drawer is gone; an HX GET returns the page the regions select from.
    make_category(_migrated, "Mine only")
    db.execute("INSERT INTO users (id, name) VALUES (2, 'other') ON CONFLICT(id) DO NOTHING")
    db.execute(
        "INSERT INTO categories (user_id, name, direction, is_system) "
        "VALUES (2, 'Theirs only', 'expense', 0)"
    )
    db.commit()
    r = client.get("/settings", headers=HX)
    region = _html.text_of(r.text, ui.category_slot)
    assert "Mine only" in region
    assert "Theirs only" not in r.text
    assert r.status_code == 200
    assert _html.text_of(r.text, ui.heading) == "Categories"
    assert _selected_tabs(r.text) == ["Categories"]
    assert _html.exists(r.text, ui.category_slot)
    assert "<aside" not in r.text
    assert "aria-modal" not in r.text


@covers("GET /settings")
def test_settings_requires_login(anon_client: TestClient) -> None:
    r = anon_client.get("/settings", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login")
    hx = anon_client.get("/settings", headers=HX, follow_redirects=False)
    assert hx.status_code == 401
    assert hx.headers["HX-Redirect"].startswith("/auth/login")


@covers("GET /settings")
def test_forced_rotation_redirects_before_settings(
    client: TestClient, db: sqlite3.Connection
) -> None:
    db.execute("UPDATE users SET must_change_password = 1 WHERE id = 1")
    db.commit()
    r = client.get("/settings", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/settings/password")


# --- GET /settings/close ---------------------------------------------------


@covers("GET /settings/close")
def test_close_returns_empty_fragment(client: TestClient) -> None:
    r = client.get("/settings/close")
    assert r.status_code == 200
    assert r.text == ""
    assert r.headers["content-type"].startswith("text/html")


@covers("GET /settings/close")
def test_close_requires_login(anon_client: TestClient) -> None:
    r = anon_client.get("/settings/close", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login")


# --- GET /settings/security ------------------------------------------------


@covers("GET /settings/security")
def test_security_page_has_password_passkeys_and_sessions(client: TestClient) -> None:
    r = client.get("/settings/security")
    assert r.status_code == 200
    assert _html.exists(r.text, ui.security_heading)
    assert _selected_tabs(r.text) == ["Security"]
    assert _html.exists(r.text, ui.password_form)
    assert _html.resolve_one(r.text, ui.password_form)["action"] == "/settings/password"
    assert _html.exists(r.text, ui.change_password_button)
    assert _html.exists(r.text, ui.passkeys)
    assert _html.exists(r.text, ui.add_passkey)
    assert _html.exists(r.text, ui.sessions)
    for ctl in (ui.current_password, ui.new_password, ui.confirm_password):
        assert _html.resolve_one(r.text, ctl.inside(ui.password_form)) is not None
    assert not _html.exists(r.text, ui.forced_banner)


@covers("GET /settings/security")
def test_security_page_marks_current_session_and_lists_others(
    client: TestClient, db: sqlite3.Connection
) -> None:
    before = _html.text_of(client.get("/settings/security").text, ui.sessions)
    assert "THIS DEVICE" in before
    issue_session(db)
    after = client.get("/settings/security").text
    assert _html.count(after, ui.session_signout.inside(ui.sessions)) == 1  # not the current device


@covers("GET /settings/security")
def test_security_page_lists_passkeys(client: TestClient, db: sqlite3.Connection) -> None:
    empty = client.get("/settings/security").text
    assert "No passkeys yet" in _html.text_of(empty, ui.passkeys)
    db.execute(
        "INSERT INTO webauthn_credentials "
        "(user_id, credential_id, public_key, sign_count, transports, label) "
        "VALUES (1, x'0102', x'0304', 0, '', 'Mac')"
    )
    db.commit()
    html = client.get("/settings/security").text
    assert _html.exists(html, ui.passkey_remove("Mac"))


@covers("GET /settings/security")
def test_security_requires_login(anon_client: TestClient) -> None:
    r = anon_client.get("/settings/security", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/auth/login?next=%2Fsettings%2Fsecurity"


@covers("GET /settings/security")
def test_security_redirects_forced_user_to_rotation(
    client: TestClient, db: sqlite3.Connection
) -> None:
    db.execute("UPDATE users SET must_change_password = 1 WHERE id = 1")
    db.commit()
    r = client.get("/settings/security", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/settings/password?next=%2Fsettings%2Fsecurity"


@pytest.mark.parametrize("path", ["/settings", "/settings/security"])
@covers("GET /settings", "GET /settings/security")
def test_settings_pages_do_not_link_to_password_page(client: TestClient, path: str) -> None:
    r = client.get(path)
    hrefs = {a.get("href") for a in _html.resolve(r.text, ui.any_link)}
    assert "/settings/password" not in hrefs
