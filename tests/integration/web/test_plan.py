"""T-Q252: Plan hub (Forecast, Budget month picker, Year) rendered values equal service values."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest
from bs4 import Tag
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.clock import DEFAULT_DISPLAY_TIMEZONE
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.periods import month_bounds, shift_month
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    planned as planned_repo,
)
from budget_planner.services import budget as budget_service, forecast as forecast_service
from tests.ui_map import _html, plan
from tests.ui_map.locator import role

USER_ID = 1
OPENING_MINOR = 100_000
PAYDAY_MINOR = 50_000
GROCERIES_BUDGET_MINOR = 30_000
DEFAULT_HORIZON = 12


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def today(_migrated: Settings) -> date:
    return clock.today_local(_migrated)


def _row_cells(row: Tag) -> list[str]:
    return _html.texts(row, role("cell"))


def _month_start(today: date, delta: int) -> date:
    year, month = shift_month(today.year, today.month, delta)
    return date(year, month, 1)


@pytest.fixture
def world(db: sqlite3.Connection, today: date) -> None:
    """One PLN account (10.00 thousand grosz), a budgeted category and next month's payday."""
    account = accounts_repo.create(
        db, USER_ID, NewAccount(name="Checking", currency="PLN", opening_balance=OPENING_MINOR)
    )
    salary = categories_repo.create(
        db, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    )
    groceries = categories_repo.create(
        db, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    )
    budgets_repo.set_default(
        db, USER_ID, NewBudgetDefault(category_id=groceries.id, amount=GROCERIES_BUDGET_MINOR)
    )
    next_month = _month_start(today, 1)
    planned_repo.create(
        db,
        USER_ID,
        NewPlannedTransaction(
            operation_date=next_month.replace(day=15),
            category_id=salary.id,
            account_id=account.id,
            amount=PAYDAY_MINOR,
            description="payday",
        ),
    )


def test_monthly_projection_series_and_balances(
    db: sqlite3.Connection, _migrated: Settings, today: date, world: None
) -> None:
    series = forecast_service.monthly_projection(db, USER_ID, _migrated, today, horizon=3)

    this_month = _month_start(today, 0)
    assert [p.month for p in series] == [
        this_month,
        _month_start(today, 1),
        _month_start(today, 2),
    ]
    assert [p.label for p in series] == [p.month.strftime("%b %Y") for p in series]
    # The groceries budget is spent down every month (overlay); payday lands in month two.
    assert [p.end_balance_minor for p in series] == [
        OPENING_MINOR - 1 * GROCERIES_BUDGET_MINOR,
        OPENING_MINOR - 2 * GROCERIES_BUDGET_MINOR + PAYDAY_MINOR,
        OPENING_MINOR - 3 * GROCERIES_BUDGET_MINOR + PAYDAY_MINOR,
    ]
    assert [p.planned_budget_minor for p in series] == [GROCERIES_BUDGET_MINOR] * 3
    assert series[1].income_minor == PAYDAY_MINOR
    assert series[0].income_minor == 0
    assert series[2].income_minor == 0
    for point in series:
        assert (
            point.net_minor == point.income_minor - point.expense_minor - point.planned_budget_minor
        )


def test_monthly_projection_horizon_sets_length(
    db: sqlite3.Connection, _migrated: Settings, today: date, world: None
) -> None:
    for horizon in (1, 6):
        series = forecast_service.monthly_projection(db, USER_ID, _migrated, today, horizon=horizon)
        assert len(series) == horizon
        assert series[-1].month == _month_start(today, horizon - 1)


def test_monthly_projection_empty_world_is_flat_zero(
    db: sqlite3.Connection, _migrated: Settings, today: date
) -> None:
    series = forecast_service.monthly_projection(db, USER_ID, _migrated, today, horizon=2)

    assert [p.end_balance_minor for p in series] == [0, 0]
    assert [p.income_minor for p in series] == [0, 0]
    assert [p.expense_minor for p in series] == [0, 0]


def test_forecast_tab_series_labels_and_end_balance(
    client: TestClient, db: sqlite3.Connection, _migrated: Settings, today: date, world: None
) -> None:
    r = client.get("/plan?tab=forecast")

    assert r.status_code == 200
    rows = _html.resolve(r.text, plan.forecast_projection_rows)[1:]  # [0] is the header row
    assert len(rows) == DEFAULT_HORIZON
    first, last = _month_start(today, 0), _month_start(today, DEFAULT_HORIZON - 1)
    assert rows[0]["data-month"] == first.isoformat()
    assert rows[-1]["data-month"] == last.isoformat()
    assert _row_cells(rows[0])[0] == first.strftime("%b %Y")
    assert _row_cells(rows[-1])[0] == last.strftime("%b %Y")
    caption = _html.text_of(r.text, plan.forecast_caption)
    assert f"{first.strftime('%b %Y')} — {last.strftime('%b %Y')}" in caption
    series = forecast_service.monthly_projection(
        db, USER_ID, _migrated, today, horizon=DEFAULT_HORIZON
    )
    end_cells = [_row_cells(row)[-1] for row in rows]  # EOM is the last column
    assert end_cells == [f"{p.end_balance_minor / 100:,.2f}" for p in series]
    last_balance = OPENING_MINOR - DEFAULT_HORIZON * GROCERIES_BUDGET_MINOR + PAYDAY_MINOR
    assert last_balance == -210_000
    assert end_cells[-1] == "-2,100.00"


