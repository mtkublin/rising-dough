"""Mutation-kill tests for ``services/upcoming`` (T-Q247, ADR-0131).

Two-user and tombstone worlds from ``conftest.py`` (T-Q221), exact items, injected ``today``.
Complements ``test_upcoming.py``.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
)
from budget_planner.services import upcoming as upcoming_svc
from tests.formula_fx_support import formula_fx_of
from tests.unit.services.conftest import (
    EXPENSE_RULE_DUE,
    INCOME_RULE_DUE,
    OTHER_ID,
    OWNER_ID,
    WORLD_TODAY,
    World,
    expense_rule_amount,
    income_rule_amount,
    planned_amount,
    seed_formula_rule,
)

PLANNED_DAY = date(2026, 11, 13)


def test_world_items_exact_scoped_and_without_tombstones(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    owner = world_with_tombstones.owner
    items = upcoming_svc.list_upcoming(
        conn, OWNER_ID, today=WORLD_TODAY, window_days=None, fx=formula_fx_of(conn, OWNER_ID)
    )
    assert items == (
        upcoming_svc.UpcomingItem(
            kind="planned",
            effective_date=PLANNED_DAY,
            account_id=owner.account_id,
            dest_account_id=None,
            category_id=owner.category_id,
            amount_minor=planned_amount(OWNER_ID),
            description="planned-1",
            is_overdue=False,
            planned_id=owner.planned_id,
            rule_id=None,
            override_present=False,
            is_formula=False,
        ),
        upcoming_svc.UpcomingItem(
            kind="recurring",
            effective_date=EXPENSE_RULE_DUE,
            account_id=owner.account_id,
            dest_account_id=None,
            category_id=owner.category_id,
            amount_minor=expense_rule_amount(OWNER_ID),
            description="rule-1-700",
            is_overdue=False,
            planned_id=None,
            rule_id=owner.rule_id,
            override_present=False,
            is_formula=False,
        ),
        upcoming_svc.UpcomingItem(
            kind="recurring",
            effective_date=INCOME_RULE_DUE,
            account_id=owner.account_id,
            dest_account_id=None,
            category_id=owner.income_category_id,
            amount_minor=income_rule_amount(OWNER_ID),
            description="rule-1-5000",
            is_overdue=False,
            planned_id=None,
            rule_id=owner.income_rule_id,
            override_present=False,
            is_formula=False,
        ),
    )
    other = upcoming_svc.list_upcoming(
        conn, OTHER_ID, today=WORLD_TODAY, window_days=None, fx=formula_fx_of(conn, OTHER_ID)
    )
    assert {i.account_id for i in other} == {world_with_tombstones.other.account_id}
    assert len(other) == 3


def test_transit_planned_row_keeps_destination_and_category(
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
            operation_date=WORLD_TODAY,
            category_id=transit.id,
            account_id=owner.account_id,
            dest_account_id=dest,
            amount=321,
            description="move",
        ),
    )
    items = upcoming_svc.list_upcoming(
        conn, OWNER_ID, today=WORLD_TODAY, window_days=0, fx=formula_fx_of(conn, OWNER_ID)
    )
    assert [(i.planned_id, i.dest_account_id, i.category_id, i.amount_minor) for i in items] == [
        (row.id, dest, transit.id, 321)
    ]


def test_window_is_inclusive_of_today_plus_days(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    def dates(window: int) -> list[date]:
        return [
            i.effective_date
            for i in upcoming_svc.list_upcoming(
                conn,
                OWNER_ID,
                today=WORLD_TODAY,
                window_days=window,
                fx=formula_fx_of(conn, OWNER_ID),
            )
        ]

    assert dates(0) == []
    assert dates(1) == [PLANNED_DAY]  # 11-13 is today + 1
    assert dates(2) == [PLANNED_DAY]  # 11-15 is today + 3
    assert dates(3) == [PLANNED_DAY, EXPENSE_RULE_DUE]
    assert dates(4) == [PLANNED_DAY, EXPENSE_RULE_DUE]
    assert dates(18) == [PLANNED_DAY, EXPENSE_RULE_DUE]
    assert dates(19) == [PLANNED_DAY, EXPENSE_RULE_DUE, INCOME_RULE_DUE]  # 12-01 is today + 19


def test_same_day_planned_row_sorts_before_recurring(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    late = planned_repo.create(
        conn,
        OWNER_ID,
        NewPlannedTransaction(
            operation_date=EXPENSE_RULE_DUE,
            category_id=owner.category_id,
            account_id=owner.account_id,
            amount=1,
            description="same-day",
        ),
    )
    items = upcoming_svc.list_upcoming(
        conn, OWNER_ID, today=WORLD_TODAY, window_days=3, fx=formula_fx_of(conn, OWNER_ID)
    )
    assert [(i.kind, i.planned_id, i.rule_id) for i in items] == [
        ("planned", owner.planned_id, None),
        ("planned", late.id, None),
        ("recurring", None, owner.rule_id),
    ]


def test_overdue_planned_is_flagged_and_overdue_recurring_is_not(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    yesterday = WORLD_TODAY - timedelta(days=1)
    stale = planned_repo.create(
        conn,
        OWNER_ID,
        NewPlannedTransaction(
            operation_date=yesterday,
            category_id=owner.category_id,
            account_id=owner.account_id,
            amount=1,
        ),
    )
    due_today = planned_repo.create(
        conn,
        OWNER_ID,
        NewPlannedTransaction(
            operation_date=WORLD_TODAY,
            category_id=owner.category_id,
            account_id=owner.account_id,
            amount=2,
        ),
    )
    conn.execute(
        "UPDATE recurring_rules SET next_due = ?, start_date = ? WHERE id = ? AND user_id = ?",
        (yesterday.isoformat(), yesterday.isoformat(), owner.rule_id, OWNER_ID),
    )
    items = upcoming_svc.list_upcoming(
        conn, OWNER_ID, today=WORLD_TODAY, window_days=0, fx=formula_fx_of(conn, OWNER_ID)
    )
    assert [(i.kind, i.planned_id, i.rule_id, i.is_overdue) for i in items] == [
        ("planned", stale.id, None, True),
        ("recurring", None, owner.rule_id, False),
        ("planned", due_today.id, None, False),
    ]


def test_formula_flag_only_on_the_formula_rule_and_is_scoped_to_the_user(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    formula = seed_formula_rule(conn, OWNER_ID, world_with_two_users.owner, due=date(2026, 11, 20))
    items = upcoming_svc.list_upcoming(
        conn, OWNER_ID, today=WORLD_TODAY, window_days=None, fx=formula_fx_of(conn, OWNER_ID)
    )
    assert {i.rule_id: i.is_formula for i in items if i.kind == "recurring"} == {
        world_with_two_users.owner.rule_id: False,
        world_with_two_users.owner.income_rule_id: False,
        formula.id: True,
    }
    other = upcoming_svc.list_upcoming(
        conn, OTHER_ID, today=WORLD_TODAY, window_days=None, fx=formula_fx_of(conn, OTHER_ID)
    )
    assert not any(i.is_formula for i in other)
