"""Tests for the reconciliation service (T-026)."""

from __future__ import annotations

import sqlite3
from datetime import date
from unittest.mock import patch

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import accounts, audit as audit_repo, categories, transactions
from budget_planner.services import balance, reconciliation
from budget_planner.services.reconciliation import (
    AccountNotFoundError,
    CannotReconcileDeletedAccountError,
    CategoryDirectionMismatchError,
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
    txn = reconciliation.reconcile(
        conn, USER_ID, account_id=seed["checking"], actual_balance_minor=140_000, today=_TODAY
    )
    assert txn.amount == 10_000
    assert balance.derive_balance(conn, USER_ID, seed["checking"]) == 140_000


def test_negative_delta(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    txn = reconciliation.reconcile(
        conn, USER_ID, account_id=seed["checking"], actual_balance_minor=120_000, today=_TODAY
    )
    assert txn.amount == -10_000
    assert balance.derive_balance(conn, USER_ID, seed["checking"]) == 120_000


def test_zero_delta_raises(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    with pytest.raises(NoAdjustmentNeededError):
        reconciliation.reconcile(
            conn, USER_ID, account_id=seed["checking"], actual_balance_minor=130_000, today=_TODAY
        )


def test_unknown_account(conn: sqlite3.Connection) -> None:
    with pytest.raises(AccountNotFoundError):
        reconciliation.reconcile(
            conn, USER_ID, account_id=9999, actual_balance_minor=1, today=_TODAY
        )


def test_deleted_account(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    accounts.soft_delete(conn, USER_ID, seed["checking"])
    with pytest.raises(CannotReconcileDeletedAccountError):
        reconciliation.reconcile(
            conn, USER_ID, account_id=seed["checking"], actual_balance_minor=140_000, today=_TODAY
        )


def test_missing_system_category(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    # Hard delete the Reconciliation category.
    cat = categories.find_by_name(conn, USER_ID, "Reconciliation")
    assert cat is not None
    conn.execute("DELETE FROM categories WHERE id = ?", (cat.id,))
    with pytest.raises(MissingSystemCategoryError):
        reconciliation.reconcile(
            conn, USER_ID, account_id=seed["checking"], actual_balance_minor=140_000, today=_TODAY
        )


def test_audit_entry_written(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    txn = reconciliation.reconcile(
        conn, USER_ID, account_id=seed["checking"], actual_balance_minor=140_000, today=_TODAY
    )
    entries = audit_repo.list_entries(conn, "transaction", txn.id)
    assert len(entries) == 1
    assert entries[0].operation.value == "create"
    assert entries[0].prev_json is None
    assert entries[0].new_json is not None


def test_description_default(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    txn = reconciliation.reconcile(
        conn, USER_ID, account_id=seed["checking"], actual_balance_minor=140_000, today=_TODAY
    )
    assert txn.description == f"auto-reconciliation {_TODAY.isoformat()}"


def test_description_with_note(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    txn = reconciliation.reconcile(
        conn,
        USER_ID,
        account_id=seed["checking"],
        actual_balance_minor=140_000,
        today=_TODAY,
        note="bank mobile app",
    )
    assert txn.description == f"auto-reconciliation {_TODAY.isoformat()} — bank mobile app"


def test_operation_date_is_today(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    txn = reconciliation.reconcile(
        conn, USER_ID, account_id=seed["checking"], actual_balance_minor=140_000, today=_TODAY
    )
    assert txn.operation_date == _TODAY


@pytest.mark.parametrize("actual", [50_000, 125_000, 1_000_000])
def test_post_condition_round_trip(
    conn: sqlite3.Connection, seed: dict[str, int], actual: int
) -> None:
    reconciliation.reconcile(
        conn, USER_ID, account_id=seed["checking"], actual_balance_minor=actual, today=_TODAY
    )
    assert balance.derive_balance(conn, USER_ID, seed["checking"]) == actual


def test_repeated_second_call_zero_delta(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    reconciliation.reconcile(
        conn, USER_ID, account_id=seed["checking"], actual_balance_minor=140_000, today=_TODAY
    )
    with pytest.raises(NoAdjustmentNeededError):
        reconciliation.reconcile(
            conn, USER_ID, account_id=seed["checking"], actual_balance_minor=140_000, today=_TODAY
        )


def test_negative_balance_account(conn: sqlite3.Connection) -> None:
    acct = accounts.create(
        conn, USER_ID, NewAccount(name="Credit Card", currency="PLN", opening_balance=0)
    ).id
    txn = reconciliation.reconcile(
        conn, USER_ID, account_id=acct, actual_balance_minor=-50_000, today=_TODAY
    )
    assert txn.amount == -50_000
    assert balance.derive_balance(conn, USER_ID, acct) == -50_000


def _count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])


def test_rollback_on_failure(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    """The INSERT succeeds, the paired audit write fails: nothing may persist (ADR-0019)."""
    before_txns = _count(conn)
    before_audit = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    with (
        patch(
            "budget_planner.repositories._shared.write_audit",
            side_effect=RuntimeError("boom"),
        ),
        pytest.raises(RuntimeError, match="boom"),
    ):
        reconciliation.reconcile(
            conn, USER_ID, account_id=seed["checking"], actual_balance_minor=140_000, today=_TODAY
        )
    assert _count(conn) == before_txns
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == before_audit
    assert balance.derive_balance(conn, USER_ID, seed["checking"]) == 130_000


def _category(conn: sqlite3.Connection, name: str, direction: Direction) -> int:
    return categories.create(conn, USER_ID, NewCategory(name=name, direction=direction)).id


@pytest.mark.parametrize(
    ("direction", "target"),
    [
        (Direction.EXPENSE, 150_000),  # delta > 0 with an expense category (Q-005 B1)
        (Direction.INCOME, 50_000),  # delta < 0 with an income category (Q-005 B2)
    ],
)
def test_category_contradicting_delta_is_rejected(
    conn: sqlite3.Connection, seed: dict[str, int], direction: Direction, target: int
) -> None:
    cat = _category(conn, "Mismatch", direction)
    before = _count(conn)
    with pytest.raises(CategoryDirectionMismatchError):
        reconciliation.reconcile(
            conn,
            USER_ID,
            account_id=seed["checking"],
            actual_balance_minor=target,
            today=_TODAY,
            category_id=cat,
        )
    assert _count(conn) == before
    assert balance.derive_balance(conn, USER_ID, seed["checking"]) == 130_000


@pytest.mark.parametrize(
    ("direction", "target", "amount"),
    [
        (Direction.INCOME, 150_000, 20_000),
        (Direction.EXPENSE, 50_000, 80_000),
    ],
)
def test_matching_category_reaches_typed_balance(
    conn: sqlite3.Connection, seed: dict[str, int], direction: Direction, target: int, amount: int
) -> None:
    cat = _category(conn, "Match", direction)
    txn = reconciliation.reconcile(
        conn,
        USER_ID,
        account_id=seed["checking"],
        actual_balance_minor=target,
        today=_TODAY,
        category_id=cat,
    )
    assert txn.amount == amount
    assert balance.derive_balance(conn, USER_ID, seed["checking"]) == target


def test_other_users_rows_untouched_on_mismatch(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    other = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES ('O', 'o@example.com', 'x')"
    ).lastrowid
    assert other is not None
    before = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id = ?", (other,)
    ).fetchone()[0]
    cat = _category(conn, "Mismatch", Direction.EXPENSE)
    with pytest.raises(CategoryDirectionMismatchError):
        reconciliation.reconcile(
            conn,
            USER_ID,
            account_id=seed["checking"],
            actual_balance_minor=150_000,
            today=_TODAY,
            category_id=cat,
        )
    after = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id = ?", (other,)
    ).fetchone()[0]
    assert after == before
