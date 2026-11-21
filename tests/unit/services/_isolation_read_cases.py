# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""Isolation cases for the read-side money services: balance, budget, account_planned, income, preferences, upcoming, today.

Expected numbers come from the world in ``conftest.py`` (user ``u`` = 1 or 2): opening balance, one expense txn of
``1000u`` on 2026-11-10, one planned expense of ``500u`` on 11-13, a monthly expense rule of ``700u`` due 11-15, a
monthly income rule of ``5000u`` due 12-01 (the income anchor) and a ``3000u`` budget. The owner additionally has
tombstones (``world_with_tombstones``) whose amounts must never show up.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget_planner.config import Settings
from budget_planner.domain.accounts import AccountStats, NewAccount
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    fx as fx_repo,
    transactions as transactions_repo,
)
from budget_planner.services import (
    account_planned,
    balance,
    budget,
    income,
    preferences,
    today as today_svc,
    upcoming,
)
from tests.unit.services._isolation_registry import covers
from tests.unit.services.conftest import (
    EXPENSE_RULE_DUE,
    INCOME_RULE_DUE,
    OTHER_BALANCE,
    OTHER_ID,
    OWNER_BALANCE,
    OWNER_ID,
    WORLD_TODAY,
    OwnedRows,
    World,
)

T = WORLD_TODAY
END_OF_CYCLE = INCOME_RULE_DUE
BASE = "PLN"


def _own(world: World, user_id: int) -> OwnedRows:
    return world.owner if user_id == OWNER_ID else world.other


# --- balance -----------------------------------------------------------------------------------------------------


@covers("balance.account_stats")
def _case_account_stats(conn: sqlite3.Connection, world: World) -> None:
    owner = balance.account_stats(conn, OWNER_ID, world.owner.account_id)
    assert owner == AccountStats(
        account_id=world.owner.account_id,
        balance=OWNER_BALANCE - 1_000,
        base_balance=OWNER_BALANCE - 1_000,
        txn_count=1,
        last_txn_date="2026-11-10",
        avg_inflow_minor=0,
        avg_outflow_minor=1_000,
    )
    other = balance.account_stats(conn, OTHER_ID, world.other.account_id)
    assert (other.balance, other.txn_count, other.avg_outflow_minor) == (
        OTHER_BALANCE - 2_000,
        1,
        2_000,
    )
    with pytest.raises(balance.AccountNotFoundError):
        balance.account_stats(conn, OTHER_ID, world.owner.account_id)
    with pytest.raises(balance.AccountNotFoundError):
        balance.account_stats(conn, OWNER_ID, world.other.account_id)
    # OQ-15 current behaviour: a soft-deleted account is still derivable by its owner (include_deleted=True).
    assert world.tombstones is not None
    dead = balance.account_stats(conn, OWNER_ID, world.tombstones.account_id)
    assert (dead.balance, dead.txn_count, dead.last_txn_date) == (9_999, 0, None)


@covers("balance.balance_series")
def _case_balance_series(conn: sqlite3.Connection, world: World) -> None:
    owner = balance.balance_series(conn, OWNER_ID, world.owner.account_id, days=4, today=T)
    expected = [
        (dt.date(2026, 11, 9), OWNER_BALANCE),
        (dt.date(2026, 11, 10), OWNER_BALANCE - 1_000),
        (dt.date(2026, 11, 11), OWNER_BALANCE - 1_000),
        (dt.date(2026, 11, 12), OWNER_BALANCE - 1_000),
    ]
    assert owner == expected
    other = balance.balance_series(conn, OTHER_ID, world.other.account_id, days=2, today=T)
    assert other == [(dt.date(2026, 11, 11), OTHER_BALANCE - 2_000), (T, OTHER_BALANCE - 2_000)]
    with pytest.raises(balance.AccountNotFoundError):
        balance.balance_series(conn, OTHER_ID, world.owner.account_id, days=2, today=T)


# --- budget ------------------------------------------------------------------------------------------------------


def _expected_summary_totals(user_id: int) -> budget.MonthTotals:
    budgeted = 3_000 * user_id
    spent = 1_000 * user_id
    committed = 500 * user_id + 700 * user_id  # planned + the monthly rule's 11-15 occurrence
    return budget.MonthTotals(
        budgeted_minor=budgeted,
        spent_minor=spent,
        committed_minor=committed,
        remaining_minor=budgeted - spent - committed,
        unbudgeted_committed_minor=0,
    )


