"""HTTP-level audit attribution for a logged-in non-admin user (T-D145, ADR-0122)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.services.audit_tail import OTHER_USER, audit_tail

USER_ID = 1  # the ``client`` fixture: user 1, non-admin


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    c = get_connection(_migrated)
    try:
        yield c
    finally:
        c.close()


def _rows(db: sqlite3.Connection, entity_type: str) -> list[sqlite3.Row]:
    return list(
        db.execute(
            "SELECT operation, user_id, actor_user_id FROM audit_log "
            "WHERE entity_type = ? ORDER BY id",
            (entity_type,),
        )
    )


def _assert_attributed(rows: list[sqlite3.Row], operations: list[str]) -> None:
    assert [r["operation"] for r in rows] == operations
    assert {(r["user_id"], r["actor_user_id"]) for r in rows} == {(USER_ID, USER_ID)}


def test_account_category_transaction_writes_are_attributed(
    client: TestClient, db: sqlite3.Connection
) -> None:
    assert client.post("/accounts", data={"name": "Main", "currency": "PLN"}).status_code == 200
    acc_id = db.execute("SELECT id FROM accounts").fetchone()[0]
    assert client.post(f"/accounts/{acc_id}", data={"name": "Main2"}).status_code == 200

    r = client.post("/categories", data={"name": "Rent", "direction": "expense"})
    assert r.status_code == 200
    cat_id = db.execute("SELECT id FROM categories WHERE name = 'Rent'").fetchone()[0]
    assert client.post(f"/categories/{cat_id}", data={"name": "Rent2"}).status_code == 200

    r = client.post(
        "/transactions",
        data={
            "operation_date": "2026-10-20",
            "category_id": cat_id,
            "account_id": acc_id,
            "amount": "12.34",
        },
    )
    assert r.status_code == 200
    txn_id = db.execute("SELECT id FROM transactions").fetchone()[0]
    assert client.post(f"/transactions/{txn_id}/delete").status_code == 200

    _assert_attributed(_rows(db, "account"), ["create", "update"])
    _assert_attributed(_rows(db, "category"), ["create", "update"])
    _assert_attributed(_rows(db, "transaction"), ["create", "delete"])

    own = [e for e in audit_tail(db, USER_ID, 20) if e["entity_type"] == "transaction"]
    assert own
    assert all(e["new"] != OTHER_USER and e["prev"] != OTHER_USER for e in own)
