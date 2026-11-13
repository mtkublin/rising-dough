"""Tests for the reconciliation service (T-026)."""

from __future__ import annotations

import sqlite3
from datetime import date
from unittest.mock import patch

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction, TransactionFilter
from budget_planner.repositories import accounts, audit as audit_repo, categories, transactions
from budget_planner.services import balance, reconciliation
from budget_planner.services.reconciliation import (
    AccountNotFoundError,
    CannotReconcileDeletedAccountError,
    MissingSystemCategoryError,
    NoAdjustmentNeededError,
)

USER_ID = 1


@pytest.fixture
def seed(conn: sqlite3.Connection) -> dict[str, int]:
    checking = accounts.create(
        conn, USER_ID, NewAccount(name="Checking", currency="PLN", opening_balance=100_000)
    ).id
    salary = categories.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    ).id
    transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 1, 10),
            category_id=salary,
            account_id=checking,
            amount=30_000,
        ),
    )
    return {"checking": checking, "salary": salary}


_TODAY = date(2026, 10, 23)


def test_positive_delta(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    txn = reconciliation.reconcile(conn, USER_ID, seed["checking"], 140_000, _TODAY)
    assert txn.amount == 10_000
    assert balance.derive_balance(conn, USER_ID, seed["checking"]) == 140_000


def test_negative_delta(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    txn = reconciliation.reconcile(conn, USER_ID, seed["checking"], 120_000, _TODAY)
    assert txn.amount == -10_000
    assert balance.derive_balance(conn, USER_ID, seed["checking"]) == 120_000


def test_zero_delta_raises(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    with pytest.raises(NoAdjustmentNeededError):
        reconciliation.reconcile(conn, USER_ID, seed["checking"], 130_000, _TODAY)


def test_unknown_account(conn: sqlite3.Connection) -> None:
    with pytest.raises(AccountNotFoundError):
        reconciliation.reconcile(conn, USER_ID, 9999, 1, _TODAY)


def test_deleted_account(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    accounts.soft_delete(conn, USER_ID, seed["checking"])
    with pytest.raises(CannotReconcileDeletedAccountError):
        reconciliation.reconcile(conn, USER_ID, seed["checking"], 140_000, _TODAY)


def test_missing_system_category(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    # Hard delete the Reconciliation category.
    cat = categories.find_by_name(conn, USER_ID, "Reconciliation")
    assert cat is not None
    conn.execute("DELETE FROM categories WHERE id = ?", (cat.id,))
    with pytest.raises(MissingSystemCategoryError):
        reconciliation.reconcile(conn, USER_ID, seed["checking"], 140_000, _TODAY)


def test_audit_entry_written(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    txn = reconciliation.reconcile(conn, USER_ID, seed["checking"], 140_000, _TODAY)
    entries = audit_repo.list_entries(conn, "transaction", txn.id)
    assert len(entries) == 1
    assert entries[0].operation.value == "create"
    assert entries[0].prev_json is None
    assert entries[0].new_json is not None


def test_description_default(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    txn = reconciliation.reconcile(conn, USER_ID, seed["checking"], 140_000, _TODAY)
    assert txn.description == f"auto-reconciliation {_TODAY.isoformat()}"


def test_description_with_note(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    txn = reconciliation.reconcile(
        conn, USER_ID, seed["checking"], 140_000, _TODAY, note="bank mobile app"
    )
    assert txn.description == f"auto-reconciliation {_TODAY.isoformat()} — bank mobile app"


def test_operation_date_is_today(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    txn = reconciliation.reconcile(conn, USER_ID, seed["checking"], 140_000, _TODAY)
    assert txn.operation_date == _TODAY


@pytest.mark.parametrize("actual", [50_000, 125_000, 1_000_000])
def test_post_condition_round_trip(
    conn: sqlite3.Connection, seed: dict[str, int], actual: int
) -> None:
    reconciliation.reconcile(conn, USER_ID, seed["checking"], actual, _TODAY)
    assert balance.derive_balance(conn, USER_ID, seed["checking"]) == actual


def test_repeated_second_call_zero_delta(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    reconciliation.reconcile(conn, USER_ID, seed["checking"], 140_000, _TODAY)
    with pytest.raises(NoAdjustmentNeededError):
        reconciliation.reconcile(conn, USER_ID, seed["checking"], 140_000, _TODAY)


def test_negative_balance_account(conn: sqlite3.Connection) -> None:
    acct = accounts.create(
        conn, USER_ID, NewAccount(name="Credit Card", currency="PLN", opening_balance=0)
    ).id
    txn = reconciliation.reconcile(conn, USER_ID, acct, -50_000, _TODAY)
    assert txn.amount == -50_000
    assert balance.derive_balance(conn, USER_ID, acct) == -50_000


def test_rollback_on_failure(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    before = len(transactions.list_filtered(conn, USER_ID, filters=TransactionFilter()))
    with (
        patch(
            "budget_planner.services.reconciliation.transactions_repo.create",
            side_effect=RuntimeError("boom"),
        ),
        pytest.raises(RuntimeError),
    ):
        reconciliation.reconcile(conn, USER_ID, seed["checking"], 140_000, _TODAY)
    after = len(transactions.list_filtered(conn, USER_ID, filters=TransactionFilter()))
    assert before == after