@covers("budget.month_summary")
def _case_month_summary(conn: sqlite3.Connection, world: World) -> None:
    for user_id in (OWNER_ID, OTHER_ID):
        rows = _own(world, user_id)
        summary = budget.month_summary(conn, user_id, 2026, 11, today=T)
        assert summary.totals == _expected_summary_totals(user_id)
        assert [line.category_id for line in summary.lines] == [rows.category_id]
        assert summary.lines[0].spent_minor == 1_000 * user_id
        assert summary.next_income_date == END_OF_CYCLE
        assert summary.anchor_category_name == f"inc-{user_id}"
        assert summary.period_start == dt.date(2026, 11, 1)
        assert summary.days_until_next_income == 19
        assert summary.left_daily_spend_minor == 42 * user_id  # 800u / 19 days, half-even


@covers("budget.resolve_budget")
def _case_resolve_budget(conn: sqlite3.Connection, world: World) -> None:
    assert budget.resolve_budget(conn, OWNER_ID, world.owner.category_id, 2026, 11) == 3_000
    assert budget.resolve_budget(conn, OTHER_ID, world.other.category_id, 2026, 11) == 6_000
    assert budget.resolve_budget(conn, OTHER_ID, world.owner.category_id, 2026, 11) is None
    assert budget.resolve_budget(conn, OWNER_ID, world.other.category_id, 2026, 11) is None


@covers("budget.fiscal_month_for")
def _case_fiscal_month_for(conn: sqlite3.Connection, world: World) -> None:
    assert budget.fiscal_month_for(conn, OWNER_ID, T) == (2026, 11)
    assert budget.fiscal_month_for(conn, OTHER_ID, T) == (2026, 11)
    # Only user 2 lands an anchor paycheck in October: user 1's cycle must not move.
    _land_anchor_income(conn, OTHER_ID, world.other, dt.date(2026, 10, 28))
    assert budget.fiscal_month_for(conn, OTHER_ID, T) == (2026, 10)
    assert budget.fiscal_month_for(conn, OWNER_ID, T) == (2026, 11)


@covers("budget.resolve_period_start")
def _case_resolve_period_start(conn: sqlite3.Connection, world: World) -> None:
    assert budget.resolve_period_start(conn, OWNER_ID, T) == dt.date(2026, 11, 1)
    _land_anchor_income(conn, OTHER_ID, world.other, dt.date(2026, 10, 28))
    assert budget.resolve_period_start(conn, OTHER_ID, T) == dt.date(2026, 10, 28)
    assert budget.resolve_period_start(conn, OWNER_ID, T) == dt.date(2026, 11, 1)


def _land_anchor_income(conn: sqlite3.Connection, user_id: int, rows: OwnedRows, on: date) -> None:
    transactions_repo.create(
        conn,
        user_id,
        NewTransaction(
            operation_date=on,
            category_id=rows.income_category_id,
            account_id=rows.account_id,
            amount=100,
            description="paycheck",
        ),
    )


@covers("budget.committed_in_window")
def _case_committed_in_window(conn: sqlite3.Connection, world: World) -> None:
    for user_id in (OWNER_ID, OTHER_ID):
        total = budget.committed_in_window(
            conn, user_id, start=None, end=END_OF_CYCLE, today=T, base_currency=BASE
        )
        assert (
            total == 1_200 * user_id
        )  # tombstoned planned (8000) and inactive/deleted rules (6000/7000) excluded
    # The window is half-open: a window ending on the rule's due date excludes the occurrence.
    only_planned = budget.committed_in_window(
        conn, OWNER_ID, start=None, end=EXPENSE_RULE_DUE, today=T, base_currency=BASE
    )
    assert only_planned == 500


@covers("budget.committed_split_in_window")
def _case_committed_split_in_window(conn: sqlite3.Connection, world: World) -> None:
    owner_split = budget.committed_split_in_window(
        conn,
        OWNER_ID,
        start=None,
        end=END_OF_CYCLE,
        budgeted_category_ids=frozenset({world.owner.category_id}),
        today=T,
        base_currency=BASE,
    )
    assert owner_split == (1_200, 0)
    # The other user's category id is not budgeted for the owner, so ids never cross: all owner spend is "unbudgeted".
    crossed = budget.committed_split_in_window(
        conn,
        OWNER_ID,
        start=None,
        end=END_OF_CYCLE,
        budgeted_category_ids=frozenset({world.other.category_id}),
        today=T,
        base_currency=BASE,
    )
    assert crossed == (0, 1_200)


