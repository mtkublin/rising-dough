"""Promotion flow integration test: planned → actual.

Covers ADR-0012 end-to-end: a successful promote inserts a transaction,
stamps ``planned.promoted_to_txn_id``, writes audit rows for both, and
rollback leaves no partial state on error.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date
from unittest import mock

import pytest

from budget_planner.repositories import audit as audit_repo
from budget_planner.services.planned import PromotionEdits, promote_to_actual

USER_ID = 1

pytestmark = pytest.mark.integration


def test_promote_one_off_planned_inserts_txn_and_stamps_planned(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
    make_planned: Callable[..., int],
) -> None:
    account_id = make_account(name="Checking")
    category_id = make_category(name="Groceries")
    planned_id = make_planned(
        account_id=account_id,
        category_id=category_id,
        amount=5000,
        operation_date=date(2026, 1, 15),
    )

    txn = promote_to_actual(conn, USER_ID, planned_id, PromotionEdits())

    # Transaction linked back to the planned row.
    assert txn.promoted_from_planned_id == planned_id
    # Planned row stamped.
    row = conn.execute(
        "SELECT promoted_to_txn_id FROM planned_transactions WHERE id = ?",
        (planned_id,),
    ).fetchone()
    assert row["promoted_to_txn_id"] == txn.id


def test_promote_applies_user_edits_to_amount_and_date(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
    make_planned: Callable[..., int],
) -> None:
    planned_id = make_planned(
        account_id=make_account(name="Main"),
        category_id=make_category(name="Rent"),
        amount=5000,
        operation_date=date(2026, 1, 15),
    )

    txn = promote_to_actual(
        conn,
        USER_ID,
        planned_id,
        PromotionEdits(amount_minor=5500, operation_date=date(2026, 1, 17)),
    )

    assert txn.amount == 5500
    assert txn.operation_date == date(2026, 1, 17)


def test_promote_writes_audit_rows_on_both_planned_and_transaction(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
    make_planned: Callable[..., int],
) -> None:
    planned_id = make_planned(
        account_id=make_account(),
        category_id=make_category(),
    )
    txn = promote_to_actual(conn, USER_ID, planned_id, PromotionEdits())

    planned_audit = audit_repo.list_entries(conn, "planned_transaction", planned_id)
    txn_audit = audit_repo.list_entries(conn, "transaction", txn.id)

    assert [e.operation.value for e in planned_audit] == ["create", "update"]
    assert [e.operation.value for e in txn_audit] == ["create"]


def test_promote_rollback_leaves_no_partial_state_on_stamp_failure(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
    make_planned: Callable[..., int],
) -> None:
    planned_id = make_planned(
        account_id=make_account(),
        category_id=make_category(),
    )

    with (
        mock.patch(
            "budget_planner.services.planned.planned_repo.stamp_promotion",
            side_effect=RuntimeError("boom"),
        ),
        pytest.raises(RuntimeError, match="boom"),
    ):
        promote_to_actual(conn, USER_ID, planned_id, PromotionEdits())

    # No transaction row persisted, planned row untouched.
    txn_count = conn.execute(
        "SELECT COUNT(*) AS n FROM transactions WHERE promoted_from_planned_id = ?",
        (planned_id,),
    ).fetchone()["n"]
    assert txn_count == 0
    stamped = conn.execute(
        "SELECT promoted_to_txn_id FROM planned_transactions WHERE id = ?",
        (planned_id,),
    ).fetchone()["promoted_to_txn_id"]
    assert stamped is None
