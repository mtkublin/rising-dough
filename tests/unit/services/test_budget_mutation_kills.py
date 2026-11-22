"""Mutation-kill tests for ``services/budget`` (T-Q224, ADR-0131).

Builds on the two-user and tombstone worlds from ``conftest.py`` (T-Q221), asserts exact minor
units, injects ``today`` and never reads the clock. Complements ``test_budget.py`` /
``test_budget_fx.py``. ``_mean_minor`` is exercised through the averages of ``month_summary``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from functools import partial
from typing import Any

import pytest

from budget_planner.clock import DEFAULT_DISPLAY_TIMEZONE
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.preferences import PREF_INCOME_ANCHOR_CATEGORY_ID
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.domain.transactions import NewTransaction, Transaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    fx as fx_repo,
    planned as planned_repo,
    preferences as preferences_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from budget_planner.repositories._unaudited import set_next_due
from budget_planner.services import budget
from budget_planner.services.fx import FxUnavailableError
from tests.unit.services.conftest import (
    OTHER_ID,
    OWNER_ID,
    WORLD_DAY,
    WORLD_TODAY,
    World,
    budget_amount,
    expense_rule_amount,
    planned_amount,
    txn_amount,
)

PLANNED_DAY = WORLD_DAY + timedelta(days=3)  # 2026-11-13, owner planned row
NEXT_INCOME = date(2026, 12, 1)  # income-anchor rule next_due in the world


def _committed(user_id: int) -> int:
    return planned_amount(user_id) + expense_rule_amount(user_id)


def _line(summary: budget.MonthSummary, category_id: int) -> budget.CategoryBudgetLine:
    return next(ln for ln in summary.lines if ln.category_id == category_id)


def _txn(conn: sqlite3.Connection, user_id: int, world_row: object, on: date, amount: int) -> None:
    row = world_row  # OwnedRows
    transactions_repo.create(
        conn,
        user_id,
        NewTransaction(
            operation_date=on,
            category_id=row.category_id,  # type: ignore[attr-defined]  # test helper over OwnedRows
            account_id=row.account_id,  # type: ignore[attr-defined]  # test helper over OwnedRows
            amount=amount,
        ),
    )


def _income(conn: sqlite3.Connection, w: World, on: date) -> None:
    transactions_repo.create(
        conn,
        OWNER_ID,
        NewTransaction(
            operation_date=on,
            category_id=w.owner.income_category_id,
            account_id=w.owner.account_id,
            amount=5_000,
        ),
    )


# ---------------------------------------------------------------------------
# month_summary: exact numbers per user, tombstones ignored
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("user_id", [OWNER_ID, OTHER_ID])
def test_month_summary_exact_totals_per_user(
    conn: sqlite3.Connection, world_with_tombstones: World, user_id: int
) -> None:
    w = world_with_tombstones
    row = w.owner if user_id == OWNER_ID else w.other
    s = budget.month_summary(
        conn,
        user_id,
        2026,
        11,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    budgeted = budget_amount(user_id)
    spent = txn_amount(user_id)
    committed = _committed(user_id)
    remaining = budgeted - spent - committed
    days = (NEXT_INCOME - WORLD_TODAY).days
    assert s.totals == budget.MonthTotals(
        budgeted_minor=budgeted,
        spent_minor=spent,
        committed_minor=committed,
        remaining_minor=remaining,
        unbudgeted_committed_minor=0,
    )
    assert s.next_income_date == NEXT_INCOME
    assert s.days_until_next_income == days == 19
    assert s.left_daily_spend_minor == round(Decimal(remaining) / days)
    assert s.period_start == date(2026, 11, 1)
    assert s.anchor_category_name == f"inc-{user_id}"
    line = _line(s, row.category_id)
    assert (line.budgeted_minor, line.spent_minor, line.remaining_minor) == (
        budgeted,
        spent,
        budgeted - spent,
    )
    assert line.delta_vs_prev_month_minor == spent
    assert line.category_name == f"cat-{user_id}"
    assert all(ln.category_id != w.tombstones.category_id for ln in s.lines)  # type: ignore[union-attr]


def test_month_summary_days_until_next_income_floor_is_one(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=NEXT_INCOME - timedelta(days=1),
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert s.days_until_next_income == 1
    # payday today: the next anchor is a month away; period opens today (ADR-0138).
    s2 = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        12,
        today=NEXT_INCOME,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert s2.period_start == NEXT_INCOME


def test_month_summary_without_budget_has_no_daily_spend_and_zero_commitments(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    # Clearing the only default leaves a month with no budget at all.
    budgets_repo.clear_default(conn, OWNER_ID, world_with_two_users.owner.category_id)
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert s.left_daily_spend_minor is None
    assert s.totals.committed_minor == 0
    assert s.totals.unbudgeted_committed_minor == 0
    assert s.anchor_category_name is None
    assert s.next_income_date == date(2026, 12, 1)
    assert s.period_start == date(2026, 11, 1)
    assert s.days_until_next_income == 19


# ---------------------------------------------------------------------------
# averages (_mean_minor through month_summary)
# ---------------------------------------------------------------------------
def test_averages_empty_category_and_single_item(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    empty = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="empty", direction=Direction.EXPENSE)
    )
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    e = _line(s, empty.id)
    assert (e.avg_monthly_overall_minor, e.avg_this_year_minor, e.delta_vs_prev_month_minor) == (
        0,
        0,
        0,
    )
    assert e.budgeted_minor is None
    assert e.remaining_minor is None
    one = _line(s, w.owner.category_id)
    assert one.avg_monthly_overall_minor == 1_000  # 1000 / 1 active month
    assert one.avg_this_year_minor == 91  # 1000 / 11 = 90.9


def test_averages_half_even_ties_and_prev_month_delta(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    _txn(conn, OWNER_ID, w.owner, date(2026, 10, 5), 1_501)
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    line = _line(s, w.owner.category_id)
    assert line.avg_monthly_overall_minor == 1_250  # 2501 / 2 = 1250.5 -> even
    assert line.avg_this_year_minor == 227  # 2501 / 11
    assert line.delta_vs_prev_month_minor == 1_000 - 1_501
    feb = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        2,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert _line(feb, w.owner.category_id).avg_this_year_minor == 1_250  # 2501 / 2 tie -> even
    _txn(conn, OWNER_ID, w.owner, date(2026, 10, 6), 2)
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert _line(s, w.owner.category_id).avg_monthly_overall_minor == 1_252  # 2503 / 2 = 1251.5
    feb = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        2,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert _line(feb, w.owner.category_id).avg_this_year_minor == 1_252


def test_overall_average_counts_distinct_months_not_transactions(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    _txn(conn, OWNER_ID, w.owner, date(2026, 11, 20), 500)  # same month as the world txn
    _txn(conn, OWNER_ID, w.owner, date(2025, 11, 20), 100)  # same month number, other year
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=date(2026, 11, 25),
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    line = _line(s, w.owner.category_id)
    assert line.avg_monthly_overall_minor == 800  # 1600 / 2 buckets (2025-11, 2026-11), not 3 txns


# ---------------------------------------------------------------------------
# committed window: start inclusive, end exclusive
# ---------------------------------------------------------------------------
D = date  # brevity in the table below


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (None, D(2026, 11, 13), 0),  # planned on the 13th is the day AT end: excluded
        (None, D(2026, 11, 14), 500),  # planned on the last day (13th) of [.., 14th)
        (None, D(2026, 11, 15), 500),  # rule due on the 15th excluded
        (None, D(2026, 11, 16), 1_200),  # rule on the last day counted
        (D(2026, 11, 13), D(2026, 11, 16), 1_200),  # start inclusive
        (D(2026, 11, 14), D(2026, 11, 16), 700),  # planned the day before start: dropped
        (D(2026, 11, 15), D(2026, 11, 16), 700),  # rule on the single day
        (D(2026, 11, 16), D(2026, 11, 20), 0),  # the day after the rule
        (D(2026, 11, 13), D(2026, 11, 13), 0),  # empty window
        (D(2026, 11, 14), D(2026, 11, 13), 0),  # inverted window
        (None, D(2026, 12, 1), 1_200),  # next rule occurrence (Dec 15) is outside
        (None, D(2026, 12, 16), 1_900),  # Dec 15 occurrence inside
    ],
)
def test_committed_in_window_boundaries(
    conn: sqlite3.Connection,
    world_with_tombstones: World,
    start: date | None,
    end: date,
    expected: int,
) -> None:
    got = budget.committed_in_window(
        conn, OWNER_ID, start=start, end=end, today=WORLD_TODAY, base_currency="PLN"
    )
    assert got == expected  # tombstones (planned 8000, inactive/deleted rules) never counted


def test_committed_other_user_has_own_numbers(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    got = budget.committed_by_category(
        conn, OTHER_ID, start=None, end=NEXT_INCOME, today=WORLD_TODAY, base_currency="PLN"
    )
    assert got == {world_with_tombstones.other.category_id: _committed(OTHER_ID)}


def test_committed_by_category_excludes_income_and_moves_start_not_cadence(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    got = budget.committed_by_category(
        conn, OWNER_ID, start=None, end=date(2027, 1, 1), today=WORLD_TODAY, base_currency="PLN"
    )
    # The income rule (5000 on Dec 1) is never committed; expense rule Nov 15 + Dec 15.
    assert got == {w.owner.category_id: 500 + 700 * 2}
    got2 = budget.committed_by_category(
        conn,
        OWNER_ID,
        start=date(2026, 11, 16),
        end=date(2027, 1, 1),
        today=WORLD_TODAY,
        base_currency="PLN",
    )
    assert got2 == {w.owner.category_id: 700}


def test_committed_split_by_budgeted_ids(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    split = partial(
        budget.committed_split_in_window,
        conn,
        OWNER_ID,
        start=None,
        end=NEXT_INCOME,
        today=WORLD_TODAY,
    )
    assert split(budgeted_category_ids=frozenset({w.owner.category_id}), base_currency="PLN") == (
        1_200,
        0,
    )
    assert split(budgeted_category_ids=frozenset(), base_currency="PLN") == (0, 1_200)


def test_unbudgeted_committed_reported_separately(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    free = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="free", direction=Direction.EXPENSE)
    )
    planned_repo.create(
        conn,
        OWNER_ID,
        NewPlannedTransaction(
            operation_date=PLANNED_DAY,
            category_id=free.id,
            account_id=w.owner.account_id,
            amount=333,
        ),
    )
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert s.totals.unbudgeted_committed_minor == 333
    assert s.totals.committed_minor == 1_200
    assert s.totals.remaining_minor == 3_000 - 1_000 - 1_200


# ---------------------------------------------------------------------------
# fiscal month and period start
# ---------------------------------------------------------------------------
def test_fiscal_month_without_landed_income_is_calendar_month(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    assert budget.fiscal_month_for(conn, OWNER_ID, WORLD_TODAY) == (2026, 11)
    assert budget.fiscal_month_for(conn, OWNER_ID, date(2027, 1, 31)) == (2027, 1)


def test_fiscal_month_window_starts_on_latest_landed_income(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    _income(conn, w, date(2026, 11, 1))
    _income(conn, w, date(2026, 10, 1))  # created second, earlier date: max() must win
    # window Nov 1 -> Dec 1 (rule next_due): 30 days all in November
    assert budget.fiscal_month_for(conn, OWNER_ID, WORLD_TODAY) == (2026, 11)
    # the other user has no landed income: calendar month of today
    assert budget.fiscal_month_for(conn, OTHER_ID, date(2027, 3, 3)) == (2027, 3)


def test_fiscal_month_labels_by_majority_of_days(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    _income(conn, w, date(2026, 10, 20))  # Oct 20 -> Dec 1: Oct 12d, Nov 30d
    assert budget.fiscal_month_for(conn, OWNER_ID, WORLD_TODAY) == (2026, 11)


def test_fiscal_month_without_future_anchor_uses_one_month_clamped(
    conn: sqlite3.Connection,
) -> None:
    acct = accounts_repo.create(conn, 1, NewAccount(name="a", currency="PLN", opening_balance=0))
    inc = categories_repo.create(conn, 1, NewCategory(name="pay", direction=Direction.INCOME))
    preferences_repo.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, str(inc.id))
    transactions_repo.create(
        conn,
        1,
        NewTransaction(
            operation_date=date(2026, 1, 31), category_id=inc.id, account_id=acct.id, amount=1
        ),
    )
    # no rule or planned row: end = Jan 31 + 1 month clamped to Feb 28 (Jan 1 day, Feb 27 days)
    assert budget.fiscal_month_for(conn, 1, date(2026, 2, 1)) == (2026, 2)
    transactions_repo.create(
        conn,
        1,
        NewTransaction(
            operation_date=date(2026, 3, 15), category_id=inc.id, account_id=acct.id, amount=1
        ),
    )
    # Mar 15 -> Apr 15: 17 days March, 14 April
    assert budget.fiscal_month_for(conn, 1, date(2026, 3, 20)) == (2026, 3)


def test_resolve_period_start_cases(conn: sqlite3.Connection, world_with_two_users: World) -> None:
    w = world_with_two_users
    assert budget.resolve_period_start(conn, OWNER_ID, WORLD_TODAY) == date(2026, 11, 1)
    _income(conn, w, date(2026, 11, 8))
    _income(conn, w, date(2026, 11, 5))
    assert budget.resolve_period_start(conn, OWNER_ID, WORLD_TODAY) == date(2026, 11, 8)
    _income(conn, w, WORLD_TODAY)  # landed today (inclusive upper bound)
    assert budget.resolve_period_start(conn, OWNER_ID, WORLD_TODAY) == WORLD_TODAY
    _income(conn, w, WORLD_TODAY + timedelta(days=1))  # future row ignored
    assert budget.resolve_period_start(conn, OWNER_ID, WORLD_TODAY) == WORLD_TODAY
    # payday (anchor rule due today) opens the period without a landed row
    assert budget.resolve_period_start(conn, OWNER_ID, NEXT_INCOME) == NEXT_INCOME
    # the other user's income rows never leak
    assert budget.resolve_period_start(conn, OTHER_ID, WORLD_TODAY) == date(2026, 11, 1)


def test_resolve_period_start_without_anchor_is_first_of_month(conn: sqlite3.Connection) -> None:
    assert budget.resolve_period_start(conn, 1, date(2026, 3, 17)) == date(2026, 3, 1)


def test_spent_resets_at_last_landed_anchor(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    _income(conn, w, date(2026, 11, 11))  # after the Nov 10 expense
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert s.period_start == date(2026, 11, 11)
    assert _line(s, w.owner.category_id).spent_minor == 0
    _txn(conn, OWNER_ID, w.owner, date(2026, 11, 11), 40)  # on the period start: counted
    _txn(conn, OWNER_ID, w.owner, WORLD_TODAY, 2)  # on today: counted
    _txn(conn, OWNER_ID, w.owner, WORLD_TODAY + timedelta(days=1), 900)  # after today: not
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert _line(s, w.owner.category_id).spent_minor == 42


def test_month_summary_period_window_overrides_anchor_window(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=WORLD_TODAY,
        period_window=(WORLD_DAY + timedelta(days=1), date(2026, 11, 30)),
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert _line(s, w.owner.category_id).spent_minor == 0
    assert s.period_start == WORLD_DAY + timedelta(days=1)
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=WORLD_TODAY,
        period_window=(WORLD_DAY, WORLD_DAY),
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert _line(s, w.owner.category_id).spent_minor == 1_000


# ---------------------------------------------------------------------------
# picker month
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("year_raw", "month_raw", "expected"),
    [
        (None, None, (2026, 11)),
        ("2027", None, (2027, 11)),
        (None, "3", (2026, 3)),
        ("2025", "12", (2025, 12)),
        ("2025", "1", (2025, 1)),
        ("2025", "0", (2026, 11)),
        ("2025", "13", (2026, 11)),
        ("abc", "3", (2026, 11)),
        ("2025", "x", (2026, 11)),
        ("0", "3", (2026, 11)),
        ("1", "3", (1, 3)),
        ("9999", "12", (9999, 12)),
        ("10000", "3", (2026, 11)),
    ],
)
def test_resolve_picker_month_parsing(
    conn: sqlite3.Connection,
    world_with_two_users: World,
    year_raw: str | None,
    month_raw: str | None,
    expected: tuple[int, int],
) -> None:
    p = budget.resolve_picker_month(
        conn, OWNER_ID, WORLD_TODAY, year_raw=year_raw, month_raw=month_raw
    )
    assert (p.year, p.month) == expected
    assert (p.fiscal_year, p.fiscal_month) == (2026, 11)


def test_resolve_picker_month_neighbours_and_fiscal_flag(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    p = budget.resolve_picker_month(conn, OWNER_ID, WORLD_TODAY, year_raw="2026", month_raw="12")
    assert (p.prev_year, p.prev_month, p.next_year, p.next_month) == (2026, 11, 2027, 1)
    assert p.is_fiscal is False
    q = budget.resolve_picker_month(conn, OWNER_ID, WORLD_TODAY)
    assert (q.prev_year, q.prev_month, q.next_year, q.next_month) == (2026, 10, 2026, 12)
    assert q.is_fiscal is True
    other_year = budget.resolve_picker_month(
        conn, OWNER_ID, WORLD_TODAY, year_raw="2025", month_raw="11"
    )
    assert other_year.is_fiscal is False
    other_month = budget.resolve_picker_month(
        conn, OWNER_ID, WORLD_TODAY, year_raw="2026", month_raw="10"
    )
    assert other_month.is_fiscal is False


def test_picker_summary_fiscal_equals_live_summary(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    picked = budget.resolve_picker_month(conn, OWNER_ID, WORLD_TODAY)
    assert budget.month_summary_for_picker(
        conn,
        OWNER_ID,
        picked,
        WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    ) == budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )


def test_picker_summary_future_month(conn: sqlite3.Connection, world_with_two_users: World) -> None:
    w = world_with_two_users
    picked = budget.resolve_picker_month(
        conn, OWNER_ID, WORLD_TODAY, year_raw="2026", month_raw="12"
    )
    s = budget.month_summary_for_picker(
        conn,
        OWNER_ID,
        picked,
        WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert s.period_start == date(2026, 12, 1)
    assert s.next_income_date == date(2027, 1, 1)
    assert s.days_until_next_income == 31
    assert s.totals == budget.MonthTotals(
        budgeted_minor=3_000,
        spent_minor=0,
        committed_minor=0,
        remaining_minor=3_000,
        unbudgeted_committed_minor=0,
    )
    assert _line(s, w.owner.category_id).spent_minor == 0


def test_picker_summary_past_month_spent_clamped_to_month(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    _txn(conn, OWNER_ID, w.owner, date(2026, 10, 31), 70)
    _txn(conn, OWNER_ID, w.owner, date(2026, 10, 1), 30)
    _txn(conn, OWNER_ID, w.owner, date(2026, 9, 30), 900)
    picked = budget.resolve_picker_month(
        conn, OWNER_ID, WORLD_TODAY, year_raw="2026", month_raw="10"
    )
    s = budget.month_summary_for_picker(
        conn,
        OWNER_ID,
        picked,
        WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert s.totals.spent_minor == 100
    assert s.totals.remaining_minor == 2_900
    assert s.totals.committed_minor == 0
    assert (s.period_start, s.next_income_date) == (date(2026, 10, 1), date(2026, 11, 1))
    assert s.days_until_next_income == 0  # window already closed


# ---------------------------------------------------------------------------
# FX: converter-backed base amounts (ADR-0095, ADR-0139)
# ---------------------------------------------------------------------------
def _rate(conn: sqlite3.Connection, on: date, rate: str, frm: str = "EUR", to: str = "PLN") -> None:
    fx_repo.upsert_rate(conn, NewFxRate(date=on, from_ccy=frm, to_ccy=to, rate=Decimal(rate)))


@pytest.fixture
def eur_world(conn: sqlite3.Connection) -> dict[str, int]:
    pln = accounts_repo.create(conn, 1, NewAccount(name="p", currency="PLN", opening_balance=0))
    eur = accounts_repo.create(conn, 1, NewAccount(name="e", currency="EUR", opening_balance=0))
    cat = categories_repo.create(conn, 1, NewCategory(name="c", direction=Direction.EXPENSE))
    return {"pln": pln.id, "eur": eur.id, "cat": cat.id}


def _new_txn(
    conn: sqlite3.Connection,
    ids: dict[str, int],
    on: date,
    *,
    key: str = "eur",
    amount: int = 10_000,
) -> Transaction:
    return transactions_repo.create(
        conn,
        1,
        NewTransaction(
            operation_date=on, category_id=ids["cat"], account_id=ids[key], amount=amount
        ),
    )


def test_txn_base_uses_rate_on_or_before_operation_date(
    conn: sqlite3.Connection, eur_world: dict[str, int]
) -> None:
    _rate(conn, date(2026, 11, 9), "4.00")
    _rate(conn, date(2026, 11, 10), "4.50")
    _rate(conn, date(2026, 11, 11), "5.00")
    base_of = budget.txn_base_amounts(conn, 1, today=date(2026, 11, 12), base_currency="PLN")
    assert base_of(_new_txn(conn, eur_world, date(2026, 11, 10))) == 45_000
    assert base_of(_new_txn(conn, eur_world, date(2026, 11, 12))) == 50_000
    assert base_of(_new_txn(conn, eur_world, date(2026, 11, 10), key="pln", amount=777)) == 777


def test_txn_base_missing_rate_raises(conn: sqlite3.Connection, eur_world: dict[str, int]) -> None:
    _rate(conn, date(2026, 11, 11), "5.00")
    t = _new_txn(conn, eur_world, date(2026, 11, 10))  # only a LATER rate is cached
    base_of = budget.txn_base_amounts(conn, 1, today=date(2026, 11, 12), base_currency="PLN")
    with pytest.raises(FxUnavailableError):
        base_of(t)


def test_planned_base_uses_latest_rate_on_or_before_today(
    conn: sqlite3.Connection, eur_world: dict[str, int]
) -> None:
    _rate(conn, date(2026, 11, 10), "4.50")
    _rate(conn, date(2026, 11, 11), "5.00")
    _rate(conn, date(2026, 11, 13), "9.00")  # after today: ignored
    base_of = budget.planned_base_amounts(conn, 1, today=date(2026, 11, 12), base_currency="PLN")
    assert base_of(eur_world["eur"], 10_000) == 50_000
    assert base_of(eur_world["pln"], 10_000) == 10_000
    assert base_of(987_654, 123) == 123  # unknown account: treated as base currency


def test_planned_base_missing_rate_raises_without_native_fallback(
    conn: sqlite3.Connection, eur_world: dict[str, int]
) -> None:
    base_of = budget.planned_base_amounts(conn, 1, today=date(2026, 11, 12), base_currency="PLN")
    with pytest.raises(FxUnavailableError):
        base_of(eur_world["eur"], 10_000)
    assert base_of(eur_world["pln"], 10_000) == 10_000  # base currency needs no rate


def test_planned_base_requires_an_explicit_today(conn: sqlite3.Connection) -> None:
    """ADR-0140: pure services never fall back to the host clock."""
    no_kwargs: dict[str, Any] = {}
    with pytest.raises(TypeError, match="today"):
        budget.planned_base_amounts(conn, 1, **no_kwargs)


def test_base_amounts_honour_base_currency_and_soft_deleted_accounts(
    conn: sqlite3.Connection, eur_world: dict[str, int]
) -> None:
    _rate(conn, date(2026, 11, 1), "0.25", frm="PLN", to="EUR")
    today = date(2026, 11, 12)
    planned_of = budget.planned_base_amounts(conn, 1, today=today, base_currency="EUR")
    assert planned_of(eur_world["pln"], 10_000) == 2_500
    assert planned_of(eur_world["eur"], 10_000) == 10_000
    txn = _new_txn(conn, eur_world, date(2026, 11, 10), key="pln")
    accounts_repo.soft_delete(conn, 1, eur_world["pln"])
    planned_after = budget.planned_base_amounts(conn, 1, today=today, base_currency="EUR")
    assert planned_after(eur_world["pln"], 10_000) == 2_500  # tombstone keeps its currency
    txn_of = budget.txn_base_amounts(conn, 1, today=today, base_currency="EUR")
    assert txn_of(txn) == 10_000  # ADR-0136: deleted accounts leave the txn converter map


def test_committed_converts_foreign_planned_and_raises_when_rate_missing(
    conn: sqlite3.Connection, eur_world: dict[str, int]
) -> None:
    planned_repo.create(
        conn,
        1,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 14),
            category_id=eur_world["cat"],
            account_id=eur_world["eur"],
            amount=10_000,
        ),
    )
    today = date(2026, 11, 12)
    with pytest.raises(FxUnavailableError):
        budget.committed_in_window(
            conn, 1, start=None, end=date(2026, 11, 20), today=today, base_currency="PLN"
        )
    _rate(conn, date(2026, 11, 11), "5.00")
    assert (
        budget.committed_in_window(
            conn, 1, start=None, end=date(2026, 11, 20), today=today, base_currency="PLN"
        )
        == 50_000
    )


def test_month_summary_spent_uses_historical_rate_and_raises_when_missing(
    conn: sqlite3.Connection, eur_world: dict[str, int]
) -> None:
    budgets_repo.set_default(
        conn, 1, NewBudgetDefault(category_id=eur_world["cat"], amount=100_000)
    )
    _new_txn(conn, eur_world, date(2026, 11, 10))
    with pytest.raises(FxUnavailableError):
        budget.month_summary(
            conn,
            1,
            2026,
            11,
            today=date(2026, 11, 12),
            base_currency="PLN",
            display_timezone=DEFAULT_DISPLAY_TIMEZONE,
        )
    _rate(conn, date(2026, 11, 10), "4.50")
    line = _line(
        budget.month_summary(
            conn,
            1,
            2026,
            11,
            today=date(2026, 11, 12),
            base_currency="PLN",
            display_timezone=DEFAULT_DISPLAY_TIMEZONE,
        ),
        eur_world["cat"],
    )
    assert line.spent_minor == 45_000
    assert line.remaining_minor == 55_000


# ---------------------------------------------------------------------------
# second round: survivors of the first mutmut run
# ---------------------------------------------------------------------------
def _rule(
    conn: sqlite3.Connection,
    *,
    category_id: int,
    account_id: int,
    start: date,
    next_due: date,
    amount: int,
    day_of_month: int | None = None,
    active: bool = True,
) -> None:
    rule = recurring_repo.create_rule(
        conn,
        OWNER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=start,
            day_of_month=day_of_month,
            category_id=category_id,
            account_id=account_id,
            default_amount=amount,
            default_description=f"extra-{amount}",
            active=active,
        ),
    )
    set_next_due(conn, OWNER_ID, rule.id, next_due=next_due, last_promoted_date=None)


def test_committed_skips_non_expense_and_out_of_window_rules_without_stopping(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    # Both sort BEFORE the world's expense rule (start Nov 15): an income rule and an expense
    # rule whose next_due lies beyond the window. Neither may end the scan.
    _rule(
        conn,
        category_id=w.owner.income_category_id,
        account_id=w.owner.account_id,
        start=date(2026, 11, 1),
        next_due=date(2026, 11, 18),
        amount=9_000,
    )
    _rule(
        conn,
        category_id=w.owner.category_id,
        account_id=w.owner.account_id,
        start=date(2026, 11, 2),
        next_due=date(2026, 12, 20),
        amount=8_000,
    )
    got = budget.committed_by_category(
        conn, OWNER_ID, start=None, end=date(2026, 11, 20), today=WORLD_TODAY, base_currency="PLN"
    )
    assert got == {w.owner.category_id: 500 + 700}


def test_committed_counts_rule_of_archived_expense_category(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    old = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="old", direction=Direction.EXPENSE)
    )
    _rule(
        conn,
        category_id=old.id,
        account_id=w.owner.account_id,
        start=date(2026, 11, 16),
        next_due=date(2026, 11, 16),
        amount=250,
    )
    categories_repo.soft_delete(conn, OWNER_ID, old.id)
    got = budget.committed_by_category(
        conn, OWNER_ID, start=None, end=date(2026, 11, 20), today=WORLD_TODAY, base_currency="PLN"
    )
    assert got == {w.owner.category_id: 1_200, old.id: 250}


def _pln_to_eur(conn: sqlite3.Connection, on: date, rate: str = "0.25") -> None:
    fx_repo.upsert_rate(conn, NewFxRate(date=on, from_ccy="PLN", to_ccy="EUR", rate=Decimal(rate)))


def _eur_calls(
    conn: sqlite3.Connection, category_id: int, *, today: date
) -> tuple[Callable[[], dict[int, int]], Callable[[], int], Callable[[], tuple[int, int]]]:
    return (
        partial(
            budget.committed_by_category,
            conn,
            OWNER_ID,
            start=None,
            end=NEXT_INCOME,
            today=today,
            base_currency="EUR",
        ),
        partial(
            budget.committed_in_window,
            conn,
            OWNER_ID,
            start=None,
            end=NEXT_INCOME,
            today=today,
            base_currency="EUR",
        ),
        partial(
            budget.committed_split_in_window,
            conn,
            OWNER_ID,
            start=None,
            end=NEXT_INCOME,
            today=today,
            base_currency="EUR",
            budgeted_category_ids=frozenset({category_id}),
        ),
    )


def test_committed_apis_pass_base_currency_through(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    _pln_to_eur(conn, date(2026, 11, 1))
    by_cat, in_window, split = _eur_calls(conn, w.owner.category_id, today=WORLD_TODAY)
    assert by_cat() == {w.owner.category_id: 125 + 175}
    assert in_window() == 300
    assert split() == (300, 0)


@pytest.mark.parametrize("api", ["by_category", "in_window", "split"])
def test_committed_apis_pass_today_through_to_the_converter(
    conn: sqlite3.Connection, world_with_two_users: World, api: str
) -> None:
    w = world_with_two_users
    _pln_to_eur(conn, date(2026, 11, 20))  # dated after the injected today, before any real clock
    by_cat, in_window, split = _eur_calls(conn, w.owner.category_id, today=WORLD_TODAY)
    calls: dict[str, Callable[[], object]] = {
        "by_category": by_cat,
        "in_window": in_window,
        "split": split,
    }
    with pytest.raises(FxUnavailableError):
        calls[api]()


def test_month_summary_passes_today_to_planned_converter(
    conn: sqlite3.Connection, eur_world: dict[str, int]
) -> None:
    budgets_repo.set_default(conn, 1, NewBudgetDefault(category_id=eur_world["cat"], amount=1_000))
    planned_repo.create(
        conn,
        1,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 14),
            category_id=eur_world["cat"],
            account_id=eur_world["eur"],
            amount=100,
        ),
    )
    _rate(conn, date(2026, 11, 20), "5.00")  # after the injected today
    with pytest.raises(FxUnavailableError):
        budget.month_summary(
            conn,
            1,
            2026,
            11,
            today=date(2026, 11, 12),
            base_currency="PLN",
            display_timezone=DEFAULT_DISPLAY_TIMEZONE,
        )
    s = budget.month_summary(
        conn,
        1,
        2026,
        11,
        today=date(2026, 11, 25),
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert s.totals.committed_minor == 500  # 100 EUR minor * 5.00; overdue items count (ADR-0105)


def test_non_anchor_income_never_moves_fiscal_month_or_period_start(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    _income(conn, w, date(2026, 9, 15))  # anchor landed Sep 15 -> Dec 1: Oct holds most days
    bonus = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="bonus", direction=Direction.INCOME)
    )
    transactions_repo.create(
        conn,
        OWNER_ID,
        NewTransaction(
            operation_date=date(2026, 11, 11),
            category_id=bonus.id,
            account_id=w.owner.account_id,
            amount=1,
        ),
    )
    assert budget.fiscal_month_for(conn, OWNER_ID, WORLD_TODAY) == (2026, 10)
    assert budget.resolve_period_start(conn, OWNER_ID, WORLD_TODAY) == date(2026, 9, 15)
    picked = budget.resolve_picker_month(conn, OWNER_ID, WORLD_TODAY)
    assert (picked.fiscal_year, picked.fiscal_month) == (2026, 10)
    other = budget.resolve_picker_month(conn, OTHER_ID, WORLD_TODAY)
    assert (other.fiscal_year, other.fiscal_month) == (2026, 11)  # no landed income


def test_payday_detected_when_anchor_also_dated_the_day_before(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    for day in (date(2026, 11, 11), WORLD_TODAY):
        planned_repo.create(
            conn,
            OWNER_ID,
            NewPlannedTransaction(
                operation_date=day,
                category_id=w.owner.income_category_id,
                account_id=w.owner.account_id,
                amount=1,
            ),
        )
    assert budget.resolve_period_start(conn, OWNER_ID, WORLD_TODAY) == WORLD_TODAY


# ---------------------------------------------------------------------------
# month_summary windows and line fields
# ---------------------------------------------------------------------------
def test_year_window_includes_jan_first_and_excludes_next_year(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    _txn(conn, OWNER_ID, w.owner, date(2026, 1, 1), 110)
    _txn(conn, OWNER_ID, w.owner, date(2026, 12, 31), 220)
    _txn(conn, OWNER_ID, w.owner, date(2027, 1, 1), 5_000)
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    # year sum = 1000 + 110 + 220 over 11 elapsed months; overall counts every active month
    assert _line(s, w.owner.category_id).avg_this_year_minor == 121  # 1330 / 11 = 120.9
    assert _line(s, w.owner.category_id).avg_monthly_overall_minor == 1_582  # 6330 / 4 buckets


def test_zero_budget_month_spent_stops_at_today(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    budgets_repo.clear_default(conn, OWNER_ID, w.owner.category_id)
    _txn(conn, OWNER_ID, w.owner, WORLD_TODAY, 5)
    _txn(conn, OWNER_ID, w.owner, WORLD_TODAY + timedelta(days=1), 900)
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert _line(s, w.owner.category_id).spent_minor == 1_005


def test_january_average_of_idle_category_is_zero(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    idle = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="idle", direction=Direction.EXPENSE)
    )
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        1,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert _line(s, idle.id).avg_this_year_minor == 0
    assert _line(s, idle.id).avg_monthly_overall_minor == 0


def test_line_carries_category_direction_and_color(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    painted = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="painted", direction=Direction.EXPENSE, color="#aa00bb")
    )
    s = budget.month_summary(
        conn,
        OWNER_ID,
        2026,
        11,
        today=WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    line = _line(s, painted.id)
    assert line.category_direction is Direction.EXPENSE
    assert line.category_color == painted.color == "#aa00bb"
    grid = budget.yearly_grid(conn, OWNER_ID, 2026, display_timezone=DEFAULT_DISPLAY_TIMEZONE)
    row = next(r for r in grid if r.category_id == painted.id)
    assert (row.category_direction, row.category_color) == (Direction.EXPENSE, "#aa00bb")


# ---------------------------------------------------------------------------
# anchor day and picker summaries
# ---------------------------------------------------------------------------
def test_picker_window_without_anchor_starts_on_the_first(conn: sqlite3.Connection) -> None:
    picked = budget.resolve_picker_month(conn, 1, date(2026, 3, 17), year_raw="2026", month_raw="5")
    s = budget.month_summary_for_picker(
        conn,
        1,
        picked,
        date(2026, 3, 17),
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert (s.period_start, s.next_income_date) == (date(2026, 5, 1), date(2026, 6, 1))
    assert s.days_until_next_income == 31


def test_picker_window_uses_active_anchor_rule_day_of_month_clamped(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    # sorts first (earlier start) but is inactive: its day must not be used
    _rule(
        conn,
        category_id=w.owner.income_category_id,
        account_id=w.owner.account_id,
        start=date(2026, 1, 5),
        next_due=date(2027, 1, 5),
        amount=1,
        day_of_month=5,
        active=False,
    )
    _rule(
        conn,
        category_id=w.owner.income_category_id,
        account_id=w.owner.account_id,
        start=date(2026, 2, 1),
        next_due=date(2026, 12, 31),
        amount=1,
        day_of_month=31,
    )
    picked = budget.resolve_picker_month(
        conn, OWNER_ID, WORLD_TODAY, year_raw="2027", month_raw="2"
    )
    s = budget.month_summary_for_picker(
        conn,
        OWNER_ID,
        picked,
        WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    # day 31 clamped per month: Feb 28 -> Mar 31
    assert (s.period_start, s.next_income_date) == (date(2027, 2, 28), date(2027, 3, 31))
    assert s.days_until_next_income == 31


def test_picker_window_day_one_rule_keeps_the_first(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    _rule(
        conn,
        category_id=w.owner.income_category_id,
        account_id=w.owner.account_id,
        start=date(2026, 1, 1),
        next_due=date(2026, 12, 1),
        amount=1,
        day_of_month=1,
    )
    picked = budget.resolve_picker_month(
        conn, OWNER_ID, WORLD_TODAY, year_raw="2027", month_raw="2"
    )
    s = budget.month_summary_for_picker(
        conn,
        OWNER_ID,
        picked,
        WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert (s.period_start, s.next_income_date) == (date(2027, 2, 1), date(2027, 3, 1))


def test_picker_window_closed_exactly_today_has_no_days_left(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    today = date(2026, 11, 1)
    picked = budget.resolve_picker_month(conn, OWNER_ID, today, year_raw="2026", month_raw="10")
    assert picked.is_fiscal is False
    s = budget.month_summary_for_picker(
        conn,
        OWNER_ID,
        picked,
        today,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert s.next_income_date == today
    assert s.days_until_next_income == 0


def test_picker_summary_zeroes_unbudgeted_commitments_and_derives_daily_spend_from_picked_month(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    free = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="free", direction=Direction.EXPENSE)
    )
    planned_repo.create(
        conn,
        OWNER_ID,
        NewPlannedTransaction(
            operation_date=PLANNED_DAY,
            category_id=free.id,
            account_id=w.owner.account_id,
            amount=333,
        ),
    )
    dec = budget.resolve_picker_month(conn, OWNER_ID, WORLD_TODAY, year_raw="2026", month_raw="12")
    s = budget.month_summary_for_picker(
        conn,
        OWNER_ID,
        dec,
        WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert s.totals.unbudgeted_committed_minor == 0
    assert s.totals.committed_minor == 0
    # reference day is Dec 12: no anchor after it, so the inner window ends Jan 1 (20 days);
    # committed (planned 500 + rules Nov 15 and Dec 15, 700 each) reduces the inner "left".
    assert s.left_daily_spend_minor == round(Decimal(3_000 - 1_900) / 20)
    feb = budget.resolve_picker_month(conn, OWNER_ID, WORLD_TODAY, year_raw="2027", month_raw="2")
    s2 = budget.month_summary_for_picker(
        conn,
        OWNER_ID,
        feb,
        WORLD_TODAY,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    # reference day Feb 12, 2027: window ends Mar 1 (17 days); 500 + 4 rule occurrences x 700
    assert s2.left_daily_spend_minor == round(Decimal(3_000 - 3_300) / 17)


# ---------------------------------------------------------------------------
# yearly_grid_totals
# ---------------------------------------------------------------------------
def _row(cat: int, amounts: list[int | None], total: int) -> budget.YearlyRow:
    return budget.YearlyRow(
        category_id=cat,
        category_name=f"c{cat}",
        category_direction=Direction.EXPENSE,
        category_color=None,
        cells=tuple(budget.YearlyCell(amount_minor=a, origin="default") for a in amounts),
        total_minor=total,
    )


def test_yearly_grid_totals_sum_columns_and_grand_total() -> None:
    a = _row(1, [i * 10 for i in range(1, 13)], 780)
    b = _row(2, [None, 5, None, 7, None, None, None, None, None, None, None, 1_000], 1_012)
    columns, grand = budget.yearly_grid_totals((a, b))
    assert columns == (10, 25, 30, 47, 50, 60, 70, 80, 90, 100, 110, 1_120)
    assert grand == 1_792
    assert budget.yearly_grid_totals(()) == ((0,) * 12, 0)


def test_yearly_grid_totals_over_real_grid(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    columns, grand = budget.yearly_grid_totals(
        budget.yearly_grid(conn, OWNER_ID, 2026, display_timezone=DEFAULT_DISPLAY_TIMEZONE)
    )
    assert columns == (3_000,) * 12
    assert grand == 36_000
