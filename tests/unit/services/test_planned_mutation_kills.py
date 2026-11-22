"""Mutation-kill tests for ``services/planned`` (T-Q247, ADR-0131).

Two-user and tombstone worlds from ``conftest.py`` (T-Q221), exact values, injected ``today``.
Complements ``test_planned.py``.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import (
    NewPlannedTransaction,
    PatchPlannedTransaction,
    PlannedFilter,
)
from budget_planner.domain.transactions import NewTransaction, TransactionFilter
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    transactions as transactions_repo,
)
from budget_planner.services import planned as pl_svc
from tests.unit.services.conftest import (
    OTHER_ID,
    OWNER_ID,
    WORLD_DAY,
    WORLD_TODAY,
    World,
    planned_amount,
)

PLANNED_DAY = WORLD_DAY + timedelta(days=3)  # 2026-11-13, the world's planned row date


def _plan(
    conn: sqlite3.Connection,
    user_id: int,
    world: World,
    *,
    on: date,
    amount: int,
    description: str = "",
) -> int:
    rows = world.owner if user_id == OWNER_ID else world.other
    return planned_repo.create(
        conn,
        user_id,
        NewPlannedTransaction(
            operation_date=on,
            category_id=rows.category_id,
            account_id=rows.account_id,
            amount=amount,
            description=description,
        ),
    ).id


# --- list_planned --------------------------------------------------------------------------------


def test_list_planned_view_fields_and_user_scope(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    owner = world_with_tombstones.owner
    views = pl_svc.list_planned(conn, OWNER_ID, PlannedFilter(), today=WORLD_TODAY)
    assert views == (
        pl_svc.PlannedView(
            kind="persisted",
            operation_date=PLANNED_DAY,
            account_id=owner.account_id,
            dest_account_id=None,
            category_id=owner.category_id,
            amount_minor=planned_amount(OWNER_ID),
            description="planned-1",
            persisted_id=owner.planned_id,
            recurring_rule_id=None,
            occurrence_date=None,
            is_overridden=False,
            is_promoted=False,
        ),
    )


def test_default_window_is_the_calendar_month_of_today_inclusive(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    ids = {
        on: _plan(conn, OWNER_ID, world_with_two_users, on=on, amount=1)
        for on in (
            date(2026, 10, 31),
            date(2026, 11, 1),
            date(2026, 11, 30),
            date(2026, 12, 1),
        )
    }
    views = pl_svc.list_planned(conn, OWNER_ID, PlannedFilter(), today=WORLD_TODAY)
    assert {v.persisted_id for v in views} == {
        ids[date(2026, 11, 1)],
        ids[date(2026, 11, 30)],
        world_with_two_users.owner.planned_id,
    }


def test_explicit_window_replaces_each_default_end_independently(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    oct_id = _plan(conn, OWNER_ID, world_with_two_users, on=date(2026, 10, 15), amount=1)
    dec_id = _plan(conn, OWNER_ID, world_with_two_users, on=date(2026, 12, 15), amount=1)
    world_id = world_with_two_users.owner.planned_id
    from_only = pl_svc.list_planned(
        conn, OWNER_ID, PlannedFilter(date_from=date(2026, 10, 1)), today=WORLD_TODAY
    )
    assert [v.persisted_id for v in from_only] == [oct_id, world_id]  # date_to stays Nov 30
    to_only = pl_svc.list_planned(
        conn, OWNER_ID, PlannedFilter(date_to=date(2026, 12, 31)), today=WORLD_TODAY
    )
    assert [v.persisted_id for v in to_only] == [world_id, dec_id]  # date_from stays Nov 1
    both = pl_svc.list_planned(
        conn,
        OWNER_ID,
        PlannedFilter(date_from=date(2026, 10, 15), date_to=date(2026, 10, 15)),
        today=WORLD_TODAY,
    )
    assert [v.persisted_id for v in both] == [oct_id]


def test_list_planned_passes_every_filter_through(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    world = world_with_two_users
    owner = world.owner
    a = _plan(conn, OWNER_ID, world, on=date(2026, 11, 20), amount=1)
    b = _plan(conn, OWNER_ID, world, on=date(2026, 11, 21), amount=2)
    c = _plan(conn, OWNER_ID, world, on=date(2026, 11, 22), amount=3)
    other_acct = accounts_repo.create(
        conn, OWNER_ID, NewAccount(name="second", currency="PLN", opening_balance=0)
    ).id
    planned_repo.update(conn, OWNER_ID, c, PatchPlannedTransaction(account_id=other_acct))
    window = {"date_from": date(2026, 11, 1), "date_to": date(2026, 11, 30)}

    def ids(**kw: object) -> list[int | None]:
        flt = PlannedFilter(**window, **kw)  # type: ignore[arg-type]  # reason: kwargs forwarded verbatim
        return [v.persisted_id for v in pl_svc.list_planned(conn, OWNER_ID, flt, today=WORLD_TODAY)]

    assert ids(account_ids=(owner.account_id,)) == [owner.planned_id, a, b]
    assert ids(account_ids=(other_acct,)) == [c]
    assert ids(category_ids=(owner.category_id,)) == [owner.planned_id, a, b, c]
    assert ids(category_ids=(owner.income_category_id,)) == []
    assert ids(directions=(Direction.INCOME,)) == []
    assert ids(directions=(Direction.EXPENSE,)) == [owner.planned_id, a, b, c]
    assert ids(limit=2) == [owner.planned_id, a]
    assert ids(limit=2, offset=2) == [b, c]
    assert ids(promoted=True) == []
    assert ids(promoted=False) == [owner.planned_id, a, b, c]


def test_list_planned_sorts_by_date_then_id(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    first = _plan(conn, OWNER_ID, world_with_two_users, on=date(2026, 11, 20), amount=1)
    second = _plan(conn, OWNER_ID, world_with_two_users, on=date(2026, 11, 20), amount=2)
    earlier = _plan(conn, OWNER_ID, world_with_two_users, on=date(2026, 11, 14), amount=3)
    views = pl_svc.list_planned(conn, OWNER_ID, PlannedFilter(), today=WORLD_TODAY)
    assert [v.persisted_id for v in views] == [
        world_with_two_users.owner.planned_id,
        earlier,
        first,
        second,
    ]


def test_promoted_view_flag_and_rule_fields(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    linked = planned_repo.create(
        conn,
        OWNER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 16),
            category_id=owner.category_id,
            account_id=owner.account_id,
            amount=9,
            recurring_rule_id=owner.rule_id,
            occurrence_date=date(2026, 11, 15),
        ),
    )
    pl_svc.promote_to_actual(conn, OWNER_ID, linked.id, pl_svc.PromotionEdits())
    views = pl_svc.list_planned(conn, OWNER_ID, PlannedFilter(), today=WORLD_TODAY)
    view = next(v for v in views if v.persisted_id == linked.id)
    assert (view.recurring_rule_id, view.occurrence_date, view.is_promoted) == (
        owner.rule_id,
        date(2026, 11, 15),
        True,
    )
    by_rule = pl_svc.list_planned(
        conn, OWNER_ID, PlannedFilter(recurring_rule_id=owner.rule_id), today=WORLD_TODAY
    )
    assert [v.persisted_id for v in by_rule] == [linked.id]


# --- promote_to_actual ---------------------------------------------------------------------------


def test_promote_without_edits_copies_the_row_and_stamps_it(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    txn = pl_svc.promote_to_actual(conn, OWNER_ID, owner.planned_id, pl_svc.PromotionEdits())
    assert (
        txn.operation_date,
        txn.amount,
        txn.description,
        txn.category_id,
        txn.account_id,
        txn.promoted_from_planned_id,
    ) == (
        PLANNED_DAY,
        planned_amount(OWNER_ID),
        "planned-1",
        owner.category_id,
        owner.account_id,
        owner.planned_id,
    )
    row = planned_repo.find_by_id(conn, OWNER_ID, owner.planned_id)
    assert row is not None and row.promoted_to_txn_id == txn.id
    other_row = planned_repo.find_by_id(conn, OTHER_ID, world_with_two_users.other.planned_id)
    assert other_row is not None and other_row.promoted_to_txn_id is None


def test_promote_edits_apply_individually(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    world = world_with_two_users
    base = world.owner.planned_id
    date_only = pl_svc.promote_to_actual(
        conn, OWNER_ID, base, pl_svc.PromotionEdits(operation_date=date(2026, 11, 14))
    )
    assert (date_only.operation_date, date_only.amount, date_only.description) == (
        date(2026, 11, 14),
        500,
        "planned-1",
    )
    p2 = _plan(conn, OWNER_ID, world, on=PLANNED_DAY, amount=800, description="orig")
    amount_only = pl_svc.promote_to_actual(
        conn, OWNER_ID, p2, pl_svc.PromotionEdits(amount_minor=1)
    )
    assert (amount_only.operation_date, amount_only.amount, amount_only.description) == (
        PLANNED_DAY,
        1,
        "orig",
    )
    p3 = _plan(conn, OWNER_ID, world, on=PLANNED_DAY, amount=800, description="orig")
    blank_desc = pl_svc.promote_to_actual(conn, OWNER_ID, p3, pl_svc.PromotionEdits(description=""))
    assert (blank_desc.amount, blank_desc.description) == (800, "")


def test_promote_zero_amount_edit_is_rejected_not_treated_as_missing(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    with pytest.raises(pl_svc.ValidationError):
        pl_svc.promote_to_actual(
            conn,
            OWNER_ID,
            world_with_two_users.owner.planned_id,
            pl_svc.PromotionEdits(amount_minor=0),
        )
    row = planned_repo.find_by_id(conn, OWNER_ID, world_with_two_users.owner.planned_id)
    assert row is not None and row.promoted_to_txn_id is None


def test_promote_errors_and_scope(conn: sqlite3.Connection, world_with_tombstones: World) -> None:
    tomb = world_with_tombstones.tombstones
    assert tomb is not None
    with pytest.raises(pl_svc.CannotPromoteDeletedError) as deleted:
        pl_svc.promote_to_actual(conn, OWNER_ID, tomb.planned_id, pl_svc.PromotionEdits())
    assert deleted.value.planned_id == tomb.planned_id
    other_planned = world_with_tombstones.other.planned_id
    with pytest.raises(pl_svc.PlannedNotFoundError):
        pl_svc.promote_to_actual(conn, OWNER_ID, other_planned, pl_svc.PromotionEdits())
    pl_svc.promote_to_actual(
        conn, OWNER_ID, world_with_tombstones.owner.planned_id, pl_svc.PromotionEdits()
    )
    with pytest.raises(pl_svc.AlreadyPromotedError) as again:
        pl_svc.promote_to_actual(
            conn, OWNER_ID, world_with_tombstones.owner.planned_id, pl_svc.PromotionEdits()
        )
    assert again.value.planned_id == world_with_tombstones.owner.planned_id


# --- batch_promote_due / undo_batch --------------------------------------------------------------


def test_batch_promote_due_boundary_scope_and_tombstones(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    world = world_with_tombstones
    on_today = _plan(conn, OWNER_ID, world, on=WORLD_TODAY, amount=11)
    _plan(conn, OWNER_ID, world, on=WORLD_TODAY + timedelta(days=1), amount=12)  # not due
    overdue = _plan(conn, OWNER_ID, world, on=WORLD_TODAY - timedelta(days=30), amount=13)
    other_due = _plan(conn, OTHER_ID, world, on=WORLD_TODAY, amount=14)
    result = pl_svc.batch_promote_due(conn, OWNER_ID, WORLD_TODAY)
    assert set(result.promoted_planned_ids) == {on_today, overdue}
    assert len(result.promoted_txn_ids) == 2
    amounts = {
        transactions_repo.find_by_id(conn, OWNER_ID, t).amount  # type: ignore[union-attr]  # reason: just created
        for t in result.promoted_txn_ids
    }
    assert amounts == {11, 13}
    untouched = planned_repo.find_by_id(conn, OTHER_ID, other_due)
    assert untouched is not None and untouched.promoted_to_txn_id is None
    assert pl_svc.batch_promote_due(conn, OWNER_ID, WORLD_TODAY) == pl_svc.BatchPromoteResult(
        (), ()
    )


def test_undo_batch_restores_deletes_and_skips(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    world = world_with_two_users
    p1 = _plan(conn, OWNER_ID, world, on=WORLD_TODAY, amount=21)
    p2 = _plan(conn, OWNER_ID, world, on=WORLD_TODAY, amount=22)
    batch = pl_svc.batch_promote_due(conn, OWNER_ID, WORLD_TODAY)
    # a later, unrelated promotion re-stamps p2 after the batch was undone-able
    foreign_txn = transactions_repo.create(
        conn,
        OWNER_ID,
        NewTransaction(
            operation_date=WORLD_TODAY,
            category_id=world.owner.category_id,
            account_id=world.owner.account_id,
            amount=22,
            description="x",
        ),
    )
    conn.execute(
        "UPDATE planned_transactions SET promoted_to_txn_id = ? WHERE id = ? AND user_id = ?",
        (foreign_txn.id, p2, OWNER_ID),
    )
    result = pl_svc.undo_batch(conn, OWNER_ID, [*batch.promoted_txn_ids, 99_999], [p1, p2, 99_998])
    assert result.deleted_txn_ids == batch.promoted_txn_ids
    assert result.restored_planned_ids == (p1,)
    assert result.skipped_planned_ids == (p2, 99_998)
    restored = planned_repo.find_by_id(conn, OWNER_ID, p1)
    assert restored is not None and restored.promoted_to_txn_id is None
    for txn_id in batch.promoted_txn_ids:
        assert transactions_repo.find_by_id(conn, OWNER_ID, txn_id) is None
    assert transactions_repo.find_by_id(conn, OWNER_ID, foreign_txn.id) is not None


def test_undo_batch_never_touches_another_users_rows(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    world = world_with_two_users
    other_plan = _plan(conn, OTHER_ID, world, on=WORLD_TODAY, amount=31)
    other_batch = pl_svc.batch_promote_due(conn, OTHER_ID, WORLD_TODAY)
    result = pl_svc.undo_batch(conn, OWNER_ID, other_batch.promoted_txn_ids, [other_plan])
    assert result == pl_svc.BatchUndoResult((), (), (other_plan,))
    for txn_id in other_batch.promoted_txn_ids:
        assert transactions_repo.find_by_id(conn, OTHER_ID, txn_id) is not None
    row = planned_repo.find_by_id(conn, OTHER_ID, other_plan)
    assert row is not None and row.promoted_to_txn_id == other_batch.promoted_txn_ids[0]


# --- remaining view fields, error payloads, soft-deleted category, undo order --------------------


def test_view_carries_destination_account_and_overridden_flag(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    dest = accounts_repo.create(
        conn, OWNER_ID, NewAccount(name="savings", currency="PLN", opening_balance=0)
    ).id
    transit = categories_repo.find_by_name(conn, OWNER_ID, "Transit")
    assert transit is not None
    row = planned_repo.create(
        conn,
        OWNER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 20),
            category_id=transit.id,
            account_id=owner.account_id,
            dest_account_id=dest,
            amount=77,
            description="move",
        ),
    )
    view = next(
        v
        for v in pl_svc.list_planned(conn, OWNER_ID, PlannedFilter(), today=WORLD_TODAY)
        if v.persisted_id == row.id
    )
    assert (view.dest_account_id, view.category_id, view.description, view.is_overridden) == (
        dest,
        transit.id,
        "move",
        False,
    )


def test_not_found_error_names_the_requested_id(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    with pytest.raises(pl_svc.PlannedNotFoundError) as err:
        pl_svc.promote_to_actual(conn, OWNER_ID, 424_242, pl_svc.PromotionEdits())
    assert err.value.args == (424_242,)


def test_promote_is_refused_when_the_category_was_soft_deleted_afterwards(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    gone = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="gone", direction=Direction.EXPENSE)
    ).id
    row = planned_repo.create(
        conn,
        OWNER_ID,
        NewPlannedTransaction(
            operation_date=WORLD_TODAY, category_id=gone, account_id=owner.account_id, amount=55
        ),
    )
    categories_repo.soft_delete(conn, OWNER_ID, gone)
    before = len(transactions_repo.list_filtered(conn, OWNER_ID, TransactionFilter()))
    with pytest.raises(pl_svc.ValidationError, match=f"category {gone} not found"):
        pl_svc.promote_to_actual(conn, OWNER_ID, row.id, pl_svc.PromotionEdits())
    # T-Q287: a soft-deleted parent refuses the write; nothing is booked or stamped.
    assert len(transactions_repo.list_filtered(conn, OWNER_ID, TransactionFilter())) == before
    stored = planned_repo.find_by_id(conn, OWNER_ID, row.id)
    assert stored is not None
    assert stored.promoted_to_txn_id is None


def test_undo_batch_skips_unknown_transaction_ids_and_keeps_going(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    planned_id = _plan(conn, OWNER_ID, world_with_two_users, on=WORLD_TODAY, amount=9)
    batch = pl_svc.batch_promote_due(conn, OWNER_ID, WORLD_TODAY)
    result = pl_svc.undo_batch(conn, OWNER_ID, [99_999, *batch.promoted_txn_ids], [planned_id])
    assert result.deleted_txn_ids == batch.promoted_txn_ids
    assert result.restored_planned_ids == (planned_id,)
    assert result.skipped_planned_ids == ()
