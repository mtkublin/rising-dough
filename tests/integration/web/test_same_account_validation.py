"""T-D153: same source and destination account is a 422, never a 500."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    transactions as transactions_repo,
)

USER_ID = 1


@pytest.fixture
def ctx(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(conn, USER_ID, NewAccount(name="Main", currency="PLN"))
        other = accounts_repo.create(conn, USER_ID, NewAccount(name="Other", currency="PLN"))
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
        )
        transit = categories_repo.create(
            conn, USER_ID, NewCategory(name="Move", direction=Direction.TRANSIT)
        )
        pl = planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=date(2026, 10, 15),
                category_id=cat.id,
                account_id=acc.id,
                amount=50000,
                dest_account_id=other.id,
            ),
        )
        txn = transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=date(2026, 10, 15),
                category_id=cat.id,
                account_id=acc.id,
                amount=5000,
            ),
        )
        return {
            "acc": acc.id,
            "other": other.id,
            "cat": cat.id,
            "transit": transit.id,
            "pl": pl.id,
            "txn": txn.id,
        }
    finally:
        conn.close()


def _count(settings: Settings, table: str) -> int:
    conn = get_connection(settings)
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608
    finally:
        conn.close()


def _form(ctx: dict[str, int], **extra: object) -> dict[str, object]:
    return {
        "operation_date": "2026-11-01",
        "category_id": ctx["cat"],
        "account_id": ctx["acc"],
        "amount": "10",
        **extra,
    }


def test_planned_create_same_accounts_is_422_and_writes_nothing(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    before = _count(_migrated, "planned_transactions")
    r = client.post("/planned", data=_form(ctx, dest_account_id=ctx["acc"]))
    assert r.status_code == 422
    assert "dest_account_id" in r.text
    assert "must differ" in r.text
    assert _count(_migrated, "planned_transactions") == before


def test_planned_update_same_accounts_is_422_and_keeps_row(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    r = client.post(
        f"/planned/{ctx['pl']}", data=_form(ctx, dest_account_id=ctx["acc"], amount="77")
    )
    assert r.status_code == 422
    assert "must differ" in r.text
    conn = get_connection(_migrated)
    try:
        row = planned_repo.find_by_id(conn, USER_ID, ctx["pl"])
        assert row is not None
        assert row.amount == 50000
    finally:
        conn.close()


def test_planned_update_onto_stored_dest_is_422(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(f"/planned/{ctx['pl']}", data=_form(ctx, account_id=ctx["other"]))
    assert r.status_code == 422
    assert "must differ" in r.text


def test_transaction_create_transit_same_accounts_is_422(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    before = _count(_migrated, "transactions")
    r = client.post(
        "/transactions",
        data=_form(ctx, category_id=ctx["transit"], dest_account_id=ctx["acc"]),
    )
    assert r.status_code == 422
    assert "must differ" in r.text
    assert _count(_migrated, "transactions") == before


def test_transaction_update_same_accounts_is_422(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(f"/transactions/{ctx['txn']}", data=_form(ctx, dest_account_id=ctx["acc"]))
    assert r.status_code == 422
    assert "must differ" in r.text
