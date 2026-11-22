"""T-Q279: archived categories reserve no budget from the archive month on; actuals still count.

ADR-0136 amendment 2026-11-22. Category "dining" has a default budget of 30_000 and a posted
expense of 4_500 in October; it is archived on 2026-11-10 (UTC), so November is the archive month.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.services import (
    analytics,
    balance,
    budget,
    budget_batch,
    categories as categories_svc,
    forecast as fc,
    forecast_overlay,
    fx as fx_svc,
)

OWNER, OTHER = 1, 2
TODAY = date(2026, 11, 15)
BUDGET = 30_000
SPENT = 4_500
ARCHIVED_AT = "2026-11-10T10:00:00.000Z"
OCT, NOV, DEC = (2026, 10), (2026, 11), (2026, 12)


def _seed(conn: sqlite3.Connection, user_id: int) -> tuple[int, int]:
    """Account + archived expense category with budget and one October expense."""
    if user_id != OWNER:
        conn.execute(
            "INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)",
            (user_id, f"u{user_id}", f"u{user_id}@example.test", "x"),
        )
    acct = accounts_repo.create(
        conn, user_id, NewAccount(name=f"acct-{user_id}", currency="PLN", opening_balance=100_000)
    ).id
    cat = categories_repo.create(
        conn, user_id, NewCategory(name=f"dining-{user_id}", direction=Direction.EXPENSE)
    ).id
    budgets_repo.set_default(conn, user_id, NewBudgetDefault(category_id=cat, amount=BUDGET))
    transactions_repo.create(
        conn,
        user_id,
        NewTransaction(
            operation_date=date(2026, 10, 20), category_id=cat, account_id=acct, amount=SPENT
        ),
    )
    categories_repo.soft_delete(conn, user_id, cat)
    conn.execute("UPDATE categories SET deleted_at = ? WHERE id = ?", (ARCHIVED_AT, cat))
    return acct, cat


def _fx() -> fx_svc.FxConverter:
    return fx_svc.build_converter("PLN", TODAY, [])


def _summary(
    conn: sqlite3.Connection, ym: tuple[int, int], user_id: int = OWNER
) -> budget.MonthSummary:
    return budget.month_summary(
        conn, user_id, *ym, today=TODAY, base_currency="PLN", period_window=(date(*ym, 1), TODAY)
    )


def test_past_month_keeps_the_budget_and_the_actual(conn: sqlite3.Connection) -> None:
    _, cat = _seed(conn, OWNER)
    summary = _summary(conn, OCT)
    line = next(ln for ln in summary.lines if ln.category_id == cat)
    assert (line.budgeted_minor, summary.totals.budgeted_minor) == (BUDGET, BUDGET)
    row = next(r for r in budget.yearly_grid(conn, OWNER, 2026) if r.category_id == cat)
    assert [c.amount_minor for c in row.cells] == [BUDGET] * 10 + [None, None]
    assert row.total_minor == 10 * BUDGET


@pytest.mark.parametrize("ym", [NOV, DEC])
def test_archive_month_and_later_reserve_nothing(
    conn: sqlite3.Connection, ym: tuple[int, int]
) -> None:
    _, cat = _seed(conn, OWNER)
    summary = _summary(conn, ym)
    assert cat not in {ln.category_id for ln in summary.lines}
    assert summary.totals.budgeted_minor == 0
    assert budget_batch.budget_resolver(conn, OWNER)(cat, *ym) is None
    assert budget_batch.budget_resolver(conn, OWNER)(cat, *OCT) == BUDGET
    assert cat not in categories_svc.budgeted_expense_category_ids(conn, OWNER, *ym)
    assert cat in categories_svc.budgeted_expense_category_ids(conn, OWNER, *OCT)
    # the actuals selector still lists it
    assert cat in categories_svc.expense_category_ids(conn, OWNER)


def test_yearly_grid_drops_the_row_in_a_later_year(conn: sqlite3.Connection) -> None:
    _, cat = _seed(conn, OWNER)
    assert cat not in {r.category_id for r in budget.yearly_grid(conn, OWNER, 2027)}


def test_forecast_overlay_and_monthly_budget_add_zero_from_the_archive_month(
    conn: sqlite3.Connection,
) -> None:
    acct, _ = _seed(conn, OWNER)
    fx = _fx()
    events = forecast_overlay.collect_budget_overlay(
        conn, OWNER, today=TODAY, end_date=date(2026, 12, 31), primary_account_id=acct, fx=fx
    )
    assert events == []
    planned = fc._planned_budget_per_month(conn, OWNER, TODAY, 2, fx=fx)
    assert planned == {date(2026, 11, 1): 0, date(2026, 12, 1): 0}
    # the previous month (an anchor in the past) would still reserve it
    before = fc._planned_budget_per_month(
        conn, OWNER, TODAY, 1, fx=fx, start_month=date(2026, 10, 1)
    )
    assert before == {date(2026, 10, 1): BUDGET - SPENT}


def test_timezone_decides_the_archive_month(conn: sqlite3.Connection) -> None:
    """2026-10-31T23:30Z is already November in Europe/Warsaw (ADR-0007)."""
    _, cat = _seed(conn, OWNER)
    conn.execute(
        "UPDATE categories SET deleted_at = '2026-10-31T23:30:00.000Z' WHERE id = ?", (cat,)
    )
    resolve = budget_batch.budget_resolver(conn, OWNER, display_timezone="Europe/Warsaw")
    assert resolve(cat, *OCT) == BUDGET
    resolve_utc = budget_batch.budget_resolver(conn, OWNER, display_timezone="UTC")
    assert resolve_utc(cat, *OCT) is None


def test_actuals_still_count(conn: sqlite3.Connection) -> None:
    acct, cat = _seed(conn, OWNER)
    transactions_repo.create(
        conn,
        OWNER,
        NewTransaction(
            operation_date=date(2026, 11, 12), category_id=cat, account_id=acct, amount=700
        ),
    )
    fx = _fx()
    assert balance.as_of_today(conn, OWNER, acct, TODAY) == 100_000 - SPENT - 700
    october = analytics.bundle(conn, OWNER, fx, today=date(2026, 10, 31), period="month")
    assert analytics.spend_total_minor(october) == SPENT
    november = analytics.bundle(conn, OWNER, fx, today=TODAY, period="month")
    assert analytics.spend_total_minor(november) == 700
    series = fc.forecast(conn, OWNER, fx, TODAY, 0, include_budget_overlay=False)
    assert series.days[0].totals_base_minor == 100_000 - SPENT - 700


def test_second_users_archived_category_changes_nothing(conn: sqlite3.Connection) -> None:
    _seed(conn, OWNER)
    before = _summary(conn, OCT).totals.budgeted_minor
    _seed(conn, OTHER)
    assert _summary(conn, OCT).totals.budgeted_minor == before == BUDGET
    assert _summary(conn, OCT, OTHER).totals.budgeted_minor == BUDGET
