"""T-Q252: Plan hub (Forecast, Budget month picker, Year) rendered values equal service values."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

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
from tests.ui_map import _html, plan, plan_budget, plan_forecast, rd_fragments
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
    rows = _html.resolve(r.text, plan_forecast.rows)[1:]  # [0] is the header row
    assert len(rows) == DEFAULT_HORIZON
    first, last = _month_start(today, 0), _month_start(today, DEFAULT_HORIZON - 1)
    assert rows[0]["data-month"] == first.isoformat()
    assert rows[-1]["data-month"] == last.isoformat()
    month_of = role("columnheader")
    assert _html.texts(rows[0], month_of) == [first.strftime("%b %Y")]
    assert _html.texts(rows[-1], month_of) == [last.strftime("%b %Y")]
    # opening 1,000.00; 300.00 budgeted every month; 500.00 payday from the second month
    cells = [_row_cells(row) for row in rows]
    assert cells[0] == [
        "0.00 PLN",
        "0.00 PLN",
        "300.00 PLN",
        "\u25b2 \u2212300.00 PLN",
        "700.00 PLN",
    ]
    assert cells[1] == [
        "500.00 PLN",
        "0.00 PLN",
        "300.00 PLN",
        "200.00 PLN",
        "900.00 PLN",
    ]
    assert cells[2][-2:] == ["\u25b2 \u2212300.00 PLN", "600.00 PLN"]
    last_balance = OPENING_MINOR - DEFAULT_HORIZON * GROCERIES_BUDGET_MINOR + PAYDAY_MINOR
    assert last_balance == -210_000
    assert cells[-1][-1] == "\u22122,100.00 PLN"
    series = forecast_service.monthly_projection(
        db, USER_ID, _migrated, today, horizon=DEFAULT_HORIZON
    )
    assert [c[-1].replace("\u2212", "-") for c in cells] == [
        f"{format(Decimal(p.end_balance_minor) / 100, ',.2f')} PLN" for p in series
    ]


def test_forecast_tab_chart_has_one_point_per_month(
    client: TestClient, today: date, world: None
) -> None:
    r = client.get("/plan?tab=forecast")

    points = [str(el["aria-label"]) for el in _html.resolve(r.text, plan_forecast.chart_points)]
    assert len(points) == DEFAULT_HORIZON
    assert points[0] == f"{today.strftime('%b %Y')}: 700.00 PLN, net \u2212300.00"
    assert points[1].endswith(": 900.00 PLN, net +200.00")
    assert points[-1].endswith(": \u22122,100.00 PLN, net \u2212300.00")
    chart = _html.resolve_one(r.text, plan_forecast.chart)
    assert str(chart["aria-label"]).startswith(
        f"Projected balance by month, {today.strftime('%b %Y')} to "
    )


def test_forecast_tab_horizon_param(client: TestClient, world: None) -> None:
    r = client.get("/plan?tab=forecast&horizon=6")

    assert len(_html.resolve(r.text, plan_forecast.rows)[1:]) == 6
    assert len(_html.resolve(r.text, plan_forecast.chart_points)) == 6
    selected = _html.resolve_one(r.text, plan_forecast.horizon_selected)
    assert (selected.get_text(strip=True), selected["value"]) == ("6", "6")
    assert [b["hx-get"] for b in _html.resolve(r.text, plan_forecast.horizon_buttons)] == [
        f"/plan?tab=forecast&horizon={h}" for h in (6, 12, 24, 60)
    ]


def test_forecast_tab_defaults_to_twelve_months(client: TestClient, world: None) -> None:
    r = client.get("/plan?tab=forecast")

    assert _html.text_of(r.text, plan_forecast.horizon_selected) == "12"


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
    hero = _html.text_of(r.text, plan_budget.hero)
    note = _html.text_of(r.text, rd_fragments.period_picker)
    assert f"{start:%b}".lower() + f" = {start.day} {start:%b} → {nxt.day} {nxt:%b}".lower() in note
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
    assert "0.00 committed" in hero
    # Groceries default budget is the budget figure on that month's row.
    spent_cell = _html.texts(r.text, plan_budget.row_cells("Groceries"))[2]
    assert spent_cell.endswith(f"/ {GROCERIES_BUDGET_MINOR / 100:,.2f}")
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
    hero = _html.text_of(r.text, plan_budget.hero)
    assert f"{GROCERIES_BUDGET_MINOR / 100:,.2f} budgeted · 0.00 spent" in hero
    assert summary.days_until_next_income > 0


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


def test_forecast_hero_delta_is_measured_from_todays_net_worth(
    client: TestClient, db: sqlite3.Connection, _migrated: Settings, today: date, world: None
) -> None:
    series = forecast_service.monthly_projection(
        db, USER_ID, _migrated, today, horizon=DEFAULT_HORIZON
    )
    assert series[0].end_balance_minor != OPENING_MINOR  # the old behaviour showed this value

    r = client.get("/plan?tab=forecast")

    last = series[-1]
    text = _html.text_of(r.text, plan_forecast.hero)
    assert text.startswith(f"projected balance \u00b7 end of {last.month.strftime('%b').lower()} ")
    # net worth today 1,000.00; end -2,100.00; the strip says "-3,100.00 over 12 months"
    assert "\u22122,100.00 PLN \u22123,100.00 PLN over 12 months" in text, text
    assert " \u00b7 peak 900.00 in " in text, text


def test_forecast_chart_scrolls_sideways_as_a_keyboard_reachable_region(
    client: TestClient, world: None
) -> None:
    r = client.get("/plan?tab=forecast")

    region = _html.resolve_one(r.text, plan_forecast.chart_scroll)
    assert region["tabindex"] == "0"
    assert _html.count(r.text, plan_forecast.chart) == 1
