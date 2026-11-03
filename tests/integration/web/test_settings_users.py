"""Integration tests for the admin user roster at ``/settings/users`` (T-D17).

ADR-0061 §4, ADR-0073. ``admin_client`` is user 1 promoted to admin;
``client`` is user 1 as a regular member; ``anon_client`` has no session.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator

import pytest
from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.services import _passwords
from budget_planner.services.users import (
    DUPLICATE_EMAIL_MESSAGE,
    LAST_ADMIN_DEMOTE_MESSAGE,
    SELF_DELETE_MESSAGE,
)
from tests.auth_support import issue_session

HX = {"HX-Request": "true"}
ADMIN_PATHS_GET = ("/settings/users", "/settings/users/1/edit")
ADMIN_PATHS_POST = (
    "/settings/users",
    "/settings/users/1",
    "/settings/users/1/reset-password",
    "/settings/users/1/delete",
)


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def _password_from(html: str) -> str:
    pre = BeautifulSoup(html, "html.parser").find("pre", id="new-password-value")
    assert pre is not None, html
    return pre.get_text().strip()


def _tag(node: object) -> Tag:
    assert isinstance(node, Tag), node
    return node


def _user_row(db: sqlite3.Connection, email: str) -> sqlite3.Row:
    row: sqlite3.Row | None = db.execute(
        "SELECT * FROM users WHERE lower(email) = lower(?) AND deleted_at IS NULL", (email,)
    ).fetchone()
    assert row is not None
    return row


def _add(admin_client: TestClient, email: str, *, admin: bool = False, hx: bool = True) -> str:
    data = {"email": email, "name": "Alice"}
    if admin:
        data["is_admin"] = "on"
    resp = admin_client.post("/settings/users", data=data, headers=HX if hx else {})
    assert resp.status_code == 200, resp.text
    return _password_from(resp.text)


def _live_sessions(db: sqlite3.Connection, user_id: int) -> int:
    row = db.execute(
        "SELECT count(*) FROM sessions WHERE user_id = ? AND revoked_at IS NULL", (user_id,)
    ).fetchone()
    return int(row[0])


# --- access control -------------------------------------------------------


@pytest.mark.parametrize("path", ADMIN_PATHS_GET)
def test_non_admin_get_is_404(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 404


@pytest.mark.parametrize("path", ADMIN_PATHS_POST)
def test_non_admin_post_is_404_even_without_csrf(client: TestClient, path: str) -> None:
    resp = client.post(path, data={}, headers={"X-CSRF-Token": "bogus"})
    assert resp.status_code == 404


def test_non_admin_404_matches_unknown_route_body(client: TestClient) -> None:
    guarded = client.get("/settings/users")
    unknown = client.get("/settings/does-not-exist-anywhere")
    assert guarded.status_code == unknown.status_code == 404
    assert "Users" not in _tag(BeautifulSoup(guarded.text, "html.parser").title).get_text()


def test_non_admin_htmx_gets_404_flash(client: TestClient) -> None:
    resp = client.get("/settings/users", headers=HX)
    assert resp.status_code == 404


def test_lookalike_path_is_not_guarded(client: TestClient) -> None:
    # /settings/usersX is not under the admin subtree (plain 404 from routing).
    assert client.get("/settings/usersX").status_code == 404


@pytest.mark.parametrize("path", ADMIN_PATHS_GET)
def test_anonymous_is_redirected_to_login(anon_client: TestClient, path: str) -> None:
    resp = anon_client.get(path, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("/auth/login")


def test_users_tab_hidden_for_members(client: TestClient) -> None:
    member = BeautifulSoup(client.get("/settings").text, "html.parser")
    assert member.find(id="tab-users") is None


def test_users_tab_shown_for_admins(admin_client: TestClient) -> None:
    admin = BeautifulSoup(admin_client.get("/settings").text, "html.parser")
    tab = admin.find(id="tab-users")
    assert tab is not None
    assert _tag(tab)["href"] == "/settings/users"


# --- list -----------------------------------------------------------------


def test_admin_lists_live_users(admin_client: TestClient, db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO users (name, email, deleted_at) VALUES ('gone', 'gone@x.test', '2026-01-01')"
    )
    resp = admin_client.get("/settings/users")
    assert resp.status_code == 200
    soup = BeautifulSoup(resp.text, "html.parser")
    assert soup.find(id="user-row-1") is not None
    assert "gone@x.test" not in resp.text
    assert _tag(soup.find(id="tab-users"))["aria-selected"] == "true"
    assert _tag(soup.find(id="user-row-1")).find(string=re.compile("You")) is not None
    # No Remove action on your own row (ADR-0073 §4).
    assert soup.find("form", attrs={"action": "/settings/users/1/delete"}) is None
    assert soup.find("script", src=re.compile("users-admin.js")) is not None


# --- create ---------------------------------------------------------------


def test_create_user_shows_password_once(admin_client: TestClient, db: sqlite3.Connection) -> None:
    resp = admin_client.post(
        "/settings/users", data={"email": " New@Example.TEST ", "name": ""}, headers=HX
    )
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    password = _password_from(resp.text)
    assert len(password) == 22
    soup = BeautifulSoup(resp.text, "html.parser")
    oob = soup.find(id="users-table")
    assert _tag(oob).get("hx-swap-oob") == "true"
    assert "new@example.test" in _tag(oob).get_text()

    row = _user_row(db, "new@example.test")
    assert row["name"] == "new"
    assert row["is_admin"] == 0
    assert row["must_change_password"] == 1
    assert row["password_hash"] != password
    assert _passwords.verify_password(password, row["password_hash"])
    cats = db.execute(
        "SELECT name FROM categories WHERE user_id = ? AND is_system = 1 ORDER BY name",
        (row["id"],),
    ).fetchall()
    assert [c["name"] for c in cats] == ["Reconciliation", "Transit"]

    # Plaintext appears nowhere in the DB (audit rows included).
    dump = "\n".join(db.iterdump())
    assert password not in dump
    # Not shown again on the next page load.
    assert password not in admin_client.get("/settings/users").text


def test_create_user_audited_with_actor(admin_client: TestClient, db: sqlite3.Connection) -> None:
    _add(admin_client, "audit@example.test", admin=True)
    row = _user_row(db, "audit@example.test")
    assert row["is_admin"] == 1
    audit = db.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'users' AND entity_id = ?", (row["id"],)
    ).fetchall()
    assert len(audit) == 1
    assert audit[0]["operation"] == "create"
    assert audit[0]["actor_user_id"] == 1
    assert audit[0]["user_id"] == 1
    assert "password_hash" not in json.loads(audit[0]["new_json"])
    cat_actors = db.execute(
        "SELECT a.actor_user_id FROM audit_log a JOIN categories c ON c.id = a.entity_id "
        "WHERE a.entity_type = 'categories' AND c.user_id = ?",
        (row["id"],),
    ).fetchall()
    assert [r[0] for r in cat_actors] == [1, 1]


def test_created_user_can_log_in(
    admin_client: TestClient, anon_client: TestClient, db: sqlite3.Connection
) -> None:
    password = _add(admin_client, "fresh@example.test")
    resp = anon_client.post(
        "/auth/login",
        data={"email": "fresh@example.test", "password": password},
        follow_redirects=False,
    )
    assert resp.status_code == 303


def test_create_duplicate_email_case_insensitive(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    _add(admin_client, "dup@example.test")
    resp = admin_client.post("/settings/users", data={"email": "DUP@Example.test"}, headers=HX)
    assert resp.status_code == 422
    assert DUPLICATE_EMAIL_MESSAGE in resp.text
    assert "new-password-value" not in resp.text
    n = db.execute("SELECT count(*) FROM users WHERE lower(email) = 'dup@example.test'").fetchone()
    assert n[0] == 1


def test_create_reuses_email_of_removed_user(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    _add(admin_client, "again@example.test")
    uid = _user_row(db, "again@example.test")["id"]
    assert admin_client.post(f"/settings/users/{uid}/delete", headers=HX).status_code == 200
    _add(admin_client, "again@example.test")


def test_create_invalid_email_non_htmx_rerenders_page(admin_client: TestClient) -> None:
    resp = admin_client.post("/settings/users", data={"email": "nope", "name": "N"})
    assert resp.status_code == 422
    soup = BeautifulSoup(resp.text, "html.parser")
    assert _tag(soup.find("h1")).get_text() == "Users"
    assert _tag(soup.find("input", attrs={"name": "email"}))["value"] == "nope"


def test_create_non_htmx_renders_page_with_toast(admin_client: TestClient) -> None:
    resp = admin_client.post("/settings/users", data={"email": "plain@example.test"})
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    soup = BeautifulSoup(resp.text, "html.parser")
    assert _tag(soup.find("h1")).get_text() == "Users"
    assert soup.find(id="new-password-toast") is not None
    assert _tag(soup.find(id="users-table")).get("hx-swap-oob") is None


# --- edit -----------------------------------------------------------------


def test_edit_form_htmx_and_full_page(admin_client: TestClient) -> None:
    frag = admin_client.get("/settings/users/1/edit", headers=HX)
    assert frag.status_code == 200
    form = _tag(BeautifulSoup(frag.text, "html.parser").find(id="user-edit-form"))
    assert form["hx-post"] == "/settings/users/1"
    page = admin_client.get("/settings/users/1/edit")
    assert page.status_code == 200
    assert "<html" in page.text
    assert 'hx-post="/settings/users/1"' not in page.text


def test_edit_missing_user_is_404(admin_client: TestClient) -> None:
    assert admin_client.get("/settings/users/999/edit").status_code == 404
    assert admin_client.post("/settings/users/999", data={"email": "a@b.test"}).status_code == 404


def test_edit_updates_and_audits(admin_client: TestClient, db: sqlite3.Connection) -> None:
    _add(admin_client, "bob@example.test")
    uid = _user_row(db, "bob@example.test")["id"]
    resp = admin_client.post(
        f"/settings/users/{uid}",
        data={"email": "Robert@Example.test", "name": "Robert", "is_admin": "on"},
        headers=HX,
    )
    assert resp.status_code == 200
    assert "robert@example.test" in resp.text
    assert "flash-success" in resp.text
    row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    assert (row["email"], row["name"], row["is_admin"]) == ("robert@example.test", "Robert", 1)
    audit = db.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'users' AND entity_id = ? "
        "AND operation = 'update'",
        (uid,),
    ).fetchone()
    assert audit["actor_user_id"] == 1


def test_edit_non_htmx_redirects(admin_client: TestClient) -> None:
    resp = admin_client.post(
        "/settings/users/1",
        data={"email": "owner@example.test", "name": "Owner", "is_admin": "on"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings/users"


def test_edit_duplicate_email_htmx_retargets_form(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    _add(admin_client, "carol@example.test")
    resp = admin_client.post(
        "/settings/users/1", data={"email": "CAROL@example.test", "is_admin": "on"}, headers=HX
    )
    assert resp.status_code == 422
    assert resp.headers["hx-retarget"] == "#user-edit-form"
    assert DUPLICATE_EMAIL_MESSAGE in resp.text


def test_edit_invalid_email_non_htmx(admin_client: TestClient) -> None:
    resp = admin_client.post("/settings/users/1", data={"email": "bad", "is_admin": "on"})
    assert resp.status_code == 422
    assert "<html" in resp.text


def test_demote_last_admin_refused(admin_client: TestClient, db: sqlite3.Connection) -> None:
    resp = admin_client.post(
        "/settings/users/1", data={"email": "owner@example.test", "name": "o"}, headers=HX
    )
    assert resp.status_code == 409
    assert resp.headers["hx-reswap"] == "none"
    assert LAST_ADMIN_DEMOTE_MESSAGE.replace("'", "&#39;") in resp.text
    assert db.execute("SELECT is_admin FROM users WHERE id = 1").fetchone()[0] == 1

    page = admin_client.post("/settings/users/1", data={"email": "owner@example.test"})
    assert page.status_code == 409


def test_self_demote_allowed_with_second_admin(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    _add(admin_client, "second@example.test", admin=True)
    resp = admin_client.post(
        "/settings/users/1", data={"email": "owner@example.test", "name": "o"}, headers=HX
    )
    assert resp.status_code == 200
    assert db.execute("SELECT is_admin FROM users WHERE id = 1").fetchone()[0] == 0
    # Admin surface disappears on the very next request.
    assert admin_client.get("/settings/users").status_code == 404


# --- reset password -------------------------------------------------------


def test_reset_password_revokes_sessions(admin_client: TestClient, db: sqlite3.Connection) -> None:
    old = _add(admin_client, "dave@example.test")
    uid = _user_row(db, "dave@example.test")["id"]
    db.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (uid,))
    issue_session(db, user_id=uid)
    issue_session(db, user_id=uid)
    assert _live_sessions(db, uid) == 2

    resp = admin_client.post(f"/settings/users/{uid}/reset-password", headers=HX)
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    new = _password_from(resp.text)
    assert new != old
    assert "signed out" in resp.text
    row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    assert row["must_change_password"] == 1
    assert _passwords.verify_password(new, row["password_hash"])
    assert _live_sessions(db, uid) == 0
    audit = db.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'users' AND entity_id = ? "
        "AND json_extract(new_json, '$.action') = 'reset_password'",
        (uid,),
    ).fetchone()
    assert audit["operation"] == "update"
    assert audit["actor_user_id"] == 1
    assert json.loads(audit["new_json"])["sessions_revoked"] == 2
    assert new not in "\n".join(db.iterdump())


def test_reset_password_non_htmx_and_missing(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    assert admin_client.post("/settings/users/999/reset-password").status_code == 404
    assert admin_client.post("/settings/users/999/reset-password", headers=HX).status_code == 404
    _add(admin_client, "gus@example.test")
    uid = _user_row(db, "gus@example.test")["id"]
    resp = admin_client.post(f"/settings/users/{uid}/reset-password")
    assert resp.status_code == 200
    assert BeautifulSoup(resp.text, "html.parser").find(id="new-password-toast") is not None


def test_reset_own_password_signs_admin_out(admin_client: TestClient) -> None:
    resp = admin_client.post("/settings/users/1/reset-password", headers=HX)
    assert resp.status_code == 200
    follow = admin_client.get("/settings/users", follow_redirects=False)
    assert follow.status_code == 302


# --- remove ---------------------------------------------------------------


def test_remove_user_soft_deletes_and_revokes(
    admin_client: TestClient, anon_client: TestClient, db: sqlite3.Connection
) -> None:
    password = _add(admin_client, "erin@example.test")
    uid = _user_row(db, "erin@example.test")["id"]
    issue_session(db, user_id=uid)

    resp = admin_client.post(f"/settings/users/{uid}/delete", headers=HX)
    assert resp.status_code == 200
    assert (
        "erin@example.test"
        not in _tag(BeautifulSoup(resp.text, "html.parser").find(id="users-table")).get_text()
    )
    assert "flash-success" in resp.text
    row = db.execute("SELECT deleted_at FROM users WHERE id = ?", (uid,)).fetchone()
    assert row["deleted_at"] is not None
    assert _live_sessions(db, uid) == 0
    audit = db.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'users' AND entity_id = ? "
        "AND operation = 'delete'",
        (uid,),
    ).fetchone()
    assert audit["actor_user_id"] == 1
    assert audit["new_json"] is None

    login = anon_client.post(
        "/auth/login",
        data={"email": "erin@example.test", "password": password},
        follow_redirects=False,
    )
    assert login.status_code == 401


def test_remove_non_htmx_redirects(admin_client: TestClient, db: sqlite3.Connection) -> None:
    _add(admin_client, "fay@example.test")
    uid = _user_row(db, "fay@example.test")["id"]
    resp = admin_client.post(f"/settings/users/{uid}/delete", follow_redirects=False)
    assert resp.status_code == 303


def test_remove_self_refused(admin_client: TestClient, db: sqlite3.Connection) -> None:
    _add(admin_client, "other-admin@example.test", admin=True)
    resp = admin_client.post("/settings/users/1/delete", headers=HX)
    assert resp.status_code == 409
    assert SELF_DELETE_MESSAGE.replace("'", "&#39;") in resp.text
    assert db.execute("SELECT deleted_at FROM users WHERE id = 1").fetchone()[0] is None
    assert admin_client.post("/settings/users/1/delete").status_code == 409


def test_remove_other_admin_allowed(admin_client: TestClient, db: sqlite3.Connection) -> None:
    # Over HTTP the actor is always a live admin, so removing *another* admin
    # never hits the last-admin rule (that path is covered in service tests).
    _add(admin_client, "co-admin@example.test", admin=True)
    target = _user_row(db, "co-admin@example.test")["id"]
    resp = admin_client.post(f"/settings/users/{target}/delete", headers=HX)
    assert resp.status_code == 200
    assert (
        db.execute(
            "SELECT count(*) FROM users WHERE is_admin = 1 AND deleted_at IS NULL"
        ).fetchone()[0]
        == 1
    )


def test_remove_missing_is_404(admin_client: TestClient) -> None:
    assert admin_client.post("/settings/users/999/delete").status_code == 404
