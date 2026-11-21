"""Tests for ``services.forecast.forecast_monthly`` (T-127, ADR-0043)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget_planner.config import Settings
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault, NewBudgetOneOffOverride
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.preferences import PREF_INCOME_ANCHOR_CATEGORY_ID
from budget_planner.domain.recurring import NewRecurringRule, PatchRecurringRule
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts,
    budgets as budgets_repo,
    categories,
    fx as fx_repo,
    planned,
    preferences as preferences_repo,
    recurring,
    transactions as transactions_repo,
)
from budget_planner.services import budget as budget_svc, forecast as forecast_svc, fx as fx_svc

USER_ID = 1


def _fx(conn: sqlite3.Connection) -> fx_svc.FxConverter:
    """Cache-only converter at TODAY (ADR-0139)."""
    return fx_svc.converter_for(conn, Settings(_env_file=None), TODAY)


TODAY = date(2026, 10, 23)


@pytest.fixture
def world(conn: sqlite3.Connection) -> dict[str, int]:
    a1 = accounts.create(
        conn, USER_ID, NewAccount(name="Checking", currency="PLN", opening_balance=100_000)
    ).id
    a2 = accounts.create(conn, USER_ID, NewAccount(name="Savings", currency="PLN")).id
    a3 = accounts.create(
        conn, USER_ID, NewAccount(name="EUR Cash", currency="EUR", opening_balance=50_000)
    ).id
    salary = categories.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    ).id
    groceries = categories.create(
        conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id
    rent = categories.create(
        conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id
    transit = categories.find_by_name(conn, USER_ID, "Transit")
    assert transit is not None

    fx_repo.upsert_rate(
        conn,
        NewFxRate(date=TODAY, from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.30")),
    )
    return {
        "a1": a1,
        "a2": a2,
        "a3": a3,
        "salary": salary,
        "groceries": groceries,
        "rent": rent,
        "transit": transit.id,
    }


def _row_for(series: forecast_svc.MonthlySeries, month: date) -> forecast_svc.MonthlyPoint:
    for r in series.months:
        if r.month == month:
            return r
    raise AssertionError(f"month {month} missing from monthly series")


def test_horizon_days_for_months_spans_full_month() -> None:
    # 2026-10-23 + 3 months -> last month = 2026-12, last day = 2026-12-31
    assert forecast_svc.horizon_days_for_months(TODAY, 3) == (date(2026, 12, 31) - TODAY).days


def test_shape_single_month(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    _ = world
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 1)
    assert monthly.base_currency == "PLN"
    assert len(monthly.months) == 1
    assert monthly.months[0].month == date(2026, 10, 1)
    assert monthly.start_month == monthly.end_month == date(2026, 10, 1)


def test_shape_multi_month(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    _ = world
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 4)
    expected = [date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)]
    assert [r.month for r in monthly.months] == expected
    assert monthly.start_month == date(2026, 10, 1)
    assert monthly.end_month == date(2027, 1, 1)


def test_income_sum_in_month(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 15),
            category_id=world["salary"],
            account_id=world["a1"],
            amount=800_000,
            description="payday",
        ),
    )
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 3)
    nov = _row_for(monthly, date(2026, 11, 1))
    assert nov.income_base_minor == 800_000
    assert nov.expense_base_minor == 0
    assert nov.net_base_minor == 800_000


def test_expense_sum_in_month_includes_recurring(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 10, 1),
            category_id=world["rent"],
            account_id=world["a1"],
            default_amount=300_000,
            default_description="rent",
        ),
    )
    recurring.set_next_due(
        conn, USER_ID, rule.id, next_due=date(2026, 11, 1), last_promoted_date=None
    )
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 20),
            category_id=world["groceries"],
            account_id=world["a1"],
            amount=10_000,
            description="groceries",
        ),
    )
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 3)
    nov = _row_for(monthly, date(2026, 11, 1))
    # Rent 300_000 (recurring) + groceries 10_000 (planned)
    assert nov.expense_base_minor == 310_000
    assert nov.income_base_minor == 0
    assert nov.net_base_minor == -310_000


def test_transit_excluded_from_income_expense(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 5),
            category_id=world["transit"],
            account_id=world["a1"],
            dest_account_id=world["a2"],
            amount=20_000,
            description="savings sweep",
        ),
    )
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 2)
    nov = _row_for(monthly, date(2026, 11, 1))
    assert nov.income_base_minor == 0
    assert nov.expense_base_minor == 0
    assert nov.net_base_minor == 0


def test_end_balance_matches_daily_eom(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 10),
            category_id=world["salary"],
            account_id=world["a1"],
            amount=800_000,
            description="payday",
        ),
    )
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 2)
    daily = forecast_svc.forecast(
        conn,
        USER_ID,
        _fx(conn),
        TODAY,
        forecast_svc.horizon_days_for_months(TODAY, 2),
    )
    eom_nov = next(d for d in daily.days if d.on_date == date(2026, 11, 30))
    nov = _row_for(monthly, date(2026, 11, 1))
    assert nov.end_balance_base_minor == eom_nov.totals_base_minor


def test_empty_accounts_returns_zero_rows(conn: sqlite3.Connection) -> None:
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 3)
    assert len(monthly.months) == 3
    assert all(r.income_base_minor == 0 for r in monthly.months)
    assert all(r.expense_base_minor == 0 for r in monthly.months)
    assert all(r.end_balance_base_minor == 0 for r in monthly.months)


def test_fx_conversion_on_foreign_account(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 10),
            category_id=world["salary"],
            account_id=world["a3"],  # EUR account
            amount=1_000,  # 10.00 EUR
            description="eur payday",
        ),
    )
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 2)
    nov = _row_for(monthly, date(2026, 11, 1))
    # 1_000 EUR minor * 4.30 = 4_300 PLN minor.
    assert nov.income_base_minor == 4_300


def test_negative_horizon_months_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="horizon_months"):
        forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 0)


def test_planned_budget_sums_default_budget_across_expense_cats(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    budgets_repo.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["groceries"], amount=50_000)
    )
    budgets_repo.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["rent"], amount=300_000)
    )
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 2)
    for row in monthly.months:
        assert row.planned_budget_base_minor == 350_000


def test_planned_budget_one_off_override_wins_for_that_month(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    budgets_repo.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["groceries"], amount=50_000)
    )
    budgets_repo.set_one_off(
        conn,
        USER_ID,
        NewBudgetOneOffOverride(
            category_id=world["groceries"], year=2026, month=11, amount=120_000
        ),
    )
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 3)
    oct_row = _row_for(monthly, date(2026, 10, 1))
    nov_row = _row_for(monthly, date(2026, 11, 1))
    dec_row = _row_for(monthly, date(2026, 12, 1))
    assert oct_row.planned_budget_base_minor == 50_000
    assert nov_row.planned_budget_base_minor == 120_000
    assert dec_row.planned_budget_base_minor == 50_000


def test_net_subtracts_planned_budget(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 15),
            category_id=world["salary"],
            account_id=world["a1"],
            amount=800_000,
            description="payday",
        ),
    )
    budgets_repo.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["groceries"], amount=50_000)
    )
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 2)
    nov = _row_for(monthly, date(2026, 11, 1))
    assert nov.income_base_minor == 800_000
    assert nov.expense_base_minor == 0
    assert nov.planned_budget_base_minor == 50_000
    assert nov.net_base_minor == 800_000 - 0 - 50_000


def test_planned_budget_zero_when_no_budgets_set(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    _ = world
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 2)
    for row in monthly.months:
        assert row.planned_budget_base_minor == 0


def test_planned_budget_ignores_income_categories(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    budgets_repo.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["salary"], amount=999_999)
    )
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 2)
    for row in monthly.months:
        assert row.planned_budget_base_minor == 0


def test_planned_budget_clamped_when_committed_exceeds_resolved(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    # Budget 10_000 but a 50_000 grocery expense committed this month -> clamp to 0.
    budgets_repo.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["groceries"], amount=10_000)
    )
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 10, 30),
            category_id=world["groceries"],
            account_id=world["a1"],
            amount=50_000,
            description="big grocery run",
        ),
    )
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 1)
    row = _row_for(monthly, date(2026, 10, 1))
    assert row.planned_budget_base_minor == 0


def test_current_month_row_mirrors_budget_month_summary(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Current-row Expenses + Planned budget must equal month_summary totals."""
    # Budget 500_000 for groceries, 300_000 recurring rent -> both expense cats.
    budgets_repo.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["groceries"], amount=500_000)
    )
    budgets_repo.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["rent"], amount=300_000)
    )
    # Planned grocery expense inside anchor window (Oct 29).
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 10, 29),
            category_id=world["groceries"],
            account_id=world["a1"],
            amount=70_000,
            description="groceries",
        ),
    )
    # Recurring rent monthly, next_due inside Oct.
    recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 10, 25),
            category_id=world["rent"],
            account_id=world["a1"],
            default_amount=300_000,
            default_description="rent",
        ),
    )
    summary = budget_svc.month_summary(conn, USER_ID, TODAY.year, TODAY.month, today=TODAY)
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 2)
    oct_row = _row_for(monthly, date(2026, 10, 1))
    assert (
        oct_row.expense_base_minor
        == summary.totals.committed_minor + summary.totals.unbudgeted_committed_minor
    )
    assert oct_row.planned_budget_base_minor == max(summary.totals.remaining_minor, 0)


