"""Reset and delete confirm dialogs of ``/settings/users`` (T-UR14, ADR-0152).

Two GET routes open dialogs in ``#modal-root``; the blocked variant shows a service guard's own
message before the POST. Bodies are inspected only through the UI map.
"""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from budget_planner.services.users import SELF_DELETE_MESSAGE
from tests.contract.conftest import covers
from tests.contract.web_helpers_t_ut04e import HX
from tests.ui_map import _html, settings as ui
from tests.ui_map.locator import role

pytest_plugins = ["tests.contract.web_support_t_ut04e"]  # admin_client, client, anon_client, db


def _second_user(admin: TestClient, db: sqlite3.Connection) -> int:
    admin.post("/settings/users", data={"email": "second@example.test", "name": "Sam"}, headers=HX)
    row = db.execute("SELECT id FROM users WHERE email = 'second@example.test'").fetchone()
    return int(row[0])


@covers("GET /settings/users/{user_id}/delete")
def test_delete_dialog_confirms_with_hx_post_to_the_row(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    uid = _second_user(admin_client, db)
    r = admin_client.get(f"/settings/users/{uid}/delete", headers=HX)
    assert r.status_code == 200
    assert r.headers["hx-retarget"] == "#modal-root"
    assert r.headers["hx-reswap"] == "innerHTML"
    form = _html.resolve_one(r.text, ui.delete_dialog).find("form")
    assert form is not None
    assert form["hx-post"] == f"/settings/users/{uid}/delete"
    assert form["hx-target"] == f"#user-row-{uid}"
    assert db.execute("SELECT deleted_at FROM users WHERE id = ?", (uid,)).fetchone()[0] is None


@covers("GET /settings/users/{user_id}/delete")
def test_delete_dialog_for_yourself_is_blocked_with_the_service_message(
    admin_client: TestClient,
) -> None:
    r = admin_client.get("/settings/users/1/delete", headers=HX)
    assert r.status_code == 200
    assert SELF_DELETE_MESSAGE in _html.text_of(r.text, ui.delete_blocked)
    assert _html.resolve_one(r.text, ui.delete_blocked).find("form") is None


@covers("GET /settings/users/{user_id}/delete", "GET /settings/users/{user_id}/reset-password")
def test_dialogs_for_a_missing_user_are_404(admin_client: TestClient) -> None:
    assert admin_client.get("/settings/users/999/delete").status_code == 404
    assert admin_client.get("/settings/users/999/reset-password", headers=HX).status_code == 404


@covers("GET /settings/users/{user_id}/delete", "GET /settings/users/{user_id}/reset-password")
def test_dialogs_are_404_for_a_non_admin(client: TestClient) -> None:
    assert client.get("/settings/users/1/delete").status_code == 404
    assert client.get("/settings/users/1/reset-password", headers=HX).status_code == 404


@covers("GET /settings/users/{user_id}/reset-password")
def test_reset_dialog_posts_to_the_reset_route(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    uid = _second_user(admin_client, db)
    r = admin_client.get(f"/settings/users/{uid}/reset-password", headers=HX)
    assert r.status_code == 200
    assert r.headers["hx-retarget"] == "#modal-root"
    form = _html.resolve_one(r.text, role("alertdialog", "reset")).find("form")
    assert form is not None
    assert form["hx-post"] == f"/settings/users/{uid}/reset-password"
