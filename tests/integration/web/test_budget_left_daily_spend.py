"""T-101 integration tests for the left-daily-spend card + anchor selector."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.preferences import PREF_INCOME_ANCHOR_CATEGORY_ID
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    planned as planned_repo,
    preferences as preferences_repo,
)
from tests.ui_map import _html, plan

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


def _hero(html: str) -> str:
    return _html.text_of(html, plan.budget_hero)


def test_left_daily_spend_card_renders_number_and_caption(
    client: TestClient, _migrated: Settings, world: dict[str, int]
) -> None:
    # Within horizon_days=400 so the anchor name resolves on the hero caption.
    _seed_anchor_and_income(_migrated, world["salary"], world["checking"], date(2027, 1, 15))
    r = client.get("/budget")
    assert r.status_code == 200
    assert _html.exists(r.text, plan.budget_hero_heading)
    hero = _hero(r.text)
    assert "Salary" in hero
    assert "next income" in hero


def test_left_daily_spend_card_renders_dash_when_zero_budget(
    client: TestClient, _migrated: Settings
) -> None:
    conn = get_connection(_migrated)
    try:
        categories_repo.create(conn, USER_ID, NewCategory(name="Any", direction=Direction.EXPENSE))
    finally:
        conn.close()
    assert "No budgets set" in _hero(client.get("/budget").text)


def test_left_daily_spend_card_shows_end_of_month_fallback_when_anchor_unset(
    client: TestClient, world: dict[str, int]
) -> None:
    assert "end of month" in _hero(client.get("/budget").text)


def test_settings_prefs_lists_income_categories_in_select(
    client: TestClient, world: dict[str, int]
) -> None:
    """Manual-audit #54 — income anchor lives on Settings · Categories now."""
    r = client.get("/settings?tab=categories")
    assert r.status_code == 200
    options = _html.resolve(r.text, plan.option_in(plan.anchor_select))
    assert "Salary" in [o.get_text(strip=True) for o in options]


def test_budget_page_links_to_settings_anchor(client: TestClient, world: dict[str, int]) -> None:
    """ADR-0031 §1 — the hero caption carries a `Change anchor →` link."""
    r = client.get("/budget")
    link = _html.resolve_one(r.text, plan.change_anchor_link)
    assert link.get("href") == "/settings?tab=prefs#income-anchor"


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
    r = client.get("/budget")
    assert r.status_code == 200
    assert "end of month" in _hero(r.text)
