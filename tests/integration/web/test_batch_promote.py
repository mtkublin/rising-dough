"""Integration tests for the planned batch promote-due route and batch undo (T-R45, ADR-0056 §6)."""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
)

USER_ID = 1


@pytest.fixture
def seeded_ids(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        )
    finally:
        conn.close()
    return {"account_id": acc.id, "category_id": cat.id}


def test_planned_batch_promote_empty(client: TestClient) -> None:
    r = client.post("/planned/batch/promote-due")
    assert r.status_code == 204
    trigger = json.loads(r.headers["HX-Trigger"])
    assert "toast" in trigger


def test_planned_batch_promote_with_due_row(
    client: TestClient,
    seeded_ids: dict[str, int],
    _migrated: Settings,
) -> None:
    conn = get_connection(_migrated)
    try:
        planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=date(2026, 10, 20),
                category_id=seeded_ids["category_id"],
                account_id=seeded_ids["account_id"],
                amount=5_000,
                description="",
            ),
        )
    finally:
        conn.close()
    r = client.post("/planned/batch/promote-due")
    assert r.status_code == 204
    payload = json.loads(r.headers["HX-Trigger"])
    toast = payload["toast"]
    assert toast["undo_url"] == "/planned/batch/undo"
    assert len(toast["undo_payload"]["promoted_txn_ids"]) == 1


def test_planned_batch_undo_restores_state(
    client: TestClient,
    seeded_ids: dict[str, int],
    _migrated: Settings,
) -> None:
    conn = get_connection(_migrated)
    try:
        planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=date(2026, 10, 20),
                category_id=seeded_ids["category_id"],
                account_id=seeded_ids["account_id"],
                amount=5_000,
                description="",
            ),
        )
    finally:
        conn.close()
    r = client.post("/planned/batch/promote-due")
    payload = json.loads(r.headers["HX-Trigger"])
    txn_ids = payload["toast"]["undo_payload"]["promoted_txn_ids"]
    planned_ids = payload["toast"]["undo_payload"]["promoted_planned_ids"]
    undo = client.post(
        "/planned/batch/undo",
        data={
            "promoted_txn_ids": ",".join(str(i) for i in txn_ids),
            "promoted_planned_ids": ",".join(str(i) for i in planned_ids),
        },
    )
    assert undo.status_code == 204
    conn = get_connection(_migrated)
    try:
        promoted = conn.execute(
            "SELECT promoted_to_txn_id FROM planned_transactions WHERE id = ?",
            (planned_ids[0],),
        ).fetchone()
        txn = conn.execute(
            "SELECT deleted_at FROM transactions WHERE id = ?", (txn_ids[0],)
        ).fetchone()
    finally:
        conn.close()
    assert promoted["promoted_to_txn_id"] is None
    assert txn["deleted_at"] is not None
