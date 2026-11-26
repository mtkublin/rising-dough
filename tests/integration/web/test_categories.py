"""T-033 categories router."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.system_categories import RECONCILIATION_CATEGORY_NAME
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
)
from tests.ui_map import _html, errors, settings as ui
from tests.ui_map.locator import Locator, by_id

USER_ID = 1


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def _names(db: sqlite3.Connection) -> list[str]:
    """Every category name incl. soft-deleted, sorted (row-count proxy with identity)."""
    return sorted(c.name for c in categories_repo.list_all(db, USER_ID, include_deleted=True))


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


def _flat(html: str, loc: Locator) -> str:
    return " ".join(_html.text_of(html, loc).split())


def test_new_form(client: TestClient) -> None:
    r = client.get("/categories/new", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert _html.exists(r.text, ui.category_expense)
    # Default: expense direction and the "default colour" radio are preselected.
    fields = _html.submitted_fields(_html.form_of(r.text, ui.category_name))
    assert ("direction", "expense") in fields
    assert ("color", "default") in fields


def test_create(client: TestClient) -> None:
    r = client.post("/categories", data={"name": "Rent", "direction": "expense"})
    assert r.status_code == 200
    assert "Rent" in _html.text_of(r.text, ui.any_category_row)
    assert "budget-stale" in r.headers["HX-Trigger"]


# -- a live category name is unique per user (T-UR00b, requirements F1.6) --

_DUPLICATE = "▲ A category with this name already exists"


def _audit_count(db: sqlite3.Connection) -> int:
    db.commit()  # end any read snapshot so the app's writes are visible
    return int(db.execute("SELECT count(*) FROM audit_log").fetchone()[0])


def test_create_duplicate_name_is_422_under_the_name_field_and_writes_nothing(
    client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    names, audits = _names(db), _audit_count(db)
    r = client.post("/categories", data={"name": "Groceries", "direction": "expense"})
    assert r.status_code == 422
    assert _html.error_lines(r.text)["field-name-error"] == _DUPLICATE
    assert _names(db) == names
    assert _audit_count(db) == audits
    # The create form's name field is marked invalid and points at its error line (a
    # whitespace-trimmed ``required`` once glued ``requiredaria-invalid`` into one attribute).
    field = _html.resolve_one(r.text, by_id("field-name"))
    assert field.get("aria-invalid") == "true"
    assert field.get("aria-describedby") == "field-name-error"
    assert field.has_attr("required")


def test_rename_onto_another_categorys_name_is_422_and_changes_nothing(
    client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    rent = categories_repo.create(
        db, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id
    names, audits = _names(db), _audit_count(db)
    r = client.post(f"/categories/{rent}", data={"name": "Groceries"})
    assert r.status_code == 422
    assert _html.error_lines(r.text)["field-name-error"] == _DUPLICATE
    assert _names(db) == names
    assert _audit_count(db) == audits


def test_resaving_the_own_name_with_a_new_colour_is_not_a_duplicate(
    client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    r = client.post(f"/categories/{cat_id}", data={"name": "Groceries", "color": "#ef4444"})
    assert r.status_code == 200
    assert _color(db, cat_id) == "#ef4444"


def test_another_users_same_name_does_not_block_create(
    client: TestClient, db: sqlite3.Connection
) -> None:
    db.execute("INSERT INTO users (id, name) VALUES (2, 'other')")
    db.commit()
    categories_repo.create(db, 2, NewCategory(name="Pets", direction=Direction.EXPENSE))
    r = client.post("/categories", data={"name": "Pets", "direction": "expense"})
    assert r.status_code == 200
    assert _names(db).count("Pets") == 1  # the caller's own; the other user's row is not listed
    assert [c.name for c in categories_repo.list_all(db, 2)].count("Pets") == 1


def test_an_archived_same_name_does_not_block_create(
    client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    """Archive is a soft delete; the unique index covers live rows only (ADR-0136)."""
    categories_repo.soft_delete(db, USER_ID, cat_id)
    r = client.post("/categories", data={"name": "Groceries", "direction": "expense"})
    assert r.status_code == 200
    assert _names(db).count("Groceries") == 2


def test_create_bad_direction(client: TestClient, db: sqlite3.Connection) -> None:
    before = _names(db)
    r = client.post("/categories", data={"name": "X", "direction": "bogus"})
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-direction-error": "▲ invalid direction",
    }
    assert _names(db) == before


def test_create_rejects_transit_direction(client: TestClient, db: sqlite3.Connection) -> None:
    """T-115 — ``transit`` and ``adjustment`` are reserved for system seeds."""
    before = _names(db)
    for direction in ("transit", "adjustment"):
        r = client.post("/categories", data={"name": "Nope", "direction": direction})
        assert r.status_code == 422, direction
        assert _html.error_lines(r.text) == {
            "field-direction-error": "▲ invalid direction",
        }
    assert _names(db) == before


def test_create_blank_name(client: TestClient, db: sqlite3.Connection) -> None:
    before = _names(db)
    r = client.post("/categories", data={"name": "   ", "direction": "expense"})
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-name-error": "▲ Name is required",
    }
    assert _names(db) == before


def test_edit(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/categories/{cat_id}/edit")
    assert r.status_code == 200
    form = _html.form_of(r.text, ui.category_name)
    assert form["hx-post"] == f"/categories/{cat_id}"
    assert ("name", "Groceries") in _html.submitted_fields(form)


def test_edit_dialog_prints_the_usage_text(
    client: TestClient, cat_id: int, db: sqlite3.Connection
) -> None:
    plain = client.get(f"/categories/{cat_id}/edit")
    assert plain.status_code == 200
    assert "\u2193 expense \u00b7 fixed once created" in _flat(plain.text, ui.category_form)

    acc = accounts_repo.create(db, USER_ID, NewAccount(name="Main", currency="PLN")).id
    planned_repo.create(
        db,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 10), category_id=cat_id, account_id=acc, amount=100
        ),
    )
    used = client.get(f"/categories/{cat_id}/edit")
    assert "\u2193 expense \u00b7 locked by 1 planned" in _flat(used.text, ui.category_form)
    archive = client.get(f"/categories/{cat_id}/archive")
    assert "Its 1 planned and budget history stay" in _flat(archive.text, ui.archive_dialog)


def test_edit_404(client: TestClient) -> None:
    r = client.get("/categories/9999/edit")
    assert r.status_code == 404
    assert _html.text_of(r.text, errors.heading) == "Not found"


def test_update(client: TestClient, cat_id: int, db: sqlite3.Connection) -> None:
    r = client.post(f"/categories/{cat_id}", data={"name": "Food"})
    assert r.status_code == 200
    assert "Food" in _html.text_of(r.text, ui.any_category_row)
    stored = categories_repo.find_by_id(db, USER_ID, cat_id)
    assert stored is not None
    assert stored.name == "Food"
    assert stored.direction is Direction.EXPENSE
    assert "Food" in _html.text_of(r.text, ui.category_row(cat_id))


def test_update_404(client: TestClient, db: sqlite3.Connection) -> None:
    before = _names(db)
    r = client.post("/categories/9999", data={"name": "X"})
    assert r.status_code == 404
    assert _html.text_of(r.text, errors.heading) == "Not found"
    assert _names(db) == before


def test_update_blank(client: TestClient, cat_id: int, db: sqlite3.Connection) -> None:
    r = client.post(f"/categories/{cat_id}", data={"name": "  "})
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-name-error": "▲ Name is required",
    }
    stored = categories_repo.find_by_id(db, USER_ID, cat_id)
    assert stored is not None
    assert stored.name == "Groceries"


def test_delete(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/categories/{cat_id}/delete")
    assert r.status_code == 200
    assert "budget-stale" in r.headers["HX-Trigger"]


def test_delete_404(client: TestClient, db: sqlite3.Connection) -> None:
    before = _names(db)
    r = client.post("/categories/9999/delete")
    assert r.status_code == 404
    assert _html.text_of(r.text, errors.heading) == "Not found"
    assert _names(db) == before


def test_delete_system_blocked(client: TestClient, _migrated: Settings) -> None:
    conn = get_connection(_migrated)
    try:
        transit = next(c for c in categories_repo.list_all(conn, USER_ID) if c.is_system)
    finally:
        conn.close()
    r = client.post(f"/categories/{transit.id}/delete")
    assert r.status_code == 409
    assert r.text == "system categories cannot be deleted"
    conn = get_connection(_migrated)
    try:
        still = categories_repo.find_by_id(conn, USER_ID, transit.id)
    finally:
        conn.close()
    assert still is not None
    assert still.deleted_at is None


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


def test_create_invalid_hex_422(client: TestClient, db: sqlite3.Connection) -> None:
    before = _names(db)
    r = client.post(
        "/categories",
        data={"name": "Bad", "direction": "expense", "color": "not-hex"},
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-color-error": "▲ invalid color 'not-hex'; expected 6-digit hex like #a3c2ff",
    }
    assert _names(db) == before


def test_update_set_color_then_clear(
    client: TestClient, cat_id: int, db: sqlite3.Connection
) -> None:
    set_resp = client.post(
        f"/categories/{cat_id}",
        data={"name": "Groceries", "color": "#112233"},
    )
    assert set_resp.status_code == 200
    colored = categories_repo.find_by_id(db, USER_ID, cat_id)
    assert colored is not None
    assert colored.color == "#112233"
    clear_resp = client.post(
        f"/categories/{cat_id}",
        data={"name": "Groceries", "clear_color": "1"},
    )
    assert clear_resp.status_code == 200
    cleared = categories_repo.find_by_id(db, USER_ID, cat_id)
    assert cleared is not None
    assert cleared.color is None


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


def test_archive_missing_404(client: TestClient, db: sqlite3.Connection) -> None:
    before = _names(db)
    r = client.post("/categories/99999/archive")
    assert r.status_code == 404
    assert _html.text_of(r.text, errors.heading) == "Not found"
    assert _names(db) == before


def test_archive_system_403(client: TestClient, _migrated: Settings) -> None:
    conn = get_connection(_migrated)
    try:
        recon = categories_repo.find_by_name(conn, USER_ID, RECONCILIATION_CATEGORY_NAME)
    finally:
        conn.close()
    assert recon is not None
    r = client.post(f"/categories/{recon.id}/archive")
    assert r.status_code == 403
    assert r.text == "system categories cannot be archived"
    conn = get_connection(_migrated)
    try:
        still = categories_repo.find_by_id(conn, USER_ID, recon.id)
    finally:
        conn.close()
    assert still is not None
    assert still.deleted_at is None


def test_archive_double_post_404(client: TestClient, cat_id: int, db: sqlite3.Connection) -> None:
    r1 = client.post(f"/categories/{cat_id}/archive")
    assert r1.status_code == 204
    archived = categories_repo.find_by_id(db, USER_ID, cat_id, include_deleted=True)
    assert archived is not None
    assert archived.deleted_at is not None
    r2 = client.post(f"/categories/{cat_id}/archive")
    assert r2.status_code == 404
    assert _html.text_of(r2.text, errors.heading) == "Not found"


def test_restore_after_archive(client: TestClient, cat_id: int, db: sqlite3.Connection) -> None:
    client.post(f"/categories/{cat_id}/archive")
    r = client.post(f"/categories/{cat_id}/restore")
    assert r.status_code == 204
    trigger = r.headers.get("HX-Trigger")
    assert trigger is not None
    restored = categories_repo.find_by_id(db, USER_ID, cat_id)
    assert restored is not None
    assert restored.deleted_at is None
    assert restored.name == "Groceries"


def test_restore_without_archive_404(
    client: TestClient, cat_id: int, db: sqlite3.Connection
) -> None:
    r = client.post(f"/categories/{cat_id}/restore")
    assert r.status_code == 404
    assert _html.text_of(r.text, errors.heading) == "Not found"
    live = categories_repo.find_by_id(db, USER_ID, cat_id)
    assert live is not None
    assert live.deleted_at is None


def test_create_reloads_page_without_swap(client: TestClient) -> None:
    # T-D150: the Settings category list has no region that refetches on a trigger.
    r = client.post(
        "/categories",
        data={"name": "Pets", "direction": "expense"},
        headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/settings"},
    )
    assert r.status_code == 200
    assert r.headers["HX-Reswap"] == "none"
    assert r.headers["HX-Refresh"] == "true"
    assert "budget-stale" in r.headers["HX-Trigger"]


def test_new_form_posts_to_the_collection_through_the_dialog_shell(client: TestClient) -> None:
    # ADR-0152: the old self-targeting form (reset on submit) is now the dialog shell.
    r = client.get("/categories/new", headers={"HX-Request": "true"})
    assert r.headers["HX-Retarget"] == "#modal-root"
    form = _html.form_of(r.text, ui.category_name)
    assert form["hx-post"] == "/categories"
    assert form["hx-target"] == "#modal-root"
    assert not form.has_attr("data-reset-on-submit")


def test_archive_dialog_closes_on_the_dialog_close_event(client: TestClient, cat_id: int) -> None:
    r = client.post(f"/categories/{cat_id}/archive")
    assert r.status_code == 204
    assert json.loads(r.headers["HX-Trigger"])["dialog-close"] is True


# -- the "default colour" radio posts color=default: the service clears the colour (T-UR13) --


def _audit(db: sqlite3.Connection, category_id: int) -> list[str]:
    db.commit()  # end any read snapshot so the app's writes are visible
    rows = db.execute(
        "SELECT operation FROM audit_log WHERE entity_type = 'category' AND entity_id = ? "
        "ORDER BY id",
        (category_id,),
    ).fetchall()
    return [str(r[0]) for r in rows]


def _color(db: sqlite3.Connection, category_id: int) -> str | None:
    db.commit()  # end any read snapshot so the app's writes are visible
    row = db.execute("SELECT color FROM categories WHERE id = ?", (category_id,)).fetchone()
    return None if row[0] is None else str(row[0])


def test_create_with_empty_colour_stores_null_and_audits(
    client: TestClient, db: sqlite3.Connection
) -> None:
    r = client.post(
        "/categories", data={"name": "Plain", "direction": "expense", "color": "default"}
    )
    assert r.status_code == 200
    row = db.execute("SELECT id, color, user_id FROM categories WHERE name = 'Plain'").fetchone()
    assert (row["color"], row["user_id"]) == (None, USER_ID)
    assert _audit(db, row["id"]) == ["create"]


def test_edit_with_empty_colour_clears_it_and_leaves_another_users_colour(
    client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    db.execute("INSERT INTO users (id, name) VALUES (2, 'other')")
    db.commit()
    other = categories_repo.create(
        db, 2, NewCategory(name="Groceries", direction=Direction.EXPENSE, color="#112233")
    ).id
    client.post(f"/categories/{cat_id}", data={"name": "Groceries", "color": "#ef4444"})
    assert _color(db, cat_id) == "#ef4444"

    r = client.post(f"/categories/{cat_id}", data={"name": "Groceries", "color": "default"})
    assert r.status_code == 200
    assert _color(db, cat_id) is None
    assert _audit(db, cat_id) == ["create", "update", "update"]
    assert _color(db, other) == "#112233"
    assert _audit(db, other) == ["create"]


def test_edit_with_a_real_colour_stores_it(
    client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    r = client.post(f"/categories/{cat_id}", data={"name": "Groceries", "color": "#A855F7"})
    assert r.status_code == 200
    assert _color(db, cat_id) == "#a855f7"
    assert _audit(db, cat_id) == ["create", "update"]


def test_edit_without_a_colour_field_keeps_the_stored_colour(
    client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    client.post(f"/categories/{cat_id}", data={"name": "Groceries", "color": "#ef4444"})
    client.post(f"/categories/{cat_id}", data={"name": "Food"})
    assert _color(db, cat_id) == "#ef4444"


def test_off_swatch_colour_survives_an_edit_round_trip(
    client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    db.execute("UPDATE categories SET color = '#112233' WHERE id = ?", (cat_id,))
    db.commit()
    page = client.get(f"/categories/{cat_id}/edit")
    form = _html.form_of(page.text, ui.category_name)
    fields = _html.submitted_fields(form)
    # D11-S: no swatch matches the hue, so the nearest one (green) is preselected and posted back
    assert ("color", "#22c55e") in fields

    posted = {name: ("Food" if name == "name" else value) for name, value in fields}
    r = client.post(f"/categories/{cat_id}", data=posted)
    assert r.status_code == 200
    row = db.execute("SELECT name, color FROM categories WHERE id = ?", (cat_id,)).fetchone()
    assert (row["name"], row["color"]) == ("Food", "#112233")
    assert _audit(db, cat_id) == ["create", "update"]


# -- D11-S: the dialog preselects the swatch nearest to a non-swatch hue; a plain save keeps it --
def _takeaway(db: sqlite3.Connection) -> int:
    return categories_repo.create(
        db, USER_ID, NewCategory(name="Takeaway", direction=Direction.EXPENSE, color="#ff9f43")
    ).id


def test_saving_the_preselected_swatch_keeps_the_stored_hue(
    client: TestClient, db: sqlite3.Connection
) -> None:
    cid = _takeaway(db)
    r = client.post(f"/categories/{cid}", data={"name": "Takeaway", "color": "#f97316"})
    assert r.status_code == 200
    assert _color(db, cid) == "#ff9f43"


def test_picking_another_swatch_or_the_default_changes_the_colour(
    client: TestClient, db: sqlite3.Connection
) -> None:
    cid = _takeaway(db)
    client.post(f"/categories/{cid}", data={"name": "Takeaway", "color": "#ef4444"})
    assert _color(db, cid) == "#ef4444"
    client.post(f"/categories/{cid}", data={"name": "Takeaway", "color": "default"})
    assert _color(db, cid) is None


def test_renaming_with_the_preselected_swatch_keeps_the_hue_and_audits_the_update(
    client: TestClient, db: sqlite3.Connection
) -> None:
    cid = _takeaway(db)
    client.post(f"/categories/{cid}", data={"name": "Takeout", "color": "#f97316"})
    assert _color(db, cid) == "#ff9f43"
    assert _audit(db, cid) == ["create", "update"]
