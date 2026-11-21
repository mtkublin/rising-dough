"""T-Q210 (Q-004, ADR-0008 amendment 2026-11-21): transit shape on every write path."""

from __future__ import annotations

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

USER_ID = 1
NO_DEST = "transit requires a destination account"
_TABLES = {"/transactions": "transactions", "/planned": "planned_transactions"}


@pytest.fixture
def world(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        a = accounts_repo.create(
            conn, USER_ID, NewAccount(name="A", currency="PLN", opening_balance=1000)
        )
        b = accounts_repo.create(
            conn, USER_ID, NewAccount(name="B", currency="PLN", opening_balance=0)
        )
        tr = categories_repo.create(
            conn, USER_ID, NewCategory(name="Move", direction=Direction.TRANSIT)
        )
        ex = categories_repo.create(
            conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
        )
        return {"a": a.id, "b": b.id, "transit": tr.id, "expense": ex.id}
    finally:
        conn.close()


def _scalar(settings: Settings, sql: str, *params: int) -> int:
    conn = get_connection(settings)
    try:
        return int(conn.execute(sql, params).fetchone()[0])
    finally:
        conn.close()


def _form(world: dict[str, int], dest: str, cat: str = "transit") -> dict[str, str | int]:
    return {
        "operation_date": "2026-11-19",
        "category_id": world[cat],
        "account_id": world["a"],
        "amount": "10",
        "dest_account_id": dest,
    }


@pytest.mark.parametrize("route", ["/transactions", "/planned"])
def test_create_transit_without_destination_is_rejected(
    client: TestClient, world: dict[str, int], _migrated: Settings, route: str
) -> None:
    r = client.post(route, data=_form(world, ""))
    assert r.status_code == 422
    assert NO_DEST in r.text
    sql = f"SELECT COUNT(*) FROM {_TABLES[route]}"  # noqa: S608  # fixed table names from _TABLES
    assert _scalar(_migrated, sql) == 0
    for page in ("/accounts", "/today", "/forecast"):
        assert client.get(page).status_code == 200


@pytest.mark.parametrize("route", ["/transactions", "/planned"])
def test_create_transit_cross_currency_is_rejected(
    client: TestClient, world: dict[str, int], _migrated: Settings, route: str
) -> None:
    conn = get_connection(_migrated)
    try:
        eur = accounts_repo.create(
            conn, USER_ID, NewAccount(name="E", currency="EUR", opening_balance=0)
        ).id
    finally:
        conn.close()
    r = client.post(route, data=_form(world, str(eur)))
    assert r.status_code == 422
    assert "cross-currency" in r.text


@pytest.mark.parametrize("route", ["/transactions", "/planned"])
def test_create_transit_with_destination_persists(
    client: TestClient, world: dict[str, int], _migrated: Settings, route: str
) -> None:
    r = client.post(route, data=_form(world, str(world["b"])))
    assert r.status_code == 200
    sql = f"SELECT COUNT(*) FROM {_TABLES[route]} WHERE dest_account_id = ?"  # noqa: S608  # fixed table names from _TABLES
    assert _scalar(_migrated, sql, world["b"]) == 1


def test_update_to_transit_without_destination_is_rejected(
    client: TestClient, world: dict[str, int], _migrated: Settings
) -> None:
    conn = get_connection(_migrated)
    try:
        txn = transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=date(2026, 11, 19),
                category_id=world["expense"],
                account_id=world["a"],
                amount=500,
            ),
        )
    finally:
        conn.close()
    r = client.post(f"/transactions/{txn.id}", data=_form(world, ""))
    assert r.status_code == 422
    assert NO_DEST in r.text
    sql = "SELECT COUNT(*) FROM transactions WHERE id = ? AND category_id = ?"
    assert _scalar(_migrated, sql, txn.id, world["expense"]) == 1
    assert client.get("/accounts").status_code == 200


def test_update_planned_to_transit_without_destination_is_rejected(
    client: TestClient, world: dict[str, int], _migrated: Settings
) -> None:
    client.post("/planned", data=_form(world, "", cat="expense"))
    pid = _scalar(_migrated, "SELECT id FROM planned_transactions")
    r = client.post(f"/planned/{pid}", data=_form(world, ""))
    assert r.status_code == 422
    assert NO_DEST in r.text
    sql = "SELECT COUNT(*) FROM planned_transactions WHERE id = ? AND category_id = ?"
    assert _scalar(_migrated, sql, pid, world["expense"]) == 1


def test_reconcile_with_transit_category_is_rejected(
    client: TestClient, world: dict[str, int], _migrated: Settings
) -> None:
    r = client.post(
        f"/accounts/{world['a']}/reconcile",
        data={"actual_balance": "20", "category_id": str(world["transit"])},
    )
    assert r.status_code == 422
    assert NO_DEST in r.text
    sql = "SELECT COUNT(*) FROM transactions WHERE category_id = ?"
    assert _scalar(_migrated, sql, world["transit"]) == 0
    assert client.get("/accounts").status_code == 200
