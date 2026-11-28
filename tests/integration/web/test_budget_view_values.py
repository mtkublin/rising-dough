"""T-Q237 (Q-039): budget numbers on Today, Plan and Budget equal the service values."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any, cast

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.clock import DEFAULT_DISPLAY_TIMEZONE
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    planned as planned_repo,
    transactions as transactions_repo,
)
from budget_planner.services import budget as budget_service
from budget_planner.web import view_models
from tests.ui_map import _html, plan_budget, today as today_ui

USER_ID = 1
BUDGET_MINOR = 100_000
SPENT_MINOR = 25_000
CCY = "PLN"


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


@pytest.fixture
def world(db: sqlite3.Connection, today: date) -> None:
    account = accounts_repo.create(
        db, USER_ID, NewAccount(name="Checking", currency=CCY, opening_balance=500_000)
    )
    groceries = categories_repo.create(
        db, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    )
    budgets_repo.set_default(
        db, USER_ID, NewBudgetDefault(category_id=groceries.id, amount=BUDGET_MINOR)
    )
    transactions_repo.create(
        db,
        USER_ID,
        NewTransaction(
            operation_date=today,
            category_id=groceries.id,
            account_id=account.id,
            amount=SPENT_MINOR,
        ),
    )


def _money_num(client: TestClient, minor: int) -> str:
    env = cast(Any, client.app).state.jinja_env
    result: str = env.filters["money_num"](minor, CCY)
    return result


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_today_hero_shows_view_model_values(
    client: TestClient,
    db: sqlite3.Connection,
    _migrated: Settings,
    today: date,
    world: None,
) -> None:
    year, month = budget_service.fiscal_month_for(db, USER_ID, today)
    summary = budget_service.month_summary(
        db,
        USER_ID,
        year,
        month,
        today=today,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    view = view_models.budget_view(summary, today)
    expected_per_day = _money_num(client, view_models.left_per_day(summary))

    html = client.get("/today").text

    assert _html.text_of(html, today_ui.hero_per_day) == expected_per_day
    assert view.spent_pct == 25
    spent_bar = _html.resolve_one(html, today_ui.spent_bar)
    totals = summary.totals
    left_pct = view_models.clamped_percent(totals.remaining_minor, totals.budgeted_minor)
    assert spent_bar["aria-label"] == view_models.bar_aria_label(view.spent_pct, left_pct)
    assert f"DAY {view.period_day} OF {view.period_total_days}" in _html.page_text(html)


def test_plan_budget_tab_shows_view_model_values(
    client: TestClient,
    db: sqlite3.Connection,
    today: date,
    world: None,
) -> None:
    picked = budget_service.resolve_picker_month(db, USER_ID, today)
    summary = budget_service.month_summary_for_picker(
        db,
        USER_ID,
        picked,
        today,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    view = view_models.budget_view(summary, today)

    html = client.get("/plan?tab=budget").text

    hero = _html.text_of(html, plan_budget.hero)
    assert hero.startswith(f"budget left {_money_num(client, summary.totals.remaining_minor)} PLN")
    assert view.left_per_day_minor == view_models.left_per_day(summary)
    cells = _html.texts(html, plan_budget.row_cells("Groceries"))
    assert cells[2] == f"{_money_num(client, SPENT_MINOR)} / {_money_num(client, BUDGET_MINOR)}"
    assert cells[3] == f"left {_money_num(client, BUDGET_MINOR - SPENT_MINOR)}"
    bar = _html.resolve_one(html, plan_budget.bar("Groceries"))
    assert bar["aria-label"] == "25 percent spent, 75 percent left"


def test_budget_view_percent_clamps_and_flags_over() -> None:
    assert view_models.clamped_percent(150, 100) == 100
    assert view_models.clamped_percent(-5, 100) == 0
    assert view_models.clamped_percent(5, 0) == 0


def _plan_day(today: date) -> date:
    """Tomorrow, unless that is next month's day 1 (month-end clock): then today (ADR-0140)."""
    tomorrow = today + timedelta(days=1)
    return tomorrow if tomorrow.month == today.month else today


def _plan_hero_totals(
    client: TestClient, db: sqlite3.Connection, today: date
) -> tuple[budget_service.MonthTotals, str]:
    picked = budget_service.resolve_picker_month(db, USER_ID, today)
    summary = budget_service.month_summary_for_picker(
        db,
        USER_ID,
        picked,
        today,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    return summary.totals, _html.text_of(client.get("/plan?tab=budget").text, plan_budget.hero)


def _category_id(db: sqlite3.Connection, name: str) -> int:
    row = db.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
    return int(row["id"])


def test_plan_hero_prints_the_committed_amount_of_a_budgeted_category(
    client: TestClient, db: sqlite3.Connection, today: date, world: None
) -> None:
    """T-UR15a (Q13): a planned row in a budgeted category is committed, not unbudgeted."""
    planned_repo.create(
        db,
        USER_ID,
        NewPlannedTransaction(
            operation_date=_plan_day(today),
            category_id=_category_id(db, "Groceries"),
            account_id=_category_account(db),
            amount=4_000,
        ),
    )

    totals, hero = _plan_hero_totals(client, db, today)

    assert totals.committed_minor == 4_000
    assert totals.unbudgeted_committed_minor == 0
    assert f"{_money_num(client, totals.committed_minor)} committed" in hero
    assert "40.00 committed" in hero
    assert "planned in unbudgeted categories" not in hero


def test_plan_hero_unbudgeted_info_line_is_not_counted_as_committed(
    client: TestClient, db: sqlite3.Connection, today: date, world: None
) -> None:
    """T-UR15a (Q13), was test_budget_hero_unbudgeted_info_line_not_counted (ADR-0085)."""
    rent = categories_repo.create(
        db, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id
    planned_repo.create(
        db,
        USER_ID,
        NewPlannedTransaction(
            operation_date=_plan_day(today),
            category_id=rent,
            account_id=_category_account(db),
            amount=35_000,
        ),
    )

    totals, hero = _plan_hero_totals(client, db, today)

    assert (totals.committed_minor, totals.unbudgeted_committed_minor) == (0, 35_000)
    assert "350.00 planned in unbudgeted categories" in hero
    assert "0.00 committed" in hero
    assert f"{_money_num(client, totals.unbudgeted_committed_minor)} planned in unbudgeted" in hero


def _category_account(db: sqlite3.Connection) -> int:
    row = db.execute("SELECT id FROM accounts WHERE name = ?", ("Checking",)).fetchone()
    return int(row["id"])
