"""Mutation-kill tests for ``services/balance`` and ``budget.yearly_grid`` (T-Q226, ADR-0131).

Every case builds on the two-user worlds from ``conftest.py`` (T-Q221), asserts exact minor-unit
values, and injects ``today`` (no real clock). Complements ``test_balance.py``.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import AccountStats, NewAccount
from budget_planner.domain.budgets import NewBudgetOneOffOverride, NewBudgetRecurringOverride
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.services import balance, budget
from tests.unit.services.conftest import (
    OTHER_BALANCE,
    OTHER_ID,
    OWNER_BALANCE,
    OWNER_ID,
    TOMBSTONE_ACCOUNT_BALANCE,
    WORLD_DAY,
    WORLD_TODAY,
    World,
    budget_amount,
    txn_amount,
)

OWNER_AFTER = OWNER_BALANCE - txn_amount(OWNER_ID)  # 122_456
OTHER_AFTER = OTHER_BALANCE - txn_amount(OTHER_ID)  # -1_223


def _txn(
    conn: sqlite3.Connection,
    *,
    on: date,
    category_id: int,
    account_id: int,
    amount: int,
    dest: int | None = None,
) -> None:
    transactions_repo.create(
        conn,
        OWNER_ID,
        NewTransaction(
            operation_date=on,
            category_id=category_id,
            account_id=account_id,
            dest_account_id=dest,
            amount=amount,
        ),
    )


# ---------------------------------------------------------------------------
# derive_balance / account_stats: two accounts, one transaction each
# ---------------------------------------------------------------------------
def test_derive_balance_two_users_each_get_own_exact_balance(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    assert balance.derive_balance(conn, OWNER_ID, w.owner.account_id) == OWNER_AFTER
    assert balance.derive_balance(conn, OTHER_ID, w.other.account_id) == OTHER_AFTER


def test_derive_balance_as_of_day_before_and_on_transaction(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    acct = world_with_two_users.owner.account_id
    day_before = date(2026, 11, 9)
    assert balance.derive_balance(conn, OWNER_ID, acct, as_of_date=day_before) == OWNER_BALANCE
    assert balance.derive_balance(conn, OWNER_ID, acct, as_of_date=WORLD_DAY) == OWNER_AFTER


def test_account_stats_returns_exact_dto_for_each_user(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    expected_last = WORLD_DAY.isoformat()
    assert balance.account_stats(conn, OWNER_ID, w.owner.account_id) == AccountStats(
        account_id=w.owner.account_id,
        balance=OWNER_AFTER,
        base_balance=OWNER_AFTER,
        txn_count=1,
        last_txn_date=expected_last,
        avg_inflow_minor=0,
        avg_outflow_minor=txn_amount(OWNER_ID),
    )
    assert balance.account_stats(conn, OTHER_ID, w.other.account_id) == AccountStats(
        account_id=w.other.account_id,
        balance=OTHER_AFTER,
        base_balance=OTHER_AFTER,
        txn_count=1,
        last_txn_date=expected_last,
        avg_inflow_minor=0,
        avg_outflow_minor=txn_amount(OTHER_ID),
    )


def test_other_user_cannot_read_owner_account(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner_account = world_with_two_users.owner.account_id
    with pytest.raises(balance.AccountNotFoundError):
        balance.account_stats(conn, OTHER_ID, owner_account)
    with pytest.raises(balance.AccountNotFoundError):
        balance.derive_balance(conn, OTHER_ID, owner_account)


def test_account_stats_latest_date_wins_regardless_of_insert_order(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    """Kills the ``>`` comparison on the running ``last_date``."""
    o = world_with_two_users.owner
    _txn(
        conn,
        on=date(2026, 11, 20),
        category_id=o.income_category_id,
        account_id=o.account_id,
        amount=5_000,
    )
    _txn(conn, on=date(2026, 11, 5), category_id=o.category_id, account_id=o.account_id, amount=300)
    stats = balance.account_stats(conn, OWNER_ID, o.account_id)
    assert stats.last_txn_date == "2026-11-20"
    assert stats.txn_count == 3
    assert stats.balance == OWNER_BALANCE - 1_000 - 300 + 5_000
    assert stats.avg_inflow_minor == 5_000
    assert stats.avg_outflow_minor == 650  # mean(1000, 300)


def test_account_stats_transit_counts_both_legs_but_not_averages(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    o = world_with_two_users.owner
    second = accounts_repo.create(
        conn, OWNER_ID, NewAccount(name="Second", currency="PLN", opening_balance=10)
    )
    transit = categories_repo.find_by_name(conn, OWNER_ID, "Transit")
    assert transit is not None
    _txn(
        conn,
        on=date(2026, 11, 11),
        category_id=transit.id,
        account_id=o.account_id,
        amount=2_500,
        dest=second.id,
    )
    src = balance.account_stats(conn, OWNER_ID, o.account_id)
    dst = balance.account_stats(conn, OWNER_ID, second.id)
    assert (src.balance, src.txn_count, src.last_txn_date) == (OWNER_AFTER - 2_500, 2, "2026-11-11")
    assert (src.avg_inflow_minor, src.avg_outflow_minor) == (0, 1_000)
    assert dst == AccountStats(
        account_id=second.id,
        balance=2_510,
        base_balance=2_510,
        txn_count=1,
        last_txn_date="2026-11-11",
        avg_inflow_minor=0,
        avg_outflow_minor=0,
    )


# ---------------------------------------------------------------------------
# include_deleted choice
# ---------------------------------------------------------------------------
def test_soft_deleted_account_balance_and_stats_still_resolve(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    tomb = world_with_tombstones.tombstones
    assert tomb is not None
    assert balance.derive_balance(conn, OWNER_ID, tomb.account_id) == TOMBSTONE_ACCOUNT_BALANCE
    stats = balance.account_stats(conn, OWNER_ID, tomb.account_id)
    assert (stats.account_id, stats.balance, stats.base_balance, stats.txn_count) == (
        tomb.account_id,
        TOMBSTONE_ACCOUNT_BALANCE,
        TOMBSTONE_ACCOUNT_BALANCE,
        0,
    )
    assert stats.last_txn_date is None


def test_live_transaction_on_soft_deleted_category_still_counts(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    o = world_with_tombstones.owner
    cat = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="gone-soon", direction=Direction.EXPENSE)
    )
    _txn(conn, on=date(2026, 11, 11), category_id=cat.id, account_id=o.account_id, amount=250)
    categories_repo.soft_delete(conn, OWNER_ID, cat.id)
    assert balance.derive_balance(conn, OWNER_ID, o.account_id) == OWNER_AFTER - 250
    stats = balance.account_stats(conn, OWNER_ID, o.account_id)
    assert (stats.balance, stats.txn_count, stats.avg_outflow_minor) == (OWNER_AFTER - 250, 2, 625)


def test_tombstoned_transaction_is_excluded_from_balance(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    o = world_with_tombstones.owner
    assert balance.derive_balance(conn, OWNER_ID, o.account_id) == OWNER_AFTER
    assert balance.account_stats(conn, OWNER_ID, o.account_id).txn_count == 1


# ---------------------------------------------------------------------------
# sparkline_points
# ---------------------------------------------------------------------------
def test_sparkline_points_exact_strings() -> None:
    assert balance.sparkline_points([0, 10, 5]) == "0.0,32.0 60.0,0.0 120.0,16.0"
    assert balance.sparkline_points([1, 3], width=50, height=10) == "0.0,10.0 50.0,0.0"
    assert (
        balance.sparkline_points([0, 1, 2, 3], width=10)
        == "0.0,32.0 3.33,21.33 6.67,10.67 10.0,0.0"
    )


def test_sparkline_points_flat_series_is_centred() -> None:
    assert balance.sparkline_points([5, 5], width=40, height=20) == "0.0,10.0 40.0,10.0"
    assert balance.sparkline_points([7, 7, 7]) == "0.0,16.0 60.0,16.0 120.0,16.0"


def test_sparkline_points_needs_two_points() -> None:
    assert balance.sparkline_points([]) == ""
    assert balance.sparkline_points([42]) == ""
    assert balance.sparkline_points([1, 2]) == "0.0,32.0 120.0,0.0"


def test_sparkline_points_falling_series_inverts_y() -> None:
    assert balance.sparkline_points([10, 0], width=10, height=4) == "0.0,0.0 10.0,4.0"


# ---------------------------------------------------------------------------
# balance_series
# ---------------------------------------------------------------------------
def test_balance_series_inclusive_window_oldest_first(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    acct = world_with_two_users.owner.account_id
    series = balance.balance_series(conn, OWNER_ID, acct, days=4, today=WORLD_TODAY)
    assert series == [
        (date(2026, 11, 9), OWNER_BALANCE),
        (date(2026, 11, 10), OWNER_AFTER),
        (date(2026, 11, 11), OWNER_AFTER),
        (date(2026, 11, 12), OWNER_AFTER),
    ]


def test_balance_series_single_day_and_non_positive_days(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    acct = world_with_two_users.owner.account_id
    assert balance.balance_series(conn, OWNER_ID, acct, days=1, today=WORLD_TODAY) == [
        (WORLD_TODAY, OWNER_AFTER)
    ]
    assert balance.balance_series(conn, OWNER_ID, acct, days=0, today=WORLD_TODAY) == []
    assert balance.balance_series(conn, OWNER_ID, acct, days=-3, today=WORLD_TODAY) == []


def test_balance_series_other_user_has_own_values(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    acct = world_with_two_users.other.account_id
    assert balance.balance_series(conn, OTHER_ID, acct, days=2, today=WORLD_DAY) == [
        (date(2026, 11, 9), OTHER_BALANCE),
        (WORLD_DAY, OTHER_AFTER),
    ]


def test_balance_series_default_window_is_ninety_days(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    series = balance.balance_series(
        conn, OWNER_ID, world_with_two_users.owner.account_id, today=WORLD_TODAY
    )
    assert len(series) == 90
    assert series[0] == (date(2026, 8, 15), OWNER_BALANCE)
    assert series[-1] == (WORLD_TODAY, OWNER_AFTER)


# ---------------------------------------------------------------------------
# budget.yearly_grid
# ---------------------------------------------------------------------------
def _row(rows: tuple[budget.YearlyRow, ...], name: str) -> budget.YearlyRow:
    return next(r for r in rows if r.category_name == name)


def test_yearly_grid_default_tier_fills_twelve_cells_for_owner_only(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    rows = budget.yearly_grid(conn, OWNER_ID, 2026)
    names = [r.category_name for r in rows]
    assert "cat-1" in names
    assert "cat-2" not in names
    row = _row(rows, "cat-1")
    default = budget_amount(OWNER_ID)
    assert row.category_id == world_with_two_users.owner.category_id
    assert row.category_direction is Direction.EXPENSE
    assert row.cells == (budget.YearlyCell(amount_minor=default, origin="default"),) * 12
    assert row.total_minor == 12 * default
    other_row = _row(budget.yearly_grid(conn, OTHER_ID, 2026), "cat-2")
    assert other_row.total_minor == 12 * budget_amount(OTHER_ID)
    assert all(r.category_direction is Direction.EXPENSE for r in rows)
    assert names == sorted(names, key=str.casefold)


def test_yearly_grid_override_precedence_and_totals(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    cat = world_with_two_users.owner.category_id
    default = budget_amount(OWNER_ID)
    for month, amount in ((3, 111), (5, 222)):
        budgets_repo.set_recurring(
            conn, OWNER_ID, NewBudgetRecurringOverride(category_id=cat, month=month, amount=amount)
        )
    for year, month, amount in ((2026, 5, 333), (2025, 7, 999)):
        budgets_repo.set_one_off(
            conn,
            OWNER_ID,
            NewBudgetOneOffOverride(category_id=cat, year=year, month=month, amount=amount),
        )
    row = _row(budget.yearly_grid(conn, OWNER_ID, 2026), "cat-1")
    cells = row.cells
    assert cells[2] == budget.YearlyCell(amount_minor=111, origin="recurring")
    assert cells[4] == budget.YearlyCell(amount_minor=333, origin="one_off")
    assert cells[6] == budget.YearlyCell(amount_minor=default, origin="default")
    assert cells[0] == budget.YearlyCell(amount_minor=default, origin="default")
    assert row.total_minor == 10 * default + 111 + 333


def test_yearly_grid_unset_cells_do_not_add_to_total(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    fresh = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="aaa-unbudgeted", direction=Direction.EXPENSE)
    )
    budgets_repo.set_one_off(
        conn,
        OWNER_ID,
        NewBudgetOneOffOverride(category_id=fresh.id, year=2026, month=12, amount=40),
    )
    row = _row(budget.yearly_grid(conn, OWNER_ID, 2026), "aaa-unbudgeted")
    assert row.cells[:11] == (budget.YearlyCell(amount_minor=None, origin="unset"),) * 11
    assert row.cells[11] == budget.YearlyCell(amount_minor=40, origin="one_off")
    assert row.total_minor == 40


def test_yearly_grid_omits_soft_deleted_category(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    names = [r.category_name for r in budget.yearly_grid(conn, OWNER_ID, 2026)]
    assert "dead-category" not in names
    assert "cat-1" in names


# ---------------------------------------------------------------------------
# error payloads
# ---------------------------------------------------------------------------
def test_unknown_account_error_carries_the_requested_id(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    """Kills ``AccountNotFoundError(None)`` in ``derive_balance`` and ``account_stats``."""
    missing = 987_654
    with pytest.raises(balance.AccountNotFoundError) as derive_exc:
        balance.derive_balance(conn, OWNER_ID, missing)
    assert derive_exc.value.args == (missing,)
    with pytest.raises(balance.AccountNotFoundError) as stats_exc:
        balance.account_stats(conn, OWNER_ID, missing)
    assert stats_exc.value.args == (missing,)


def test_signed_legs_transit_without_destination_raises_exact_message(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    """The schema CHECK blocks this row, so build the in-memory shape directly."""
    txn = transactions_repo.find_by_id(conn, OWNER_ID, world_with_two_users.owner.transaction_id)
    assert txn is not None
    broken = dataclasses.replace(txn, dest_account_id=None)
    with pytest.raises(ValueError, match=r"^transit transaction missing dest_account_id$"):
        balance.signed_legs(broken, Direction.TRANSIT)