def _eur_account_with_rate(conn: sqlite3.Connection, user_id: int, *, deleted: bool) -> int:
    fx_repo.upsert_rate(conn, NewFxRate(date=T, from_ccy="EUR", to_ccy=BASE, rate=Decimal("4.00")))
    account = accounts_repo.create(
        conn,
        user_id,
        NewAccount(name=f"eur-{user_id}-{deleted}", currency="EUR", opening_balance=0),
    )
    if deleted:
        accounts_repo.soft_delete(conn, user_id, account.id)
    return account.id


@covers("budget.base_amount_converter")
def _case_base_amount_converter(conn: sqlite3.Connection, world: World) -> None:
    eur = _eur_account_with_rate(conn, OWNER_ID, deleted=False)
    gone = _eur_account_with_rate(conn, OWNER_ID, deleted=True)
    owner = budget.base_amount_converter(conn, OWNER_ID, today=T, base_currency=BASE)
    other = budget.base_amount_converter(conn, OTHER_ID, today=T, base_currency=BASE)
    assert owner(eur, 1_000) == 4_000
    # OQ-15 current behaviour: archived accounts keep converting (their currency is still resolved).
    assert owner(gone, 1_000) == 4_000
    assert owner(world.owner.account_id, 1_000) == 1_000
    # The other user cannot see the owner's EUR currency: the account id degrades to the base-currency default.
    assert other(eur, 1_000) == 1_000


@covers("budget.base_txn_converter")
def _case_base_txn_converter(conn: sqlite3.Connection, world: World) -> None:
    eur = _eur_account_with_rate(conn, OWNER_ID, deleted=False)
    eur_txn = transactions_repo.create(
        conn,
        OWNER_ID,
        NewTransaction(
            operation_date=T, category_id=world.owner.category_id, account_id=eur, amount=1_000
        ),
    )
    owner = budget.base_txn_converter(conn, OWNER_ID, base_currency=BASE)
    other = budget.base_txn_converter(conn, OTHER_ID, base_currency=BASE)
    assert owner(eur_txn) == 4_000
    assert other(eur_txn) == 1_000  # the other user cannot see the account's currency
    accounts_repo.soft_delete(conn, OWNER_ID, eur)
    # OQ-15 current behaviour: a soft-deleted account keeps converting its (still listed) transactions.
    assert budget.base_txn_converter(conn, OWNER_ID, base_currency=BASE)(eur_txn) == 4_000
    live = transactions_repo.find_by_id(conn, OWNER_ID, world.owner.transaction_id)
    assert live is not None
    assert owner(live) == 1_000


# --- account_planned ---------------------------------------------------------------------------------------------


@covers("account_planned.resolve_window")
def _case_resolve_window(conn: sqlite3.Connection, world: World) -> None:
    expected = account_planned.PlannedWindow(start=dt.date(2026, 11, 1), end=END_OF_CYCLE)
    assert account_planned.resolve_window(conn, OWNER_ID, T) == expected
    assert account_planned.resolve_window(conn, OTHER_ID, T) == expected
    preferences.set_income_anchor_category_id(conn, OWNER_ID, None)
    # No anchor: the window ends at the end of the month, and only for the user who cleared it.
    assert account_planned.resolve_window(conn, OWNER_ID, T).end == dt.date(2026, 12, 1)
    assert account_planned.resolve_window(conn, OTHER_ID, T) == expected


@covers("account_planned.planned_net_by_account")
def _case_planned_net_by_account(conn: sqlite3.Connection, world: World) -> None:
    window = account_planned.PlannedWindow(start=dt.date(2026, 11, 1), end=END_OF_CYCLE)
    assert account_planned.planned_net_by_account(conn, OWNER_ID, window) == {
        world.owner.account_id: -1_200
    }
    assert account_planned.planned_net_by_account(conn, OTHER_ID, window) == {
        world.other.account_id: -2_400
    }


@covers("account_planned.compute_accounts_planned")
def _case_compute_accounts_planned(conn: sqlite3.Connection, world: World) -> None:
    settings = Settings(_env_file=None)
    result = account_planned.compute_accounts_planned(conn, OWNER_ID, T, settings)
    assert result.by_account == {
        world.owner.account_id: account_planned.AccountPlanned(
            account_id=world.owner.account_id,
            currency=BASE,
            net_minor=-1_200,
            projected_minor=OWNER_BALANCE - 1_000 - 1_200,
        )
    }
    assert result.base_net_minor == -1_200
    other = account_planned.compute_accounts_planned(conn, OTHER_ID, T, settings)
    assert set(other.by_account) == {world.other.account_id}
    assert other.base_net_minor == -2_400


