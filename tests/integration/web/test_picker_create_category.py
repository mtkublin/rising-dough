"""T-UR68: the entry dialog's category picker creates a category in place."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import categories as categories_repo
from tests.ui_map import _html
from tests.ui_map.locator import by_id, role

USER_ID = 1
_DUPLICATE = "▲ A category with this name already exists"


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def _audits(db: sqlite3.Connection) -> list[tuple[str, str]]:
    db.commit()  # end any read snapshot so the app's writes are visible
    rows = db.execute(
        "SELECT entity_type, operation FROM audit_log WHERE entity_type = 'category' ORDER BY id"
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def _names(db: sqlite3.Connection, user_id: int = USER_ID) -> list[str]:
    return sorted(c.name for c in categories_repo.list_all(db, user_id, include_deleted=True))


def test_create_returns_the_new_option_and_writes_row_and_audit(
    client: TestClient, db: sqlite3.Connection
) -> None:
    before = _audits(db)
    r = client.post("/categories/picker", data={"name": "Zzz Test"})
    assert r.status_code == 200
    created = [c for c in categories_repo.list_all(db, USER_ID) if c.name == "Zzz Test"]
    assert len(created) == 1
    assert created[0].direction == Direction.EXPENSE
    option = _html.resolve_one(r.text, role("option"))
    assert option.get("data-value") == str(created[0].id)
    assert _html.text_of(r.text, role("option")).startswith("Zzz Test")
    assert _audits(db)[len(before) :] == [("category", "create")]


def test_duplicate_is_case_insensitive_422_with_the_field_error_and_no_row(
    client: TestClient, db: sqlite3.Connection
) -> None:
    categories_repo.create(db, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE))
    names, audits = _names(db), _audits(db)
    r = client.post("/categories/picker", data={"name": "groceries"})
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {"picker-create-error": _DUPLICATE}
    assert not _html.exists(r.text, role("option"))
    assert _names(db) == names
    assert _audits(db) == audits


def test_blank_name_is_422(client: TestClient, db: sqlite3.Connection) -> None:
    audits = _audits(db)
    r = client.post("/categories/picker", data={"name": "   "})
    assert r.status_code == 422
    assert "picker-create-error" in _html.error_lines(r.text)
    assert _audits(db) == audits


def test_another_users_same_name_does_not_block_and_is_not_touched(
    client: TestClient, db: sqlite3.Connection
) -> None:
    db.execute("INSERT INTO users (id, name) VALUES (2, 'other')")
    db.commit()
    categories_repo.create(db, 2, NewCategory(name="Pets", direction=Direction.EXPENSE))
    r = client.post("/categories/picker", data={"name": "Pets"})
    assert r.status_code == 200
    assert _names(db).count("Pets") == 1
    assert _names(db, 2).count("Pets") == 1


def test_the_picker_offers_a_post_button_instead_of_a_link(client: TestClient) -> None:
    r = client.get("/add?when=happened&dialog=1", headers={"HX-Request": "true"})
    assert r.status_code == 200
    button = _html.resolve_one(r.text, by_id("catpick-new-entry-create"))
    assert button.name == "button"
    assert button.get("hx-post") == "/categories/picker"
