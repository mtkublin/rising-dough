"""GET /plan?tab=analytics on the Rising Dough markup, with exact values (T-UR12, ADR-0107).

World (all PLN): October 2026 spends Groceries 120.00 + 80.00 and Car 50.00 and earns Salary
1,000.00; September earns 900.00 and spends Groceries 100.00. The 12-month average divides the
trailing-12 sum by 12: Groceries (200 + 100) / 12 = 25.00, Car 50 / 12 = 4.17 (half even).
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from tests.auth_support import seed_login_user
from tests.ui_map import _html, plan_analytics, plan_budget, rd_fragments

pytest_plugins = ("tests.contract.test_plan_support",)

URL = "/plan?tab=analytics&year=2026&month=10"
USER_ID = 1
MINUS = "\N{MINUS SIGN}"


def _spend(client: TestClient, account_id: int, category_id: int, day: str, amount: str) -> None:
    r = client.post(
        "/transactions",
        data={
            "operation_date": day,
            "category_id": str(category_id),
            "account_id": str(account_id),
            "amount": amount,
            "description": "t",
        },
    )
    assert r.status_code < 400, r.text


@pytest.fixture
def world(
    client: TestClient, db: sqlite3.Connection, account_id: int, cat_id: int, income_cat_id: int
) -> int:
    """Seed the module's world; returns the Car category id (``cat_id`` is Groceries)."""
    car = categories_repo.create(db, USER_ID, NewCategory(name="Car", direction=Direction.EXPENSE))
    for category, day, amount in (
        (cat_id, "2026-10-05", "120"),
        (cat_id, "2026-10-20", "80"),
        (car.id, "2026-10-12", "50"),
        (income_cat_id, "2026-10-01", "1000"),
        (cat_id, "2026-09-15", "100"),
        (income_cat_id, "2026-09-01", "900"),
    ):
        _spend(client, account_id, category, day, amount)
    return car.id


@pytest.fixture
def page(client: TestClient, world: int) -> str:
    return client.get(URL).text


def test_hero_prints_the_period_spend(page: str) -> None:
    assert _html.text_of(page, plan_analytics.heading) == "where it went"
    assert _html.text_of(page, plan_analytics.hero) == "where it went 250.00 PLN spent"


def test_spend_rows_show_amount_share_and_delta(page: str, cat_id: int, world: int) -> None:
    assert _html.texts(page, plan_analytics.spend_cells("Groceries")) == [
        "Groceries",
        "████████████████ ░░░░",
        "200.00",
        "▲ +175.00",
    ]
    assert _html.texts(page, plan_analytics.spend_cells("Car")) == [
        "Car",
        "████ ░░░░░░░░░░░░░░░░",
        "50.00",
        "▲ +45.83",
    ]
    assert _html.resolve_one(page, plan_analytics.share_bar("Groceries")).get_text() == (
        "█" * 16 + "░" * 4
    )
    assert _html.resolve_one(page, plan_analytics.share_bar("Groceries"))["aria-label"] == (
        "80 percent of spend"
    )
    assert _html.resolve_one(page, plan_analytics.share_bar("Car"))["aria-label"] == (
        "20 percent of spend"
    )
    link = _html.resolve_one(page, plan_analytics.spend_link("Groceries"))
    assert link["aria-label"] == "Groceries: 200.00 PLN, open in ledger"
    assert link["href"] == (
        f"/ledger?view=actual&category_id={cat_id}&date_from=2026-10-01&date_to=2026-10-31"
    )


def test_spend_rows_are_sorted_by_amount(page: str) -> None:
    names = [r.get_text(" ", strip=True) for r in _html.resolve(page, plan_analytics.spend_rows)]
    assert [n.split(" ")[0] for n in names[1:]] == ["Groceries", "Car"]


def test_flow_chart_has_a_month_per_active_month(page: str) -> None:
    months = [el["aria-label"] for el in _html.resolve(page, plan_analytics.flow_months)]
    assert months == [
        "Sep 2026: income 900.00 PLN, expense 100.00 PLN",
        "Oct 2026: income 1,000.00 PLN, expense 250.00 PLN",
    ]
    chart = _html.resolve_one(page, plan_analytics.flow_chart)
    assert chart["aria-label"] == (
        "Monthly income and expense, Sep to Oct 2026. Hover a month for exact totals."
    )


def test_largest_items_list_the_biggest_expenses(page: str) -> None:
    items = _html.texts(page, plan_analytics.largest_items)
    assert items == [
        f"Groceries · 5 Oct {MINUS}120.00 PLN",
        f"Groceries · 20 Oct {MINUS}80.00 PLN",
        f"Car · 12 Oct {MINUS}50.00 PLN",
    ]


def test_range_buttons_select_the_range_and_keep_the_month(page: str) -> None:
    assert _html.text_of(page, plan_analytics.range_selected) == "month"
    urls = {
        b.get_text(strip=True): b["hx-get"]
        for b in _html.resolve(page, plan_analytics.range_buttons)
    }
    assert urls == {
        "month": "/plan?tab=analytics&period=month&year=2026&month=10",
        "year to date": "/plan?tab=analytics&period=year&year=2026&month=10",
        "12 months": "/plan?tab=analytics&period=trailing-12&year=2026&month=10",
    }


def test_year_range_sums_the_calendar_year(client: TestClient, world: int) -> None:
    page = client.get(f"{URL}&period=year").text

    assert _html.text_of(page, plan_analytics.range_selected) == "year to date"
    assert _html.text_of(page, plan_analytics.hero) == "where it went 350.00 PLN spent"
    assert _html.texts(page, plan_analytics.spend_cells("Groceries"))[2:] == ["300.00", "▲ +275.00"]


def test_period_nav_steps_the_month_and_keeps_the_range(page: str) -> None:
    assert _html.resolve_one(page, rd_fragments.period_prev)["href"] == (
        "/plan?tab=analytics&period=month&year=2026&month=9"
    )
    assert _html.resolve_one(page, rd_fragments.period_next)["href"] == (
        "/plan?tab=analytics&period=month&year=2026&month=11"
    )
    assert "October 2026" in _html.text_of(page, plan_budget.period_trigger)
    assert "oct = 1 oct → 31 oct" in _html.text_of(page, rd_fragments.period_picker)
    assert _html.resolve_one(page, plan_budget.tab("analytics")).get("aria-current") == "page"


def test_second_users_spend_is_absent(
    client: TestClient, db: sqlite3.Connection, world: int
) -> None:
    other = seed_login_user(db, user_id=2, email="mallory@example.test")
    account = accounts_repo.create(
        db, other, NewAccount(name="Theirs", currency="PLN", opening_balance=0)
    )
    secret = categories_repo.create(
        db, other, NewCategory(name="Secret", direction=Direction.EXPENSE)
    )
    transactions_repo.create(
        db,
        other,
        NewTransaction(
            operation_date=date(2026, 10, 9),
            category_id=secret.id,
            account_id=account.id,
            amount=999_99,
        ),
    )

    page = client.get(URL).text

    assert _html.count(page, plan_analytics.spend_row("Secret")) == 0
    assert _html.text_of(page, plan_analytics.hero) == "where it went 250.00 PLN spent"


def test_empty_world_says_so(client: TestClient) -> None:
    page = client.get(URL).text

    assert _html.text_of(page, plan_analytics.hero) == "where it went 0.00 PLN spent"
    assert _html.count(page, plan_analytics.spend_table) == 0
    assert "No expense activity in this period." in _html.all_text(
        page, plan_analytics.spend_section
    )
