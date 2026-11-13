from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import (
    NewPlannedTransaction,
    PatchPlannedTransaction,
    PlannedFilter,
)
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import audit, planned, recurring, transactions

USER_ID = 1


def _mk(
    conn: sqlite3.Connection,
    account_id: int,
    category_id: int,
    *,
    amount: int = 100,
    on: date | None = None,
) -> int:
    row = planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=on or date(2026, 3, 1),
            category_id=category_id,
            account_id=account_id,
            amount=amount,
        ),
    )
    return row.id


def test_create_round_trip(conn: sqlite3.Connection, account_id: int, category_id: int) -> None:
    pid = _mk(conn, account_id, category_id)
    assert planned.find_by_id(conn, USER_ID, pid) is not None
    entries = audit.list_entries(conn, "planned_transaction", pid)
    assert len(entries) == 1


def test_update(conn: sqlite3.Connection, account_id: int, category_id: int) -> None:
    pid = _mk(conn, account_id, category_id)
    updated = planned.update(
        conn,
        USER_ID,
        pid,
        PatchPlannedTransaction(amount=250, operation_date=date(2026, 4, 1)),
    )
    assert updated.amount == 250
    assert updated.operation_date == date(2026, 4, 1)


def test_update_missing(conn: sqlite3.Connection) -> None:
    with pytest.raises(LookupError):
        planned.update(conn, USER_ID, 999, PatchPlannedTransaction(amount=1))


def test_soft_delete_and_undelete(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    pid = _mk(conn, account_id, category_id)
    planned.soft_delete(conn, USER_ID, pid)
    assert planned.find_by_id(conn, USER_ID, pid) is None
    planned.soft_delete(conn, USER_ID, 999)  # no-op path
    planned.undelete(conn, USER_ID, pid)
    assert planned.find_by_id(conn, USER_ID, pid) is not None
    with pytest.raises(LookupError):
        planned.undelete(conn, USER_ID, 999)


def test_list_filtered(
    conn: sqlite3.Connection,
    account_id: int,
    category_id: int,
    income_category_id: int,
) -> None:
    _mk(conn, account_id, category_id, on=date(2026, 3, 15))
    _mk(conn, account_id, income_category_id, on=date(2026, 4, 15))

    one = planned.list_filtered(conn, USER_ID, PlannedFilter(date_from=date(2026, 4, 1)))
    assert len(one) == 1

    two = planned.list_filtered(
        conn,
        USER_ID,
        PlannedFilter(
            account_ids=(account_id,),
            category_ids=(income_category_id, category_id),
            directions=(Direction.INCOME,),
        ),
    )
    assert all(p.account_id == account_id for p in two)
    assert all(p.category_id == income_category_id for p in two)


def test_list_filtered_recurring_and_promoted(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    pid = _mk(conn, account_id, category_id)
    # Not promoted yet.
    nope = planned.list_filtered(conn, USER_ID, PlannedFilter(promoted=True))
    assert nope == []
    waiting = planned.list_filtered(conn, USER_ID, PlannedFilter(promoted=False))
    assert len(waiting) == 1

    txn = transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 3, 1),
            category_id=category_id,
            account_id=account_id,
            amount=100,
            promoted_from_planned_id=pid,
        ),
    )
    planned.stamp_promotion(conn, USER_ID, pid, txn.id)
    promoted = planned.list_filtered(conn, USER_ID, PlannedFilter(promoted=True))
    assert len(promoted) == 1


def test_list_filtered_pagination(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    for n in range(5):
        _mk(conn, account_id, category_id, on=date(2026, 5, 1 + n))
    first_two = planned.list_filtered(conn, USER_ID, PlannedFilter(limit=2, offset=0))
    assert len(first_two) == 2


def test_stamp_promotion_missing(conn: sqlite3.Connection) -> None:
    with pytest.raises(LookupError):
        planned.stamp_promotion(conn, USER_ID, 999, 1)


def test_list_filtered_date_to_and_rule(
    conn: sqlite3.Connection,
    account_id: int,
    category_id: int,
) -> None:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 1),
            category_id=category_id,
            account_id=account_id,
            default_amount=10,
            day_of_month=1,
        ),
    )
    linked = planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 5, 10),
            category_id=category_id,
            account_id=account_id,
            amount=50,
            recurring_rule_id=rule.id,
        ),
    )
    orphan = _mk(conn, account_id, category_id, on=date(2026, 6, 15))

    # date_to clips the orphan.
    only_may = planned.list_filtered(conn, USER_ID, PlannedFilter(date_to=date(2026, 5, 31)))
    assert len(only_may) == 1
    assert only_may[0].id == linked.id

    # rule filter picks only the linked one.
    only_linked = planned.list_filtered(conn, USER_ID, PlannedFilter(recurring_rule_id=rule.id))
    assert [p.id for p in only_linked] == [linked.id]
    # orphan is still reachable via rule-less filter.
    all_rows = planned.list_filtered(conn, USER_ID, PlannedFilter())
    assert {p.id for p in all_rows} == {linked.id, orphan}


def test_hides_soft_deleted(conn: sqlite3.Connection, account_id: int, category_id: int) -> None:
    pid = _mk(conn, account_id, category_id)
    planned.soft_delete(conn, USER_ID, pid)
    assert planned.list_filtered(conn, USER_ID, PlannedFilter()) == []
    with_deleted = planned.list_filtered(conn, USER_ID, PlannedFilter(), include_deleted=True)
    assert any(p.id == pid for p in with_deleted)