def test_future_month_row_keeps_calendar_logic(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Future rows use calendar-month flows + residual-budget math."""
    budgets_repo.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["groceries"], amount=100_000)
    )
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 10),
            category_id=world["groceries"],
            account_id=world["a1"],
            amount=30_000,
            description="nov groceries",
        ),
    )
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 2)
    nov = _row_for(monthly, date(2026, 11, 1))
    assert nov.expense_base_minor == 30_000  # calendar-month event sum
    # Resolved 100_000 - already-committed 30_000 = residual 70_000.
    assert nov.planned_budget_base_minor == 70_000


def test_current_month_eom_absorbs_remaining_budget_overlay(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    _ = world
    # Budget 100_000 PLN for groceries this month, no planned/actual spending yet.
    # Overlay should distribute the 100_000 across remaining days, dropping EOM
    # by exactly that amount vs. the pre-overlay projection.
    budgets_repo.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["groceries"], amount=100_000)
    )
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 1)
    pre_overlay = forecast_svc.forecast(
        conn,
        USER_ID,
        _fx(conn),
        TODAY,
        forecast_svc.horizon_days_for_months(TODAY, 1),
        include_budget_overlay=False,
    )
    oct_row = _row_for(monthly, date(2026, 10, 1))
    pre_eom = pre_overlay.days[-1].totals_base_minor
    assert oct_row.end_balance_base_minor == pre_eom - 100_000
    assert oct_row.planned_budget_base_minor == 100_000


def test_fiscal_row_eom_equals_current_plus_net_after_calendar_boundary(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Regression: fiscal row EOM must reconcile with its own Net column.

    When today has crossed into the next calendar month but the fiscal cycle
    (anchored on the previous paycheck) is still open, the fiscal row's
    calendar-month end is in the past. Deriving EOM from a historical
    month-end balance leaves the row with an EOM that cannot be reconciled
    with its Expenses + Planned budget columns (see docs/CHANGELOG issue:
    "Accounts/Today net worth vs. Plan/Forecast EOM mismatch").

    The fix anchors EOM to ``current_net_worth + net`` for the fiscal row so
    the user-visible identity ``current + Net = EOM`` always holds.
    """
    # Anchor on salary; promoted paycheck on Oct 25 so fiscal_month_for(Nov 1)
    # returns (2026, 10).
    preferences_repo.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, str(world["salary"]))
    transactions_repo.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 10, 25),
            category_id=world["salary"],
            account_id=world["a1"],
            amount=500_000,
        ),
    )
    budgets_repo.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["groceries"], amount=100_000)
    )
    today = date(2026, 11, 1)
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), today, 1)
    daily = forecast_svc.forecast(conn, USER_ID, _fx(conn), today, 0)
    current_net_worth = daily.days[0].totals_base_minor
    oct_row = _row_for(monthly, date(2026, 10, 1))
    assert oct_row.end_balance_base_minor == current_net_worth + oct_row.net_base_minor


