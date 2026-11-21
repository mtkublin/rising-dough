"""T-Q252: Plan hub (Forecast, Budget month picker, Year) rendered values equal service values."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from budget_planner import clock
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


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


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
        assert point.value_major == point.end_balance_minor / 100


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
    soup = _soup(r.text)
    rows = soup.select("tr[data-month]")
    assert len(rows) == DEFAULT_HORIZON
    first, last = _month_start(today, 0), _month_start(today, DEFAULT_HORIZON - 1)
    assert rows[0]["data-month"] == first.isoformat()
    assert rows[-1]["data-month"] == last.isoformat()
    assert rows[0].select("td")[0].get_text(strip=True) == first.strftime("%b %Y")
    assert rows[-1].select("td")[0].get_text(strip=True) == last.strftime("%b %Y")
    caption = soup.select_one("#forecast-caption")
    assert caption is not None
    assert f"{first.strftime('%b %Y')} — {last.strftime('%b %Y')}" in " ".join(
        caption.get_text().split()
    )
    series = forecast_service.monthly_projection(
        db, USER_ID, _migrated, today, horizon=DEFAULT_HORIZON
    )
    end_cells = [row.select_one(".rd-forecast__eom") for row in rows]
    assert [c.get_text(strip=True) for c in end_cells if c] == [
        f"{p.end_balance_minor / 100:,.2f}" for p in series
    ]
    last_balance = OPENING_MINOR - DEFAULT_HORIZON * GROCERIES_BUDGET_MINOR + PAYDAY_MINOR
    assert last_balance == -210_000
    assert end_cells[-1] is not None
    assert end_cells[-1].get_text(strip=True) == "-2,100.00"


def test_forecast_tab_horizon_param(client: TestClient, world: None) -> None:
    r = client.get("/plan?tab=forecast&horizon=6")

    assert len(_soup(r.text).select("tr[data-month]")) == 6


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
    soup = _soup(r.text)
    period = soup.select_one(".rd-period-bar__range")
    assert period is not None
    assert period.get_text(strip=True) == f"{start.day} {start:%b} → {nxt.day} {nxt:%b}"
    picked = budget_service.resolve_picker_month(
        db, USER_ID, today, year_raw=str(start.year), month_raw=str(start.month)
    )
    summary = budget_service.month_summary_for_picker(db, USER_ID, picked=picked, today=today)
    assert summary.totals.committed_minor == 0
    assert summary.period_start == start
    assert summary.next_income_date == nxt
    meta = soup.select_one(".rd-period-bar__right .rd-period-bar__meta")
    assert meta is not None
    assert meta.get_text(" ", strip=True).startswith("0.00 committed")
    assert f"{summary.days_until_next_income} days left" in meta.get_text()
    # Groceries default budget is the planned figure on that month's row.
    planned_cells = [td.get_text(strip=True) for td in soup.select("#plan-budget tbody td.num")]
    assert f"{GROCERIES_BUDGET_MINOR / 100:,.2f}" in planned_cells
    assert month_bounds(start.year, start.month)[0] == start


def test_budget_month_future_has_no_days_elapsed_pressure(
    client: TestClient, db: sqlite3.Connection, today: date, world: None
) -> None:
    start = _month_start(today, 3)
    picked = budget_service.resolve_picker_month(
        db, USER_ID, today, year_raw=str(start.year), month_raw=str(start.month)
    )
    summary = budget_service.month_summary_for_picker(db, USER_ID, picked=picked, today=today)

    r = client.get(f"/plan?tab=budget&year={start.year}&month={start.month}")

    assert summary.totals.spent_minor == 0
    assert summary.totals.budgeted_minor == GROCERIES_BUDGET_MINOR
    assert f"{summary.days_until_next_income} days left" in r.text


def test_year_tab_grid_and_totals(
    client: TestClient, db: sqlite3.Connection, today: date, world: None
) -> None:
    r = client.get(f"/plan?tab=year&year={today.year}")

    assert r.status_code == 200
    soup = _soup(r.text)
    rows = soup.select(".rd-plan-year__table tbody tr")
    assert len(rows) == 1
    cells = rows[0].select("td.rd-plan-year__cell")
    assert len(cells) == 12
    grid = budget_service.yearly_grid(db, USER_ID, today.year)
    assert [cell.amount_minor for cell in grid[0].cells] == [GROCERIES_BUDGET_MINOR] * 12
    total = rows[0].select("td.num")[-1].get_text(strip=True)
    assert total == f"{12 * GROCERIES_BUDGET_MINOR / 100:,.0f}"
    footer = [td.get_text(strip=True) for td in soup.select(".rd-plan-year__table tfoot td.num")]
    assert footer[-1] == total
    assert footer[:-1] == [f"{GROCERIES_BUDGET_MINOR / 100:,.0f}"] * 12
    heading = soup.select_one("#plan-year-heading")
    assert heading is not None
    assert heading.get_text(strip=True) == f"Year · {today.year}"
