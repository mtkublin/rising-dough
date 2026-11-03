"""Integration tests for batch promote-due routes (T-R45, ADR-0056 §6)."""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
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


def test_recurring_batch_promote_empty(client: TestClient) -> None:
    r = client.post("/recurring/batch/promote-due")
    assert r.status_code == 204
    trigger = json.loads(r.headers["HX-Trigger"])
    assert "toast" in trigger
    assert trigger["ledger-stale"] is True


def test_planned_batch_promote_empty(client: TestClient) -> None:
    r = client.post("/planned/batch/promote-due")
    assert r.status_code == 204
    trigger = json.loads(r.headers["HX-Trigger"])
    assert "toast" in trigger


def test_recurring_batch_promote_with_due_rule(
    client: TestClient,
    seeded_ids: dict[str, int],
    _migrated: Settings,
) -> None:
    conn = get_connection(_migrated)
    try:
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 10, 1),
                category_id=seeded_ids["category_id"],
                account_id=seeded_ids["account_id"],
                default_amount=1_000,
                default_description="",
            ),
        )
        recurring_repo.set_next_due(
            conn, USER_ID, rule.id, next_due=date(2026, 10, 20), last_promoted_date=None
        )
    finally:
        conn.close()
    r = client.post("/recurring/batch/promote-due")
    assert r.status_code == 204
    payload = json.loads(r.headers["HX-Trigger"])
    toast = payload["toast"]
    assert "undo_url" in toast
    assert toast["undo_url"] == "/recurring/batch/undo"
    assert "promoted_txn_ids" in toast["undo_payload"]
    assert len(toast["undo_payload"]["promoted_txn_ids"]) == 1


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


def test_recurring_batch_undo_restores_state(
    client: TestClient,
    seeded_ids: dict[str, int],
    _migrated: Settings,
) -> None:
    conn = get_connection(_migrated)
    try:
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 10, 1),
                category_id=seeded_ids["category_id"],
                account_id=seeded_ids["account_id"],
                default_amount=1_000,
                default_description="",
            ),
        )
        recurring_repo.set_next_due(
            conn, USER_ID, rule.id, next_due=date(2026, 10, 20), last_promoted_date=None
        )
    finally:
        conn.close()
    r = client.post("/recurring/batch/promote-due")
    payload = json.loads(r.headers["HX-Trigger"])
    txn_ids = payload["toast"]["undo_payload"]["promoted_txn_ids"]
    rule_ids = payload["toast"]["undo_payload"]["advanced_rule_ids"]
    undo = client.post(
        "/recurring/batch/undo",
        data={
            "promoted_txn_ids": ",".join(str(i) for i in txn_ids),
            "advanced_rule_ids": ",".join(str(i) for i in rule_ids),
        },
    )
    assert undo.status_code == 204
    undo_payload = json.loads(undo.headers["HX-Trigger"])
    assert undo_payload["toast"]["variant"] == "info"


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


def test_batch_undo_invalid_ids_422(client: TestClient) -> None:
    r = client.post(
        "/recurring/batch/undo",
        data={"promoted_txn_ids": "x,y", "advanced_rule_ids": ""},
    )
    assert r.status_code == 422
