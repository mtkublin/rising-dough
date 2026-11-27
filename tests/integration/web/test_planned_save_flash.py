"""A planned save from the new-entry dialog flashes, no page reload (T-UR96, ADR-0143)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import accounts as accounts_repo, categories as categories_repo
from tests.ui_map import _html, rd_shell

USER_ID = 1
PAGES = ["/today", "/ledger", "/ledger?tab=planned", "/plan", "/accounts"]


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


@pytest.mark.parametrize("page", PAGES)
def test_planned_save_answers_with_the_flash_and_no_reload(
    client: TestClient, db: sqlite3.Connection, page: str
) -> None:
    acc = accounts_repo.create(db, USER_ID, NewAccount(name="Main", currency="PLN"))
    cat = categories_repo.create(
        db, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    )
    r = client.post(
        "/planned",
        data={
            "category": str(cat.id),
            "account_id": str(acc.id),
            "amount": "12.34",
            "operation_date": "2026-12-01",
            "description": "flash-check",
        },
        headers={
            "HX-Request": "true",
            "HX-Target": "modal-root",
            "HX-Current-URL": f"http://testserver{page}",
        },
    )
    assert r.status_code == 200
    assert "HX-Refresh" not in r.headers
    flash = _html.resolve_one(r.text, rd_shell.flash_saved)
    assert "Planned entry saved" in flash.get_text()
    events = json.loads(r.headers["HX-Trigger"])
    assert events["forecast-stale"] is True
    assert events["ledger-stale"] is True
    row = db.execute(
        "SELECT amount, description FROM planned_transactions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert (row[0], row[1]) == (1234, "flash-check")