def test_eom_chain_each_row_equals_prev_eom_plus_net(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """EOM is a running chain: EOM_N = EOM_{N-1} + Net_N anchored at current.

    Regression guard against future refactors that reintroduce a mix of
    daily-projection EOMs and chain-anchored EOMs across the fiscal /
    calendar boundary — the symptom was the fiscal row showing
    current+Net but the next row ignoring that anchor and jumping back
    to a daily projection, so the user-visible gap re-appeared on the
    row after the fiscal row.
    """
    budgets_repo.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["groceries"], amount=100_000)
    )
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 10),
            category_id=world["groceries"],
            account_id=world["a1"],
            amount=30_000,
            description="nov groceries",
        ),
    )
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 3)
    daily = forecast_svc.forecast(conn, USER_ID, _fx(conn), TODAY, 0)
    prev = daily.days[0].totals_base_minor
    for row in monthly.months:
        assert row.end_balance_base_minor == prev + row.net_base_minor, (
            f"chain broken at {row.month}: expected {prev + row.net_base_minor}, "
            f"got {row.end_balance_base_minor}"
        )
        prev = row.end_balance_base_minor


# ---------------------------------------------------------------------------
# ADR-0105: current-period Expenses includes every overdue item (T-D115)
# ---------------------------------------------------------------------------
def _planned_expense(
    conn: sqlite3.Connection, world: dict[str, int], cat: str, on: date, amount: int
) -> None:
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=on, category_id=world[cat], account_id=world["a1"], amount=amount
        ),
    )


