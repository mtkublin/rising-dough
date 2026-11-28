"""A dialog save with a required form value missing never fails silently (Q18, CLAUDE.md).

FastAPI answers a missing ``Form(...)`` value with a ``RequestValidationError`` before the
dialog handler runs. For an HTMX caller that is a 422 flash in the live region with
``HX-Reswap: none``: the dialog stays open with the typed values, nothing is stored, and no
event closes it. Non-HTMX callers keep the JSON ``detail`` body.
"""

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
from tests.contract.test_plan_support import audit_total
from tests.ui_map import _html, errors
from tests.ui_map.locator import by_id

USER_ID = 1
HX = {"HX-Request": "true"}
FLASH = errors.alert.inside(by_id("flash-region"))


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def cat_id(db: sqlite3.Connection) -> int:
    cat = categories_repo.create(
        db, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    )
    return cat.id


def _names(db: sqlite3.Connection) -> list[str]:
    return sorted(c.name for c in categories_repo.list_all(db, USER_ID, include_deleted=True))


def _assert_stays_open(r: object, text: str) -> None:
    assert r.status_code == 422  # type: ignore[attr-defined]  # object is a Response
    assert r.headers["HX-Reswap"] == "none"  # type: ignore[attr-defined]  # object is a Response
    assert "HX-Trigger" not in r.headers  # type: ignore[attr-defined]  # object is a Response
    assert "HX-Retarget" not in r.headers  # type: ignore[attr-defined]  # object is a Response
    body = r.text  # type: ignore[attr-defined]  # object is a Response
    assert " ".join(_html.text_of(body, FLASH).split()) == f"▲ {text}"


def test_new_category_without_name_or_direction(client: TestClient, db: sqlite3.Connection) -> None:
    before = (_names(db), audit_total(db))
    r = client.post("/categories", data={"name": "", "color": "default"}, headers=HX)
    _assert_stays_open(r, "Some fields need fixing: Name, Direction")
    assert (_names(db), audit_total(db)) == before


def test_new_category_with_empty_name(client: TestClient, db: sqlite3.Connection) -> None:
    before = (_names(db), audit_total(db))
    r = client.post("/categories", data={"name": "", "direction": "expense"}, headers=HX)
    _assert_stays_open(r, "Some fields need fixing: Name")
    assert (_names(db), audit_total(db)) == before


def test_edit_category_with_empty_name(
    client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    before = (_names(db), audit_total(db))
    r = client.post(f"/categories/{cat_id}", data={"name": ""}, headers=HX)
    _assert_stays_open(r, "Some fields need fixing: Name")
    assert (_names(db), audit_total(db)) == before


def test_budget_override_without_a_tier(
    client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    before = audit_total(db)
    r = client.post(
        f"/budget/rules/{cat_id}/overrides", data={"amount": "5", "month": "3"}, headers=HX
    )
    _assert_stays_open(r, "Some fields need fixing: Tier")
    assert audit_total(db) == before


def test_dev_dialog_without_a_note(client: TestClient) -> None:
    r = client.post("/dev/shell/dialog", data={"note": ""}, headers=HX)
    _assert_stays_open(r, "Some fields need fixing: Note")


def test_non_htmx_caller_keeps_the_json_detail(client: TestClient, db: sqlite3.Connection) -> None:
    before = (_names(db), audit_total(db))
    r = client.post("/categories", data={"name": ""}, headers={"Accept": "application/json"})
    assert r.status_code == 422
    assert "HX-Reswap" not in r.headers
    assert [(e["type"], e["loc"]) for e in r.json()["detail"]] == [
        ("missing", ["body", "name"]),
        ("missing", ["body", "direction"]),
    ]
    assert (_names(db), audit_total(db)) == before
