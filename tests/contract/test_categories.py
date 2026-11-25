"""Categories routes: status, redirects, HX headers, CSRF, auth, DB and audit effect (T-UT04e).

ADR-0106 section 1. Bodies are inspected only through the UI map.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.domain.system_categories import RECONCILIATION_CATEGORY_NAME
from tests.contract.conftest import covers
from tests.contract.web_helpers_t_ut04e import (
    HX,
    USER_ID,
    audit_ops,
    fetch_all,
    make_category,
    system_category_id,
)
from tests.ui_map import _html, settings as ui

pytest_plugins = ["tests.contract.web_support_t_ut04e"]  # client, anon_client, raw_client

NEW = {"name": "Rent", "direction": "expense"}


@pytest.fixture
def cat_id(_migrated: Settings) -> int:
    return make_category(_migrated)


def _category(settings: Settings, name: str) -> dict[str, object]:
    rows = fetch_all(
        settings, "SELECT * FROM categories WHERE name = ? AND deleted_at IS NULL", (name,)
    )
    assert len(rows) == 1
    return rows[0]


# --- GET /categories ---------------------------------------------------------


# --- GET /categories/new ------------------------------------------------------


@covers("GET /categories/new")
def test_new_form_opens_the_dialog_shell(client: TestClient) -> None:
    # ADR-0152: transport changed from a self-targeting inline form to the dialog shell.
    r = client.get("/categories/new", headers=HX)
    assert r.status_code == 200
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert r.headers["HX-Reswap"] == "innerHTML"
    dialog = _html.resolve_one(r.text, ui.category_form)
    assert dialog["aria-labelledby"] == f"{dialog['id']}-title"
    form = dialog.find("form")
    assert form is not None
    assert form["hx-post"] == "/categories"
    assert form["hx-target"] == "#modal-root"
    assert _html.exists(r.text, ui.category_name)
    assert _html.exists(r.text, ui.category_expense)
    assert _html.exists(r.text, ui.category_income)
    assert _html.exists(r.text, ui.create_category)


@covers("GET /categories/new")
def test_new_form_requires_login(anon_client: TestClient) -> None:
    r = anon_client.get("/categories/new", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login")


# --- POST /categories ---------------------------------------------------------


@covers("POST /categories")
def test_create_persists_audits_and_reloads(client: TestClient, _migrated: Settings) -> None:
    r = client.post("/categories", data=NEW, headers=HX)
    assert r.status_code == 200
    assert "budget-stale" in json.loads(r.headers["HX-Trigger"])
    assert r.headers["HX-Reswap"] == "none"
    assert r.headers["HX-Refresh"] == "true"
    row = _category(_migrated, "Rent")
    assert (row["direction"], row["user_id"], row["color"]) == ("expense", USER_ID, None)
    assert ("create", row["id"]) in audit_ops(_migrated, "category")


@covers("POST /categories")
def test_create_colour_normalised_and_clear_wins(client: TestClient, _migrated: Settings) -> None:
    client.post("/categories", data={**NEW, "name": "Travel", "color": "#A3C2FF"})
    assert _category(_migrated, "Travel")["color"] == "#a3c2ff"
    client.post(
        "/categories", data={**NEW, "name": "Reset", "color": "#aabbcc", "clear_color": "1"}
    )
    assert _category(_migrated, "Reset")["color"] is None


@covers("POST /categories")
@pytest.mark.parametrize(
    "data",
    [
        {"name": "X", "direction": "bogus"},
        {"name": "X", "direction": "transit"},
        {"name": "X", "direction": "adjustment"},
        {"name": "   ", "direction": "expense"},
        {"name": "X", "direction": "expense", "color": "not-hex"},
    ],
)
def test_create_invalid_is_422_and_writes_nothing(
    client: TestClient, _migrated: Settings, data: dict[str, str]
) -> None:
    before = len(fetch_all(_migrated, "SELECT id FROM categories"))
    r = client.post("/categories", data=data)
    assert r.status_code == 422
    assert _html.exists(r.text, ui.category_form) or _html.exists(r.text, ui.category_name)
    assert len(fetch_all(_migrated, "SELECT id FROM categories")) == before


@covers("POST /categories")
def test_create_requires_csrf_and_login(
    raw_client: TestClient, anon_client: TestClient, _migrated: Settings
) -> None:
    before = len(fetch_all(_migrated, "SELECT id FROM categories"))
    assert raw_client.post("/categories", data=NEW).status_code == 403
    anon = anon_client.post("/categories", data=NEW, follow_redirects=False)
    assert anon.status_code in {302, 401}
    assert len(fetch_all(_migrated, "SELECT id FROM categories")) == before


# --- GET /categories/{id}/edit -----------------------------------------------


@covers("GET /categories/{category_id}/edit")
def test_edit_form_prefilled_without_direction_choice(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/categories/{cat_id}/edit", headers=HX)
    assert r.status_code == 200
    assert _html.resolve_one(r.text, ui.category_name)["value"] == "Groceries"
    assert not _html.exists(r.text, ui.category_expense)  # direction fixed once created


@covers("GET /categories/{category_id}/edit")
def test_edit_form_missing_is_404(client: TestClient) -> None:
    assert client.get("/categories/9999/edit").status_code == 404


@covers("GET /categories/{category_id}/edit")
def test_edit_form_requires_login(anon_client: TestClient, cat_id: int) -> None:
    r = anon_client.get(f"/categories/{cat_id}/edit", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login")


# --- POST /categories/{id} ----------------------------------------------------


@covers("POST /categories/{category_id}")
def test_update_renames_sets_and_clears_colour(
    client: TestClient, cat_id: int, _migrated: Settings
) -> None:
    r = client.post(f"/categories/{cat_id}", data={"name": "Food", "color": "#112233"})
    assert r.status_code == 200
    assert "budget-stale" in json.loads(r.headers["HX-Trigger"])
    assert _html.exists(r.text, ui.category_row(cat_id))
    row = _category(_migrated, "Food")
    assert row["color"] == "#112233"
    assert ("update", cat_id) in audit_ops(_migrated, "category")
    client.post(f"/categories/{cat_id}", data={"name": "Food", "clear_color": "1"})
    assert _category(_migrated, "Food")["color"] is None


@covers("POST /categories/{category_id}")
def test_update_invalid_and_missing(client: TestClient, cat_id: int, _migrated: Settings) -> None:
    assert client.post(f"/categories/{cat_id}", data={"name": "  "}).status_code == 422
    bad = client.post(f"/categories/{cat_id}", data={"name": "A", "color": "zzz"})
    assert bad.status_code == 422
    assert client.post("/categories/9999", data={"name": "X"}).status_code == 404
    assert _category(_migrated, "Groceries")["id"] == cat_id


@covers("POST /categories/{category_id}")
def test_update_requires_csrf(raw_client: TestClient, cat_id: int, _migrated: Settings) -> None:
    assert raw_client.post(f"/categories/{cat_id}", data={"name": "Hacked"}).status_code == 403
    assert _category(_migrated, "Groceries")["id"] == cat_id


# --- POST /categories/{id}/delete ----------------------------------------------


@covers("POST /categories/{category_id}/delete")
def test_delete_soft_deletes_and_audits(
    client: TestClient, cat_id: int, _migrated: Settings
) -> None:
    r = client.post(f"/categories/{cat_id}/delete", headers=HX)
    assert r.status_code == 200
    assert "budget-stale" in json.loads(r.headers["HX-Trigger"])
    row = fetch_all(_migrated, "SELECT deleted_at FROM categories WHERE id = ?", (cat_id,))[0]
    assert row["deleted_at"] is not None
    assert ("delete", cat_id) in audit_ops(_migrated, "category")


@covers("POST /categories/{category_id}/delete")
def test_delete_missing_system_and_csrf(
    client: TestClient, raw_client: TestClient, cat_id: int, _migrated: Settings
) -> None:
    assert client.post("/categories/9999/delete").status_code == 404
    system = system_category_id(_migrated, name=RECONCILIATION_CATEGORY_NAME)
    assert client.post(f"/categories/{system}/delete").status_code == 409
    assert raw_client.post(f"/categories/{cat_id}/delete").status_code == 403
    row = fetch_all(_migrated, "SELECT deleted_at FROM categories WHERE id = ?", (cat_id,))[0]
    assert row["deleted_at"] is None


# --- POST /categories/{id}/archive and /restore --------------------------------


@covers("GET /categories/{category_id}/archive")
def test_archive_form_is_a_confirm_dialog_with_usage(client: TestClient, cat_id: int) -> None:
    # New route (T-UR13): the confirm dialog the archive link opens; the POST below is unchanged.
    r = client.get(f"/categories/{cat_id}/archive", headers=HX)
    assert r.status_code == 200
    assert r.headers["HX-Retarget"] == "#modal-root"
    dialog = _html.resolve_one(r.text, ui.archive_dialog)
    assert dialog["aria-labelledby"] == f"{dialog['id']}-title"
    assert "Archive Groceries?" in _html.text_of(r.text, ui.archive_dialog)
    form = dialog.find("form")
    assert form is not None
    assert form["hx-post"] == f"/categories/{cat_id}/archive"
    assert _html.exists(r.text, ui.archive_confirm)


@covers("GET /categories/{category_id}/archive")
def test_archive_form_missing_is_404_and_needs_login(
    client: TestClient, anon_client: TestClient, cat_id: int
) -> None:
    assert client.get("/categories/9999/archive").status_code == 404
    anon = anon_client.get(f"/categories/{cat_id}/archive", follow_redirects=False)
    assert anon.status_code == 302
    assert anon.headers["location"].startswith("/auth/login")


@covers("POST /categories/{category_id}/archive")
def test_archive_204_with_undo_toast_and_audit(
    client: TestClient, cat_id: int, _migrated: Settings
) -> None:
    r = client.post(f"/categories/{cat_id}/archive")
    assert r.status_code == 204
    payload = json.loads(r.headers["HX-Trigger"])
    assert payload["toast"] == {
        "variant": "success",
        "message": "Category archived",
        "undo_url": f"/categories/{cat_id}/restore",
    }
    assert payload["settings-categories-stale"] is True
    assert payload["budget-stale"] is True
    row = fetch_all(_migrated, "SELECT deleted_at FROM categories WHERE id = ?", (cat_id,))[0]
    assert row["deleted_at"] is not None
    assert ("delete", cat_id) in audit_ops(_migrated, "category")


@covers("POST /categories/{category_id}/archive")
def test_archive_missing_system_double_and_csrf(
    client: TestClient, raw_client: TestClient, cat_id: int, _migrated: Settings
) -> None:
    assert client.post("/categories/99999/archive").status_code == 404
    system = system_category_id(_migrated, name=RECONCILIATION_CATEGORY_NAME)
    assert client.post(f"/categories/{system}/archive").status_code == 403
    assert raw_client.post(f"/categories/{cat_id}/archive").status_code == 403
    assert client.post(f"/categories/{cat_id}/archive").status_code == 204
    assert client.post(f"/categories/{cat_id}/archive").status_code == 404


@covers("POST /categories/{category_id}/archive")
def test_archive_requires_login(anon_client: TestClient, cat_id: int) -> None:
    r = anon_client.post(f"/categories/{cat_id}/archive", follow_redirects=False)
    assert r.status_code in {302, 401}


@covers("POST /categories/{category_id}/restore")
def test_restore_after_archive(client: TestClient, cat_id: int, _migrated: Settings) -> None:
    client.post(f"/categories/{cat_id}/archive")
    r = client.post(f"/categories/{cat_id}/restore")
    assert r.status_code == 204
    payload = json.loads(r.headers["HX-Trigger"])
    assert payload["toast"] == {"variant": "success", "message": "Category restored"}
    row = fetch_all(_migrated, "SELECT deleted_at FROM categories WHERE id = ?", (cat_id,))[0]
    assert row["deleted_at"] is None
    assert ("undelete", cat_id) in audit_ops(_migrated, "category")


@covers("POST /categories/{category_id}/restore")
def test_restore_live_missing_and_csrf(
    client: TestClient, raw_client: TestClient, cat_id: int
) -> None:
    assert client.post(f"/categories/{cat_id}/restore").status_code == 404
    assert client.post("/categories/99999/restore").status_code == 404
    assert raw_client.post(f"/categories/{cat_id}/restore").status_code == 403