def _overdue_rule(
    conn: sqlite3.Connection, world: dict[str, int], cat: str, next_due: date, amount: int
) -> None:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=next_due,
            category_id=world[cat],
            account_id=world["a1"],
            default_amount=amount,
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=next_due))


def test_current_row_expenses_include_overdue_planned_and_recurring(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    budgets_repo.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["groceries"], amount=500_000)
    )
    _planned_expense(conn, world, "groceries", date(2026, 8, 1), 1_000)  # old overdue
    _planned_expense(conn, world, "groceries", date(2026, 10, 20), 2_000)  # overdue
    _planned_expense(conn, world, "groceries", TODAY, 4_000)  # due today
    _planned_expense(conn, world, "groceries", date(2026, 10, 29), 8_000)  # upcoming
    _overdue_rule(conn, world, "groceries", date(2026, 10, 10), 16_000)  # overdue recurring
    monthly = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 2)
    oct_row = _row_for(monthly, date(2026, 10, 1))
    assert oct_row.expense_base_minor == 31_000
    assert oct_row.planned_budget_base_minor == 500_000 - 31_000


def test_current_row_unbudgeted_overdue_lowers_eom(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Overdue items in categories without a budget must still leave the balance."""
    budgets_repo.set_default(
        conn, USER_ID, NewBudgetDefault(category_id=world["groceries"], amount=500_000)
    )
    before = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 1)
    _planned_expense(conn, world, "rent", date(2026, 9, 15), 3_000)
    _overdue_rule(conn, world, "rent", date(2026, 10, 15), 5_000)
    after = forecast_svc.forecast_monthly(conn, USER_ID, _fx(conn), TODAY, 1)
    oct_before, oct_after = before.months[0], after.months[0]
    assert oct_after.expense_base_minor - oct_before.expense_base_minor == 8_000
    assert oct_before.end_balance_base_minor - oct_after.end_balance_base_minor == 8_000
