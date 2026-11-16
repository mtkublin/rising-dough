from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.domain.transactions import (
    NewTransaction,
    PatchTransaction,
    TransactionFilter,
)
from budget_planner.repositories import audit, recurring as recurring_repo, transactions

USER_ID = 1


def _mk(
    conn: sqlite3.Connection,
    account_id: int,
    category_id: int,
    *,
    amount: int = 100,
    on: date | None = None,
    description: str = "",
    dest: int | None = None,
) -> int:
    txn = transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=on or date(2026, 1, 1),
            category_id=category_id,
            account_id=account_id,
            amount=amount,
            description=description,
            dest_account_id=dest,
        ),
    )
    return txn.id


def test_create_round_trip(conn: sqlite3.Connection, account_id: int, category_id: int) -> None:
    tid = _mk(conn, account_id, category_id, amount=250)
    fetched = transactions.find_by_id(conn, USER_ID, tid)
    assert fetched is not None
    assert fetched.amount == 250
    assert audit.list_entries(conn, "transaction", tid)[0].operation.value == "create"


def test_update(conn: sqlite3.Connection, account_id: int, category_id: int) -> None:
    tid = _mk(conn, account_id, category_id, amount=100)
    updated = transactions.update(
        conn,
        USER_ID,
        tid,
        PatchTransaction(amount=150, operation_date=date(2026, 2, 1), description="x"),
    )
    assert updated.amount == 150
    assert updated.operation_date == date(2026, 2, 1)


def test_update_missing_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(LookupError):
        transactions.update(conn, USER_ID, 999, PatchTransaction(amount=1))


def test_soft_delete_and_undelete(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    tid = _mk(conn, account_id, category_id)
    transactions.soft_delete(conn, USER_ID, tid)
    assert transactions.find_by_id(conn, USER_ID, tid) is None
    transactions.undelete(conn, USER_ID, tid)
    assert transactions.find_by_id(conn, USER_ID, tid) is not None


def test_soft_delete_missing_is_noop(conn: sqlite3.Connection) -> None:
    transactions.soft_delete(conn, USER_ID, 999)


def test_undelete_missing_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(LookupError):
        transactions.undelete(conn, USER_ID, 999)


def test_list_filtered_date_range(
    conn: sqlite3.Connection,
    account_id: int,
    category_id: int,
    income_category_id: int,
) -> None:
    _mk(conn, account_id, category_id, on=date(2026, 1, 15))
    _mk(conn, account_id, category_id, on=date(2026, 2, 15))
    _mk(conn, account_id, income_category_id, on=date(2026, 3, 15))

    filtered = transactions.list_filtered(
        conn,
        USER_ID,
        TransactionFilter(
            date_from=date(2026, 2, 1),
            date_to=date(2026, 2, 28),
        ),
    )
    assert len(filtered) == 1
    assert filtered[0].operation_date == date(2026, 2, 15)


def test_list_filtered_full_matrix(
    conn: sqlite3.Connection,
    account_id: int,
    dest_account_id: int,
    category_id: int,
    income_category_id: int,
) -> None:
    _mk(conn, account_id, category_id, amount=100, description="apple")
    _mk(conn, account_id, income_category_id, amount=500, description="salary")
    _mk(conn, dest_account_id, category_id, amount=250, description="apples")
    # Transit-style txn pointing at dest.
    _mk(
        conn,
        account_id,
        income_category_id,
        amount=99,
        description="xfer",
        dest=dest_account_id,
    )

    r = transactions.list_filtered(conn, USER_ID, TransactionFilter(account_ids=(account_id,)))
    assert all(t.account_id == account_id for t in r)

    r = transactions.list_filtered(
        conn, USER_ID, TransactionFilter(category_ids=(income_category_id,))
    )
    assert all(t.category_id == income_category_id for t in r)

    r = transactions.list_filtered(
        conn, USER_ID, TransactionFilter(directions=(Direction.EXPENSE,))
    )
    assert len(r) == 2

    r = transactions.list_filtered(conn, USER_ID, TransactionFilter(amount_min=200, amount_max=400))
    assert all(200 <= t.amount <= 400 for t in r)

    r = transactions.list_filtered(conn, USER_ID, TransactionFilter(description_contains="apple"))
    assert {t.description for t in r} == {"apple", "apples"}

    r = transactions.list_filtered(
        conn, USER_ID, TransactionFilter(account_or_dest=dest_account_id)
    )
    assert len(r) == 2

    r = transactions.list_filtered(conn, USER_ID, TransactionFilter(limit=1, offset=0))
    assert len(r) == 1

    r = transactions.list_filtered(conn, USER_ID, TransactionFilter(up_to_date=date(2026, 1, 1)))
    # All seeded transactions are on 2026-01-01 by default.
    assert len(r) >= 1


def test_list_filtered_hides_soft_deleted(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    tid = _mk(conn, account_id, category_id)
    transactions.soft_delete(conn, USER_ID, tid)
    assert transactions.list_filtered(conn, USER_ID, TransactionFilter()) == []
    all_rows = transactions.list_filtered(conn, USER_ID, TransactionFilter(), include_deleted=True)
    assert any(t.id == tid for t in all_rows)


def test_create_round_trips_recurring_provenance_fields(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    """T-117 / ADR-0038: `create` persists + hydrates the recurring provenance pair.

    The service layer (T-118) enforces XOR with `promoted_from_planned_id`;
    the repository itself takes whatever the DTO gives it.
    """
    rule = recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 1),
            category_id=category_id,
            account_id=account_id,
            default_amount=10_000,
            day_of_month=1,
        ),
    )
    txn = transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 1, 1),
            category_id=category_id,
            account_id=account_id,
            amount=10_000,
            description="rent for jan",
            promoted_from_recurring_rule_id=rule.id,
            promoted_from_recurring_date=date(2026, 1, 1),
        ),
    )
    assert txn.promoted_from_recurring_rule_id == rule.id
    assert txn.promoted_from_recurring_date == date(2026, 1, 1)
    assert txn.promoted_from_planned_id is None

    # list_filtered surfaces the same shape.
    rows = transactions.list_filtered(conn, USER_ID, TransactionFilter())
    hit = next(r for r in rows if r.id == txn.id)
    assert hit.promoted_from_recurring_rule_id == rule.id
    assert hit.promoted_from_recurring_date == date(2026, 1, 1)


def test_create_defaults_recurring_provenance_fields_to_none(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    """A plain user-entered transaction has no provenance stamps."""
    tid = _mk(conn, account_id, category_id)
    hit = transactions.find_by_id(conn, USER_ID, tid)
    assert hit is not None
    assert hit.promoted_from_recurring_rule_id is None
    assert hit.promoted_from_recurring_date is None
    assert hit.promoted_from_planned_id is None
