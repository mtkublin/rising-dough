"""Audit-log coverage integration test (ADR-0019).

Every mutating repository function writes exactly one audit row with
correct ``entity_type`` / ``entity_id`` / ``operation`` plus matching
``prev_json`` / ``new_json`` null-shape per operation kind.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import date

import pytest

from budget_planner.domain.accounts import PatchAccount
from budget_planner.domain.transactions import PatchTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    transactions as txn_repo,
)

USER_ID = 1

pytestmark = pytest.mark.integration


def _audit(conn: sqlite3.Connection, entity_type: str, entity_id: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT entity_type, entity_id, operation, prev_json, new_json "
            "FROM audit_log WHERE entity_type=? AND entity_id=? ORDER BY id ASC",
            (entity_type, entity_id),
        )
    )


def test_create_writes_create_audit_row_with_null_prev(
    conn: sqlite3.Connection, make_account: Callable[..., int]
) -> None:
    account_id = make_account(name="Checking")
    rows = _audit(conn, "account", account_id)
    assert len(rows) == 1
    assert rows[0]["operation"] == "create"
    assert rows[0]["prev_json"] is None
    assert rows[0]["new_json"] is not None
    payload = json.loads(rows[0]["new_json"])
    assert payload["name"] == "Checking"


def test_update_captures_prev_and_new_json(
    conn: sqlite3.Connection, make_account: Callable[..., int]
) -> None:
    account_id = make_account(name="A")
    accounts_repo.update(conn, USER_ID, account_id, PatchAccount(name="B"))

    rows = _audit(conn, "account", account_id)
    assert [r["operation"] for r in rows] == ["create", "update"]
    update_row = rows[1]
    assert update_row["prev_json"] is not None
    assert update_row["new_json"] is not None
    prev = json.loads(update_row["prev_json"])
    new = json.loads(update_row["new_json"])
    assert prev["name"] == "A"
    assert new["name"] == "B"


def test_soft_delete_logs_delete_operation(
    conn: sqlite3.Connection, make_account: Callable[..., int]
) -> None:
    account_id = make_account()
    accounts_repo.soft_delete(conn, USER_ID, account_id)
    ops = [r["operation"] for r in _audit(conn, "account", account_id)]
    assert ops[-1] == "delete"


def test_undelete_logs_undelete_operation(
    conn: sqlite3.Connection, make_account: Callable[..., int]
) -> None:
    account_id = make_account()
    accounts_repo.soft_delete(conn, USER_ID, account_id)
    accounts_repo.undelete(conn, USER_ID, account_id)
    ops = [r["operation"] for r in _audit(conn, "account", account_id)]
    assert ops == ["create", "delete", "undelete"]


def test_transaction_update_writes_matching_audit(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
    make_transaction: Callable[..., int],
) -> None:
    txn_id = make_transaction(
        account_id=make_account(),
        category_id=make_category(),
        amount=1000,
        operation_date=date(2026, 2, 1),
    )
    txn_repo.update(conn, USER_ID, txn_id, PatchTransaction(amount=2000))

    rows = _audit(conn, "transaction", txn_id)
    assert [r["operation"] for r in rows] == ["create", "update"]
    new = json.loads(rows[1]["new_json"])
    assert new["amount"] == 2000
