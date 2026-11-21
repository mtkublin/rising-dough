"""Admin roster at ``/settings/users``: authz, CSRF, HX shapes, DB and audit (T-UT04e).

ADR-0106 section 1, ADR-0061 section 4, ADR-0073. Bodies are inspected only
through the UI map. bcrypt is pinned to cost 4 for this module only.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from budget_planner.services import _passwords
from budget_planner.services.users import (
    DUPLICATE_EMAIL_MESSAGE,
    LAST_ADMIN_DEMOTE_MESSAGE,
    SELF_DELETE_MESSAGE,
)
from tests.auth_support import FAST_ROUNDS, issue_session
from tests.contract.conftest import covers
from tests.contract.web_helpers_t_ut04e import HX, live_sessions
from tests.ui_map import _html, settings as ui

pytest_plugins = ["tests.contract.web_support_t_ut04e"]  # admin_client, client, anon_client, db

ADMIN_GET = ("/settings/users", "/settings/users/1/edit")
ADMIN_POST = (
    "/settings/users",
    "/settings/users/1",
    "/settings/users/1/reset-password",
    "/settings/users/1/delete",
)


@pytest.fixture(autouse=True)
def _cheap_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_passwords, "DEFAULT_ROUNDS", FAST_ROUNDS)


def _password_in(html: str) -> str:
    return _html.text_of(html, ui.new_password_value)


def _add(admin: TestClient, email: str, *, is_admin: bool = False) -> str:
    data = {"email": email, "name": "Alice", **({"is_admin": "on"} if is_admin else {})}
    r = admin.post("/settings/users", data=data, headers=HX)
    assert r.status_code == 200, r.text
    return _password_in(r.text)


def _uid(db: sqlite3.Connection, email: str) -> int:
    row = db.execute(
        "SELECT id FROM users WHERE lower(email) = lower(?) AND deleted_at IS NULL", (email,)
    ).fetchone()
    assert row is not None
    return int(row[0])


def _audit(db: sqlite3.Connection, uid: int, operation: str) -> sqlite3.Row:
    row: sqlite3.Row | None = db.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'users' AND entity_id = ? AND operation = ?",
        (uid, operation),
    ).fetchone()
    assert row is not None
    return row


# --- authz and CSRF (every route) -------------------------------------------


@covers("GET /settings/users", "GET /settings/users/{user_id}/edit")
@pytest.mark.parametrize("path", ADMIN_GET)
def test_non_admin_get_is_404_and_anonymous_goes_to_login(
    client: TestClient, anon_client: TestClient, path: str
) -> None:
    assert client.get(path).status_code == 404
    assert client.get(path, headers=HX).status_code == 404
    anon = anon_client.get(path, follow_redirects=False)
    assert anon.status_code == 302
    assert anon.headers["location"].startswith("/auth/login")


@covers(
    "POST /settings/users",
    "POST /settings/users/{user_id}",
    "POST /settings/users/{user_id}/reset-password",
    "POST /settings/users/{user_id}/delete",
)
@pytest.mark.parametrize("path", ADMIN_POST)
def test_non_admin_post_is_404_before_csrf_and_changes_nothing(
    client: TestClient, db: sqlite3.Connection, path: str
) -> None:
    users_before = db.execute("SELECT count(*), sum(is_admin) FROM users").fetchone()
    r = client.post(path, data={"email": "x@y.test"}, headers={"X-CSRF-Token": "bogus"})
    assert r.status_code == 404
    assert tuple(db.execute("SELECT count(*), sum(is_admin) FROM users").fetchone()) == tuple(
        users_before
    )


@covers(
    "POST /settings/users",
    "POST /settings/users/{user_id}",
    "POST /settings/users/{user_id}/reset-password",
    "POST /settings/users/{user_id}/delete",
)
@pytest.mark.parametrize("path", ADMIN_POST)
def test_admin_post_without_csrf_token_is_403(
    admin_raw_client: TestClient, db: sqlite3.Connection, path: str
) -> None:
    r = admin_raw_client.post(path, data={"email": "new@example.test"})
    assert r.status_code == 403
    assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1
    assert db.execute("SELECT deleted_at FROM users WHERE id = 1").fetchone()[0] is None


@covers("POST /settings/users")
def test_post_by_anonymous_is_not_served(anon_client: TestClient, db: sqlite3.Connection) -> None:
    r = anon_client.post("/settings/users", data={"email": "a@b.test"}, follow_redirects=False)
    assert r.status_code in {302, 401, 403}
    assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1


@covers("GET /settings/users")
def test_forced_rotation_comes_before_admin_pages(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    db.execute("UPDATE users SET must_change_password = 1 WHERE id = 1")
    db.commit()
    r = admin_client.get("/settings/users", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/settings/password?next=%2Fsettings%2Fusers"


# --- GET /settings/users -----------------------------------------------------


@covers("GET /settings/users")
def test_list_shows_live_users_only_and_marks_me(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    db.execute(
        "INSERT INTO users (name, email, deleted_at) VALUES ('gone', 'gone@x.test', '2026-01-01')"
    )
    db.commit()
    r = admin_client.get("/settings/users")
    assert r.status_code == 200
    assert _html.exists(r.text, ui.users_heading)
    assert _html.exists(r.text, ui.user_row(1))
    assert "You" in _html.text_of(r.text, ui.user_row(1))
    assert "gone@x.test" not in _html.text_of(r.text, ui.users_table)
    assert _html.resolve_one(r.text, ui.tab("Users"))["aria-selected"] == "true"
    assert not _html.exists(r.text, ui.remove_user("owner@example.test"))  # no self-remove
    assert _html.exists(r.text, ui.reset_user("owner@example.test"))


# --- POST /settings/users ----------------------------------------------------


@covers("POST /settings/users")
def test_create_shows_password_once_oob_table_and_audits_actor(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    r = admin_client.post(
        "/settings/users", data={"email": " New@Example.TEST ", "name": ""}, headers=HX
    )
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    password = _password_in(r.text)
    assert len(password) == 22
    assert _html.resolve_one(r.text, ui.users_table)["hx-swap-oob"] == "true"
    assert "new@example.test" in _html.text_of(r.text, ui.users_table)
    uid = _uid(db, "new@example.test")
    row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    assert (row["name"], row["is_admin"], row["must_change_password"]) == ("new", 0, 1)
    assert _passwords.verify_password(password, row["password_hash"])
    audit = _audit(db, uid, "create")
    assert (audit["actor_user_id"], audit["user_id"]) == (1, 1)
    assert "password_hash" not in json.loads(audit["new_json"])
    assert password not in "\n".join(db.iterdump())
    assert password not in admin_client.get("/settings/users").text


@covers("POST /settings/users")
def test_create_admin_flag_and_login_works(
    admin_client: TestClient, anon_client: TestClient, db: sqlite3.Connection
) -> None:
    password = _add(admin_client, "boss@example.test", is_admin=True)
    assert (
        db.execute(
            "SELECT is_admin FROM users WHERE id = ?", (_uid(db, "boss@example.test"),)
        ).fetchone()[0]
        == 1
    )
    login = anon_client.post(
        "/auth/login",
        data={"email": "boss@example.test", "password": password},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert (
        anon_client.get("/today", follow_redirects=False)
        .headers["location"]
        .startswith("/settings/password")
    )


@covers("POST /settings/users")
def test_create_non_htmx_renders_full_page_with_toast_inline(admin_client: TestClient) -> None:
    r = admin_client.post("/settings/users", data={"email": "plain@example.test"})
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert _html.exists(r.text, ui.users_heading)
    assert _html.exists(r.text, ui.new_password_toast)
    assert not _html.resolve_one(r.text, ui.users_table).has_attr("hx-swap-oob")


@covers("POST /settings/users")
def test_create_duplicate_email_is_422_case_insensitive(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    _add(admin_client, "dup@example.test")
    r = admin_client.post("/settings/users", data={"email": "DUP@Example.test"}, headers=HX)
    assert r.status_code == 422
    assert DUPLICATE_EMAIL_MESSAGE in _html.text_of(r.text, ui.add_errors)
    assert not _html.exists(r.text, ui.new_password_value)
    n = db.execute("SELECT count(*) FROM users WHERE lower(email) = 'dup@example.test'").fetchone()
    assert n[0] == 1


@covers("POST /settings/users")
def test_create_invalid_email_non_htmx_rerenders_page_with_value(admin_client: TestClient) -> None:
    r = admin_client.post("/settings/users", data={"email": "nope", "name": "N"})
    assert r.status_code == 422
    assert _html.exists(r.text, ui.users_heading)
    assert _html.resolve_one(r.text, ui.user_email)["value"] == "nope"


@covers("POST /settings/users")
def test_create_reuses_email_of_removed_user(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    _add(admin_client, "again@example.test")
    uid = _uid(db, "again@example.test")
    assert admin_client.post(f"/settings/users/{uid}/delete", headers=HX).status_code == 200
    _add(admin_client, "again@example.test")


# --- GET /settings/users/{id}/edit -------------------------------------------


@covers("GET /settings/users/{user_id}/edit")
def test_edit_form_htmx_slideover_and_full_page(admin_client: TestClient) -> None:
    frag = admin_client.get("/settings/users/1/edit", headers=HX)
    assert frag.status_code == 200
    form = _html.resolve_one(frag.text, ui.edit_form)
    assert form["hx-post"] == "/settings/users/1"
    assert _html.resolve_one(frag.text, ui.user_email)["value"] == "owner@example.test"
    page = admin_client.get("/settings/users/1/edit")
    assert page.status_code == 200
    assert not _html.resolve_one(page.text, ui.edit_form).has_attr("hx-post")


@covers("GET /settings/users/{user_id}/edit")
def test_edit_form_missing_user_is_404(admin_client: TestClient) -> None:
    assert admin_client.get("/settings/users/999/edit").status_code == 404
    assert admin_client.get("/settings/users/999/edit", headers=HX).status_code == 404


# --- POST /settings/users/{id} -----------------------------------------------


@covers("POST /settings/users/{user_id}")
def test_save_updates_row_flashes_and_audits(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    _add(admin_client, "bob@example.test")
    uid = _uid(db, "bob@example.test")
    r = admin_client.post(
        f"/settings/users/{uid}",
        data={"email": "Robert@Example.test", "name": "Robert", "is_admin": "on"},
        headers=HX,
    )
    assert r.status_code == 200
    assert "robert@example.test" in _html.text_of(r.text, ui.users_table)
    assert _html.exists(r.text, ui.flash_success)
    row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    assert (row["email"], row["name"], row["is_admin"]) == ("robert@example.test", "Robert", 1)
    assert _audit(db, uid, "update")["actor_user_id"] == 1


@covers("POST /settings/users/{user_id}")
def test_save_non_htmx_redirects_to_list(admin_client: TestClient) -> None:
    r = admin_client.post(
        "/settings/users/1",
        data={"email": "owner@example.test", "name": "Owner", "is_admin": "on"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/settings/users"


@covers("POST /settings/users/{user_id}")
def test_save_duplicate_email_retargets_form(admin_client: TestClient) -> None:
    _add(admin_client, "carol@example.test")
    r = admin_client.post(
        "/settings/users/1", data={"email": "CAROL@example.test", "is_admin": "on"}, headers=HX
    )
    assert r.status_code == 422
    assert r.headers["hx-retarget"] == "#user-edit-form"
    assert r.headers["hx-reswap"] == "outerHTML"
    assert DUPLICATE_EMAIL_MESSAGE in _html.text_of(r.text, ui.add_errors)


@covers("POST /settings/users/{user_id}")
def test_save_invalid_email_non_htmx_is_full_422_page(admin_client: TestClient) -> None:
    r = admin_client.post("/settings/users/1", data={"email": "bad", "is_admin": "on"})
    assert r.status_code == 422
    assert _html.exists(r.text, ui.edit_form)


@covers("POST /settings/users/{user_id}")
def test_save_missing_user_is_404(admin_client: TestClient) -> None:
    assert admin_client.post("/settings/users/999", data={"email": "a@b.test"}).status_code == 404


@covers("POST /settings/users/{user_id}")
def test_demote_last_admin_is_409_without_swap(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    r = admin_client.post(
        "/settings/users/1", data={"email": "owner@example.test", "name": "o"}, headers=HX
    )
    assert r.status_code == 409
    assert r.headers["hx-reswap"] == "none"
    assert LAST_ADMIN_DEMOTE_MESSAGE in _html.text_of(r.text, ui.flash_error)
    assert db.execute("SELECT is_admin FROM users WHERE id = 1").fetchone()[0] == 1
    page = admin_client.post("/settings/users/1", data={"email": "owner@example.test"})
    assert page.status_code == 409


@covers("POST /settings/users/{user_id}")
def test_self_demote_allowed_with_second_admin_and_drops_access(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    _add(admin_client, "second@example.test", is_admin=True)
    r = admin_client.post(
        "/settings/users/1", data={"email": "owner@example.test", "name": "o"}, headers=HX
    )
    assert r.status_code == 200
    assert db.execute("SELECT is_admin FROM users WHERE id = 1").fetchone()[0] == 0
    assert admin_client.get("/settings/users").status_code == 404


# --- POST /settings/users/{id}/reset-password ---------------------------------


@covers("POST /settings/users/{user_id}/reset-password")
def test_reset_password_new_secret_revokes_sessions_and_audits(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    old = _add(admin_client, "dave@example.test")
    uid = _uid(db, "dave@example.test")
    db.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (uid,))
    db.commit()
    issue_session(db, user_id=uid)
    issue_session(db, user_id=uid)
    assert live_sessions(db, uid) == 2
    r = admin_client.post(f"/settings/users/{uid}/reset-password", headers=HX)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    new = _password_in(r.text)
    assert new != old
    assert "signed out" in _html.text_of(r.text, ui.new_password_toast)
    row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    assert row["must_change_password"] == 1
    assert _passwords.verify_password(new, row["password_hash"])
    assert live_sessions(db, uid) == 0
    audit = db.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'users' AND entity_id = ? "
        "AND json_extract(new_json, '$.action') = 'reset_password'",
        (uid,),
    ).fetchone()
    assert (audit["operation"], audit["actor_user_id"]) == ("update", 1)
    assert json.loads(audit["new_json"])["sessions_revoked"] == 2
    assert new not in "\n".join(db.iterdump())


@covers("POST /settings/users/{user_id}/reset-password")
def test_reset_password_non_htmx_missing_and_self(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    assert admin_client.post("/settings/users/999/reset-password").status_code == 404
    assert admin_client.post("/settings/users/999/reset-password", headers=HX).status_code == 404
    _add(admin_client, "gus@example.test")
    uid = _uid(db, "gus@example.test")
    page = admin_client.post(f"/settings/users/{uid}/reset-password")
    assert page.status_code == 200
    assert _html.exists(page.text, ui.new_password_toast)
    own = admin_client.post("/settings/users/1/reset-password", headers=HX)
    assert own.status_code == 200
    assert admin_client.get("/settings/users", follow_redirects=False).status_code == 302


# --- POST /settings/users/{id}/delete -----------------------------------------


@covers("POST /settings/users/{user_id}/delete")
def test_delete_soft_deletes_revokes_sessions_and_blocks_login(
    admin_client: TestClient, anon_client: TestClient, db: sqlite3.Connection
) -> None:
    password = _add(admin_client, "erin@example.test")
    uid = _uid(db, "erin@example.test")
    issue_session(db, user_id=uid)
    r = admin_client.post(f"/settings/users/{uid}/delete", headers=HX)
    assert r.status_code == 200
    assert "erin@example.test" not in _html.text_of(r.text, ui.users_table)
    assert _html.exists(r.text, ui.flash_success)
    assert db.execute("SELECT deleted_at FROM users WHERE id = ?", (uid,)).fetchone()[0]
    assert live_sessions(db, uid) == 0
    audit = _audit(db, uid, "delete")
    assert (audit["actor_user_id"], audit["new_json"]) == (1, None)
    login = anon_client.post(
        "/auth/login",
        data={"email": "erin@example.test", "password": password},
        follow_redirects=False,
    )
    assert login.status_code == 401


@covers("POST /settings/users/{user_id}/delete")
def test_delete_non_htmx_redirects_and_missing_is_404(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    _add(admin_client, "fay@example.test")
    uid = _uid(db, "fay@example.test")
    r = admin_client.post(f"/settings/users/{uid}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/settings/users"
    assert admin_client.post("/settings/users/999/delete").status_code == 404
    assert admin_client.post("/settings/users/999/delete", headers=HX).status_code == 404


@covers("POST /settings/users/{user_id}/delete")
def test_delete_self_is_409(admin_client: TestClient, db: sqlite3.Connection) -> None:
    _add(admin_client, "other-admin@example.test", is_admin=True)
    r = admin_client.post("/settings/users/1/delete", headers=HX)
    assert r.status_code == 409
    assert r.headers["hx-reswap"] == "none"
    assert SELF_DELETE_MESSAGE in _html.text_of(r.text, ui.flash_error)
    assert db.execute("SELECT deleted_at FROM users WHERE id = 1").fetchone()[0] is None
    assert admin_client.post("/settings/users/1/delete").status_code == 409


@covers("POST /settings/users/{user_id}/delete")
def test_delete_other_admin_is_allowed(admin_client: TestClient, db: sqlite3.Connection) -> None:
    _add(admin_client, "co-admin@example.test", is_admin=True)
    target = _uid(db, "co-admin@example.test")
    assert admin_client.post(f"/settings/users/{target}/delete", headers=HX).status_code == 200
    live_admins = db.execute(
        "SELECT count(*) FROM users WHERE is_admin = 1 AND deleted_at IS NULL"
    ).fetchone()[0]
    assert live_admins == 1
