"""T-033 categories router."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.system_categories import RECONCILIATION_CATEGORY_NAME
from budget_planner.repositories import categories as categories_repo

USER_ID = 1


@pytest.fixture
def cat_id(_migrated: Settings) -> int:
    conn = get_connection(_migrated)
    try:
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        )
        return cat.id
    finally:
        conn.close()


def test_index_redirects_to_settings(client: TestClient, cat_id: int) -> None:
    """T-070: ``/categories`` returns 302 to the Settings drawer tab."""
    r = client.get("/categories", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/settings?tab=categories"


def test_new_form(client: TestClient) -> None:
    r = client.get("/categories/new")
    assert r.status_code == 200
    assert 'name="direction"' in r.text


def test_create(client: TestClient) -> None:
    r = client.post("/categories", data={"name": "Rent", "direction": "expense"})
    assert r.status_code == 200
    assert "Rent" in r.text
    assert "budget-stale" in r.headers["HX-Trigger"]


def test_create_bad_direction(client: TestClient) -> None:
    r = client.post("/categories", data={"name": "X", "direction": "bogus"})
    assert r.status_code == 422


def test_create_rejects_transit_direction(client: TestClient) -> None:
    """T-115 — ``transit`` and ``adjustment`` are reserved for system seeds."""
    for direction in ("transit", "adjustment"):
        r = client.post("/categories", data={"name": "Nope", "direction": direction})
        assert r.status_code == 422, direction


def test_create_blank_name(client: TestClient) -> None:
    r = client.post("/categories", data={"name": "   ", "direction": "expense"})
    assert r.status_code == 422


def test_edit(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/categories/{cat_id}/edit")
    assert r.status_code == 200


def test_edit_404(client: TestClient) -> None:
    assert client.get("/categories/9999/edit").status_code == 404


def test_update(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/categories/{cat_id}", data={"name": "Food"})
    assert r.status_code == 200
    assert "Food" in r.text


def test_update_404(client: TestClient) -> None:
    assert client.post("/categories/9999", data={"name": "X"}).status_code == 404


def test_update_blank(client: TestClient, cat_id: int) -> None:
    assert client.post(f"/categories/{cat_id}", data={"name": "  "}).status_code == 422


def test_delete(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/categories/{cat_id}/delete")
    assert r.status_code == 200
    assert "budget-stale" in r.headers["HX-Trigger"]


def test_delete_404(client: TestClient) -> None:
    assert client.post("/categories/9999/delete").status_code == 404


def test_delete_system_blocked(client: TestClient, _migrated: Settings) -> None:
    conn = get_connection(_migrated)
    try:
        transit = next(c for c in categories_repo.list_all(conn, USER_ID) if c.is_system)
    finally:
        conn.close()
    r = client.post(f"/categories/{transit.id}/delete")
    assert r.status_code == 409


# -- ADR-0048 color override --------------------------------------------


def test_create_with_color(client: TestClient, _migrated: Settings) -> None:
    r = client.post(
        "/categories",
        data={"name": "Travel", "direction": "expense", "color": "#A3C2FF"},
    )
    assert r.status_code == 200
    conn = get_connection(_migrated)
    try:
        cat = categories_repo.find_by_name(conn, USER_ID, "Travel")
    finally:
        conn.close()
    assert cat is not None
    # Hex normalised to lowercase per ADR-0048.
    assert cat.color == "#a3c2ff"


def test_create_clear_color_wins_over_color_value(client: TestClient, _migrated: Settings) -> None:
    r = client.post(
        "/categories",
        data={
            "name": "Reset",
            "direction": "expense",
            "color": "#aabbcc",
            "clear_color": "1",
        },
    )
    assert r.status_code == 200
    conn = get_connection(_migrated)
    try:
        cat = categories_repo.find_by_name(conn, USER_ID, "Reset")
    finally:
        conn.close()
    assert cat is not None
    assert cat.color is None


def test_create_invalid_hex_422(client: TestClient) -> None:
    r = client.post(
        "/categories",
        data={"name": "Bad", "direction": "expense", "color": "not-hex"},
    )
    assert r.status_code == 422


def test_update_set_color_then_clear(client: TestClient, cat_id: int) -> None:
    set_resp = client.post(
        f"/categories/{cat_id}",
        data={"name": "Groceries", "color": "#112233"},
    )
    assert set_resp.status_code == 200
    clear_resp = client.post(
        f"/categories/{cat_id}",
        data={"name": "Groceries", "clear_color": "1"},
    )
    assert clear_resp.status_code == 200


# ---------------------------------------------------------------------------
# T-R44 — Archive + Restore (ADR-0056 §6)
# ---------------------------------------------------------------------------
def test_archive_category_204_with_undo_toast(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/categories/{cat_id}/archive")
    assert r.status_code == 204
    trigger = r.headers.get("HX-Trigger")
    assert trigger is not None
    payload = json.loads(trigger)
    assert "toast" in payload
    assert payload["toast"]["variant"] == "success"
    assert payload["toast"]["undo_url"] == f"/categories/{cat_id}/restore"
    assert payload.get("settings-categories-stale") is True


def test_archive_missing_404(client: TestClient) -> None:
    r = client.post("/categories/99999/archive")
    assert r.status_code == 404


def test_archive_system_403(client: TestClient, _migrated: Settings) -> None:
    conn = get_connection(_migrated)
    try:
        recon = categories_repo.find_by_name(conn, USER_ID, RECONCILIATION_CATEGORY_NAME)
    finally:
        conn.close()
    assert recon is not None
    r = client.post(f"/categories/{recon.id}/archive")
    assert r.status_code == 403


def test_archive_double_post_404(client: TestClient, cat_id: int) -> None:
    r1 = client.post(f"/categories/{cat_id}/archive")
    assert r1.status_code == 204
    r2 = client.post(f"/categories/{cat_id}/archive")
    assert r2.status_code == 404


def test_restore_after_archive(client: TestClient, cat_id: int) -> None:
    client.post(f"/categories/{cat_id}/archive")
    r = client.post(f"/categories/{cat_id}/restore")
    assert r.status_code == 204
    trigger = r.headers.get("HX-Trigger")
    assert trigger is not None


def test_restore_without_archive_404(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/categories/{cat_id}/restore")
    assert r.status_code == 404
