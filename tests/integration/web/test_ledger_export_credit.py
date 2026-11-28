"""T-UR28: the export menu per Ledger tab and the credit-limit line (ADR-0134 §2, §6)."""

from __future__ import annotations

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
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from tests.ui_map import _html, entries, ledger

pytestmark = pytest.mark.integration

USER_ID = 1


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def test_planned_tab_export_follows_its_filters(client: TestClient) -> None:
    r = client.get("/ledger", params={"view": "planned", "q": "rent", "date_from": "2026-11-01"})
    query = "date_from=2026-11-01&q=rent"
    assert ledger.export_hrefs(r.text) == {
        "export as csv": f"/planned/export?{query}&format=csv",
        "export as parquet": f"/planned/export?{query}&format=parquet",
    }


def test_recurring_tab_has_no_export_menu(client: TestClient) -> None:
    r = client.get("/ledger", params={"view": "recurring"})
    assert not _html.exists(r.text, ledger.export_menu)


def test_edit_dialog_credit_line_is_the_service_value_and_alerts_over_limit(
    client: TestClient, db: sqlite3.Connection
) -> None:
    card = accounts_repo.create(
        db,
        USER_ID,
        NewAccount(name="Card", currency="PLN", is_liability=True, credit_limit_minor=1_000_00),
    )
    cat = categories_repo.create(db, USER_ID, NewCategory(name="Gear", direction=Direction.EXPENSE))
    txn = transactions_repo.create(
        db,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 11, 2),
            category_id=cat.id,
            account_id=card.id,
            amount=1_250_00,
            description="Drone",
        ),
    )
    r = client.get(f"/transactions/{txn.id}/edit", headers={"HX-Request": "true"})
    alert = _html.resolve_one(r.text, entries.credit_line).find("p")
    assert alert is not None
    assert alert.get("role") == "alert"
    assert _html.text_of(r.text, entries.credit_line) == (
        "▲ Card · 250.00 over the credit limit (1,000.00 left)"
    )
