"""Invite routes: authz, CSRF, HX shapes, DB and audit (T-UR20a, ADR-0134 section 1, ADR-0106).

Admin routes under ``/settings/users/invites`` and the public landing ``/invite/{token}``.
Bodies are inspected only through the UI map; the page behaviour is in
``tests/integration/web/test_invites_ui.py``.
"""

from __future__ import annotations

import hashlib
import sqlite3

import pytest
from fastapi.testclient import TestClient

from tests.contract._audit import audit_count
from tests.contract.conftest import covers
from tests.contract.web_helpers_t_ut04e import HX
from tests.ui_map import _html, auth, settings as ui

pytest_plugins = ["tests.contract.web_support_t_ut04e"]  # admin_client, client, anon_client, db

EMAIL = "invitee@example.test"
ADMIN_POST = (
    "/settings/users/invites",
    "/settings/users/invites/1/resend",
    "/settings/users/invites/1/revoke",
)


def _invites(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT count(*) FROM invites").fetchone()[0])


def _create(admin: TestClient) -> str:
    r = admin.post("/settings/users/invites", data={"email": EMAIL, "role": "member"}, headers=HX)
    assert r.status_code == 200
    return _html.text_of(r.text, ui.invite_link_value).strip().rsplit("/invite/", 1)[1]


@covers("GET /settings/users/invites/new", "GET /settings/users/invites/{invite_id}/revoke")
@pytest.mark.parametrize(
    "path", ("/settings/users/invites/new", "/settings/users/invites/1/revoke")
)
def test_non_admin_get_is_404_and_anonymous_goes_to_login(
    client: TestClient, anon_client: TestClient, path: str
) -> None:
    assert client.get(path, headers=HX).status_code == 404
    anon = anon_client.get(path, follow_redirects=False)
    assert anon.status_code == 302
    assert anon.headers["location"].startswith("/auth/login")


@covers(
    "POST /settings/users/invites",
    "POST /settings/users/invites/{invite_id}/resend",
    "POST /settings/users/invites/{invite_id}/revoke",
)
@pytest.mark.parametrize("path", ADMIN_POST)
def test_non_admin_post_is_404_and_changes_nothing(
    client: TestClient, db: sqlite3.Connection, path: str
) -> None:
    r = client.post(path, data={"email": EMAIL}, headers={"X-CSRF-Token": "bogus"})
    assert r.status_code == 404
    assert _invites(db) == 0


@covers(
    "POST /settings/users/invites",
    "POST /settings/users/invites/{invite_id}/resend",
    "POST /settings/users/invites/{invite_id}/revoke",
)
@pytest.mark.parametrize("path", ADMIN_POST)
def test_admin_post_without_csrf_token_is_403(
    admin_raw_client: TestClient, db: sqlite3.Connection, path: str
) -> None:
    r = admin_raw_client.post(path, data={"email": EMAIL})
    assert r.status_code == 403
    assert _invites(db) == 0


@covers("GET /settings/users/invites/new", "POST /settings/users/invites")
def test_create_dialog_and_create_audit(admin_client: TestClient, db: sqlite3.Connection) -> None:
    dialog = admin_client.get("/settings/users/invites/new", headers=HX)
    assert dialog.status_code == 200
    assert dialog.headers["hx-retarget"] == "#modal-root"
    token = _create(admin_client)
    row = db.execute("SELECT id, token_hash FROM invites").fetchone()
    assert row["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert audit_count(db, "invites", "create") == 1


@covers(
    "GET /settings/users/invites/{invite_id}/revoke",
    "POST /settings/users/invites/{invite_id}/resend",
    "POST /settings/users/invites/{invite_id}/revoke",
)
def test_resend_and_revoke_audit_and_unknown_invite(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    _create(admin_client)
    invite_id = int(db.execute("SELECT id FROM invites").fetchone()[0])
    confirm = admin_client.get(f"/settings/users/invites/{invite_id}/revoke", headers=HX)
    assert confirm.status_code == 200
    assert _html.exists(confirm.text, ui.revoke_invite_confirm)
    assert (
        admin_client.post(f"/settings/users/invites/{invite_id}/resend", headers=HX).status_code
        == 200
    )
    assert (
        admin_client.post(f"/settings/users/invites/{invite_id}/revoke", headers=HX).status_code
        == 200
    )
    assert audit_count(db, "invites", "update") == 2
    assert admin_client.get("/settings/users/invites/999/revoke", headers=HX).status_code == 404
    gone = admin_client.post(f"/settings/users/invites/{invite_id}/revoke", headers=HX)
    assert gone.status_code == 409


@covers("GET /invite/{token}", "POST /invite/{token}")
def test_landing_is_public_and_accept_requires_csrf(
    admin_client: TestClient, anon_client: TestClient, db: sqlite3.Connection
) -> None:
    token = _create(admin_client)
    page = anon_client.get(f"/invite/{token}")
    assert page.status_code == 200
    assert _html.exists(page.text, auth.invite_create)
    assert anon_client.get("/invite/unknown").status_code == 200
    forged = anon_client.post(
        f"/invite/{token}",
        data={"name": "N", "password": "x", "password_confirm": "x"},
        headers={"X-CSRF-Token": "forged"},
        follow_redirects=False,
    )
    assert forged.status_code == 403
    assert db.execute("SELECT used_at FROM invites").fetchone()[0] is None