def test_forecast_tab_horizon_param(client: TestClient, world: None) -> None:
    r = client.get("/plan?tab=forecast&horizon=6")

    assert len(_html.resolve(r.text, plan.forecast_projection_rows)[1:]) == 6


@pytest.mark.parametrize(("delta", "label"), [(-2, "past"), (3, "future")])
def test_budget_month_committed_zero_and_period_dates(
    client: TestClient,
    *,
    db: sqlite3.Connection,
    today: date,
    world: None,
    delta: int,
    label: str,
) -> None:
    start = _month_start(today, delta)
    nxt = _month_start(today, delta + 1)

    r = client.get(f"/plan?tab=budget&year={start.year}&month={start.month}")

    assert r.status_code == 200, label
    region = _html.text_of(r.text, plan.period_region)
    assert f"{start.day} {start:%b} → {nxt.day} {nxt:%b}" in region
    picked = budget_service.resolve_picker_month(
        db, USER_ID, today, year_raw=str(start.year), month_raw=str(start.month)
    )
    summary = budget_service.month_summary_for_picker(
        db,
        USER_ID,
        picked=picked,
        today=today,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    assert summary.totals.committed_minor == 0
    assert summary.period_start == start
    assert summary.next_income_date == nxt
    assert "0.00 committed" in region
    assert f"{summary.days_until_next_income} days left" in region
    # Groceries default budget is the planned figure on that month's row.
    planned_cells = _html.texts(r.text, plan.budget_row_cells)
    assert f"{GROCERIES_BUDGET_MINOR / 100:,.2f}" in planned_cells
    assert month_bounds(start.year, start.month)[0] == start


def test_budget_month_future_has_no_days_elapsed_pressure(
    client: TestClient, db: sqlite3.Connection, today: date, world: None
) -> None:
    start = _month_start(today, 3)
    picked = budget_service.resolve_picker_month(
        db, USER_ID, today, year_raw=str(start.year), month_raw=str(start.month)
    )
    summary = budget_service.month_summary_for_picker(
        db,
        USER_ID,
        picked=picked,
        today=today,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )

    r = client.get(f"/plan?tab=budget&year={start.year}&month={start.month}")

    assert summary.totals.spent_minor == 0
    assert summary.totals.budgeted_minor == GROCERIES_BUDGET_MINOR
    assert f"{summary.days_until_next_income} days left" in _html.text_of(
        r.text, plan.period_region
    )


def test_year_tab_grid_and_totals(
    client: TestClient, db: sqlite3.Connection, today: date, world: None
) -> None:
    r = client.get(f"/plan?tab=year&year={today.year}")

    assert r.status_code == 200
    rows = _html.resolve(r.text, plan.year_body_rows)
    body = [row for row in rows if _html.resolve(row, role("cell"))]
    assert len(body) == 2  # one category row + the totals footer row
    cells = _html.resolve(r.text, plan.year_cell_open_any)
    assert len(cells) == 12
    grid = budget_service.yearly_grid(
        db, USER_ID, today.year, display_timezone=DEFAULT_DISPLAY_TIMEZONE
    )
    assert [cell.amount_minor for cell in grid[0].cells] == [GROCERIES_BUDGET_MINOR] * 12
    total = _row_cells(body[0])[-1]
    assert total == f"{12 * GROCERIES_BUDGET_MINOR / 100:,.0f}"
    footer = _row_cells(body[1])[1:]  # [0] is the "Total" label
    assert footer[-1] == total
    assert footer[:-1] == [f"{GROCERIES_BUDGET_MINOR / 100:,.0f}"] * 12
    assert _html.text_of(r.text, plan.year_heading) == f"Year · {today.year}"


def test_forecast_summary_now_is_todays_net_worth_not_first_month_end(
    client: TestClient, db: sqlite3.Connection, _migrated: Settings, today: date, world: None
) -> None:
    series = forecast_service.monthly_projection(
        db, USER_ID, _migrated, today, horizon=DEFAULT_HORIZON
    )
    assert series[0].end_balance_minor != OPENING_MINOR  # the old behaviour showed this value

    r = client.get("/plan?tab=forecast")

    text = _html.text_of(r.text, plan.forecast_summary)
    assert text.startswith("Now 1,000 PLN"), text
    assert f"End · {series[-1].label} -2,100 PLN" in text, text
