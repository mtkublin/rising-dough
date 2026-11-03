"""Reconciliation integration test (ADR-0011).

Before-after derived balance invariant: after a reconcile, the derived
balance equals the user-asserted actual balance.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date

import pytest

from budget_planner.domain.enums import Direction
from budget_planner.repositories import audit as audit_repo
from budget_planner.services import balance as balance_service, reconciliation as reconcile_service

USER_ID = 1

pytestmark = pytest.mark.integration


def test_reconcile_computes_delta_from_derived_balance(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
    make_transaction: Callable[..., int],
) -> None:
    """Seed: opening 100, 40 of expense -> derived 60; actual 70 -> +10 adjustment."""
    account_id = make_account(name="Checking", opening_balance=10000)
    expense_id = make_category(name="Food")
    make_transaction(
        account_id=account_id,
        category_id=expense_id,
        amount=4000,
        operation_date=date(2026, 1, 10),
    )
    assert balance_service.derive_balance(conn, USER_ID, account_id) == 6000

    txn = reconcile_service.reconcile(
        conn,
        USER_ID,
        account_id,
        actual_balance_minor=7000,
        today=date(2026, 1, 15),
    )

    # Signed adjustment of +10.00 minor units.
    assert txn.amount == 1000

    # Derived balance now matches the asserted actual.
    assert balance_service.derive_balance(conn, USER_ID, account_id) == 7000


def test_reconcile_inserts_adjustment_under_reconciliation_category(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
) -> None:
    account_id = make_account(name="Checking", opening_balance=10000)
    make_category(name="placeholder")

    txn = reconcile_service.reconcile(
        conn,
        USER_ID,
        account_id,
        actual_balance_minor=15000,
        today=date(2026, 1, 15),
    )

    row = conn.execute(
        "SELECT c.direction FROM transactions t "
        "JOIN categories c ON c.id = t.category_id "
        "WHERE t.id = ?",
        (txn.id,),
    ).fetchone()
    assert row["direction"] == Direction.ADJUSTMENT.value


def test_reconcile_is_noop_when_delta_zero(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
) -> None:
    account_id = make_account(opening_balance=10000)
    with pytest.raises(reconcile_service.NoAdjustmentNeededError):
        reconcile_service.reconcile(
            conn,
            USER_ID,
            account_id,
            actual_balance_minor=10000,
            today=date(2026, 1, 15),
        )
    assert conn.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()["n"] == 0


def test_reconcile_writes_audit_row(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
) -> None:
    account_id = make_account(opening_balance=10000)
    txn = reconcile_service.reconcile(
        conn,
        USER_ID,
        account_id,
        actual_balance_minor=12000,
        today=date(2026, 1, 15),
    )
    entries = audit_repo.list_entries(conn, "transaction", txn.id)
    assert [e.operation.value for e in entries] == ["create"]
