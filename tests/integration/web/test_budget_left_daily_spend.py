"""T-101 integration tests for the left-daily-spend card + anchor selector."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.periods import next_month_start
from budget_planner.domain.preferences import PREF_INCOME_ANCHOR_CATEGORY_ID
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    planned as planned_repo,
    preferences as preferences_repo,
)
from budget_planner.web.view_models import day_month
from tests.ui_map import _html, plan, today
from tests.ui_map.locator import by_id

USER_ID = 1


@pytest.fixture
def world(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        checking = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Checking", currency="PLN")
        ).id
        groceries = categories_repo.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        ).id
        salary = categories_repo.create(
            conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
        ).id
        budgets_repo.set_default(
            conn, USER_ID, NewBudgetDefault(category_id=groceries, amount=100_000)
        )
        return {
            "checking": checking,
            "groceries": groceries,
            "salary": salary,
        }
    finally:
        conn.close()


def _seed_anchor_and_income(
    settings: Settings, salary: int, checking: int, income_date: date
) -> None:
    conn = get_connection(settings)
    try:
        preferences_repo.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, str(salary))
        planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=income_date,
                category_id=salary,
                account_id=checking,
                amount=500_000,
            ),
        )
    finally:
        conn.close()


def _end_of_month_caption(settings: Settings) -> str:
    """The fallback caption for the frozen clock: days to the 1st of next month, as ``d mon``."""
    today_ = clock.today_local(settings)
    first_next = next_month_start(today_.year, today_.month)
    days = max((first_next - today_).days, 1)
    noun = "day" if days == 1 else "days"
    return f"{days} {noun} until next income ({day_month(first_next)})"


def _hero(html: str) -> str:
    return _html.text_of(html, by_id("today-hero"))


def test_left_daily_spend_card_renders_number_and_caption(
    client: TestClient, _migrated: Settings, world: dict[str, int]
) -> None:
    # Within horizon_days=400 so the anchor name resolves on the hero caption; relative to
    # the frozen clock so the test holds on any date (ADR-0140).
    income_date = clock.today_local(_migrated) + timedelta(days=30)
    _seed_anchor_and_income(_migrated, world["salary"], world["checking"], income_date)
    r = client.get("/today")
    assert r.status_code == 200
    assert _html.exists(r.text, today.heading)
    hero = _hero(r.text)
    assert "Salary" in hero
    assert "until next income (Salary," in hero


def test_left_daily_spend_card_renders_dash_when_zero_budget(
    client: TestClient, _migrated: Settings
) -> None:
    conn = get_connection(_migrated)
    try:
        categories_repo.create(conn, USER_ID, NewCategory(name="Any", direction=Direction.EXPENSE))
    finally:
        conn.close()
    assert _html.text_of(client.get("/today").text, today.hero_per_day) == "0.00"


def test_left_daily_spend_card_shows_end_of_month_fallback_when_anchor_unset(
    client: TestClient, _migrated: Settings, world: dict[str, int]
) -> None:
    assert _end_of_month_caption(_migrated) in _hero(client.get("/today").text)


def test_settings_prefs_lists_income_categories_in_select(
    client: TestClient, world: dict[str, int]
) -> None:
    """Manual-audit #54 — income anchor lives on Settings · Categories now."""
    r = client.get("/settings?tab=categories")
    assert r.status_code == 200
    options = _html.resolve(r.text, plan.option_in(plan.anchor_select))
    assert "Salary" in [o.get_text(strip=True) for o in options]


def test_stale_anchor_renders_fallback_without_500(
    client: TestClient, _migrated: Settings, world: dict[str, int]
) -> None:
    # Set anchor, then soft-delete the category — resolve must fall back.
    conn = get_connection(_migrated)
    try:
        preferences_repo.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, str(world["salary"]))
        categories_repo.soft_delete(conn, USER_ID, world["salary"])
    finally:
        conn.close()
    r = client.get("/today")
    assert r.status_code == 200
    assert _end_of_month_caption(_migrated) in _hero(r.text)