# --- income / preferences ----------------------------------------------------------------------------------------


@covers("income.next_anchor_date")
def _case_next_anchor_date(conn: sqlite3.Connection, world: World) -> None:
    assert (
        income.next_anchor_date(conn, OWNER_ID, world.owner.income_category_id, after=T)
        == INCOME_RULE_DUE
    )
    assert (
        income.next_anchor_date(conn, OTHER_ID, world.other.income_category_id, after=T)
        == INCOME_RULE_DUE
    )
    # A category id owned by someone else never yields a date.
    assert income.next_anchor_date(conn, OTHER_ID, world.owner.income_category_id, after=T) is None
    assert income.next_anchor_date(conn, OWNER_ID, world.other.income_category_id, after=T) is None


@covers("preferences.get_income_anchor_category_id")
def _case_get_anchor_id(conn: sqlite3.Connection, world: World) -> None:
    assert (
        preferences.get_income_anchor_category_id(conn, OWNER_ID) == world.owner.income_category_id
    )
    assert (
        preferences.get_income_anchor_category_id(conn, OTHER_ID) == world.other.income_category_id
    )
    preferences.set_income_anchor_category_id(conn, OWNER_ID, None)
    assert preferences.get_income_anchor_category_id(conn, OWNER_ID) is None
    assert (
        preferences.get_income_anchor_category_id(conn, OTHER_ID) == world.other.income_category_id
    )


@covers("preferences.resolve_income_anchor_category")
def _case_resolve_anchor(conn: sqlite3.Connection, world: World) -> None:
    owner = preferences.resolve_income_anchor_category(conn, OWNER_ID)
    other = preferences.resolve_income_anchor_category(conn, OTHER_ID)
    assert owner is not None
    assert other is not None
    assert (owner.id, owner.name) == (world.owner.income_category_id, "inc-1")
    assert (other.id, other.name) == (world.other.income_category_id, "inc-2")


@covers("preferences.set_income_anchor_category_id")
def _case_set_anchor(conn: sqlite3.Connection, world: World) -> None:
    with pytest.raises(preferences.InvalidAnchorCategoryError):
        preferences.set_income_anchor_category_id(conn, OTHER_ID, world.owner.income_category_id)
    assert (
        preferences.get_income_anchor_category_id(conn, OTHER_ID) == world.other.income_category_id
    )
    assert world.tombstones is not None
    with pytest.raises(preferences.InvalidAnchorCategoryError):  # soft-deleted category
        preferences.set_income_anchor_category_id(conn, OWNER_ID, world.tombstones.category_id)
    with pytest.raises(preferences.InvalidAnchorCategoryError):  # wrong direction
        preferences.set_income_anchor_category_id(conn, OWNER_ID, world.owner.category_id)
    assert (
        preferences.get_income_anchor_category_id(conn, OWNER_ID) == world.owner.income_category_id
    )


# --- upcoming / today --------------------------------------------------------------------------------------------


@covers("upcoming.list_upcoming")
def _case_list_upcoming(conn: sqlite3.Connection, world: World) -> None:
    for user_id in (OWNER_ID, OTHER_ID):
        rows = _own(world, user_id)
        items = upcoming.list_upcoming(conn, user_id, today=T, window_days=None)
        assert [(i.kind, i.effective_date, i.amount_minor, i.account_id) for i in items] == [
            ("planned", dt.date(2026, 11, 13), 500 * user_id, rows.account_id),
            ("recurring", EXPENSE_RULE_DUE, 700 * user_id, rows.account_id),
            ("recurring", INCOME_RULE_DUE, 5_000 * user_id, rows.account_id),
        ]
        assert [(i.planned_id, i.rule_id) for i in items] == [
            (rows.planned_id, None),
            (None, rows.rule_id),
            (None, rows.income_rule_id),
        ]
    windowed = upcoming.list_upcoming(conn, OWNER_ID, today=T, window_days=5)
    assert [i.amount_minor for i in windowed] == [500, 700]


@covers("today.afford")
def _case_afford(conn: sqlite3.Connection, world: World) -> None:
    owner = today_svc.afford(conn, OWNER_ID, T, 1_000)
    assert owner == today_svc.AffordResult(
        per_day_minor=0, delta_minor=-42, pace_tag="over_limit", days_left=19
    )
    other = today_svc.afford(conn, OTHER_ID, T, 1_000)
    assert other == today_svc.AffordResult(
        per_day_minor=32, delta_minor=-52, pace_tag="tight", days_left=19
    )
