"""GET /plan?tab=budget renders the Rising Dough budget page with exact values (T-UR11, ADR-0107).

Values come from the service (``MonthTotals``, ``CategoryBudgetLine``) through the view model;
the template prints them, so a changed figure here means a changed service value.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import categories as categories_repo
from tests.ui_map import _html, plan_budget, rd_fragments

pytest_plugins = ("tests.contract.test_plan_support",)

URL = "/plan?tab=budget&year=2026&month=10"
USER_ID = 1


def _post(client: TestClient, path: str, form: dict[str, str]) -> None:
    assert client.post(path, data=form).status_code < 400, path


@pytest.fixture
def page(client: TestClient, db: sqlite3.Connection, account_id: int, cat_id: int) -> str:
    """Groceries 500.00 budget with 120.00 spent; Car 100.00 budget with 150.00 spent."""
    car = categories_repo.create(db, USER_ID, NewCategory(name="Car", direction=Direction.EXPENSE))
    for category, budget, spent in ((cat_id, "500", "120"), (car.id, "100", "150")):
        _post(client, f"/budget/defaults/{category}", {"amount": budget})
        _post(
            client,
            "/transactions",
            {
                "operation_date": "2026-10-15",
                "category_id": str(category),
                "account_id": str(account_id),
                "amount": spent,
                "description": "spend",
            },
        )
    return client.get(URL).text


def _cells(page: str, name: str) -> list[str]:
    return _html.texts(page, plan_budget.row_cells(name))


def test_hero_prints_the_remaining_budget(page: str) -> None:
    text = _html.text_of(page, plan_budget.hero)
    assert text.startswith("budget left 330.00 PLN")
    assert "600.00 budgeted · 270.00 spent" in text
    assert "1 category over" in text
    assert _html.text_of(page, plan_budget.heading) == "budget left"


def test_rows_show_spent_budget_and_status(page: str) -> None:
    assert _cells(page, "Groceries")[2:4] == ["120.00 / 500.00", "left 380.00"]
    assert _cells(page, "Car")[2:4] == ["150.00 / 100.00", "▲ over 50.00"]


def test_bars_carry_the_percentages(page: str) -> None:
    groceries = _html.resolve_one(page, plan_budget.bar("Groceries"))
    assert groceries["aria-label"] == "24 percent spent, 76 percent left"
    assert _html.resolve_one(page, plan_budget.bar("Car")).get("aria-label") == "over budget"


def test_total_row_sums_the_month(page: str) -> None:
    cells = _html.texts(page, plan_budget.total_row)
    assert cells[0] == "Total 270.00 / 600.00 left 330.00"


def test_period_nav_steps_the_month_and_names_the_range(page: str) -> None:
    assert _html.resolve_one(page, rd_fragments.period_prev)["href"] == (
        "/plan?tab=budget&year=2026&month=9"
    )
    assert _html.resolve_one(page, rd_fragments.period_next)["href"] == (
        "/plan?tab=budget&year=2026&month=11"
    )
    assert "October 2026" in _html.text_of(page, plan_budget.period_trigger)
    assert _html.count(page, rd_fragments.period_cell("Dec")) == 1
    assert _html.resolve_one(page, rd_fragments.period_prev_year)["href"] == (
        "/plan?tab=budget&year=2025&month=10"
    )


def test_tabs_link_the_other_plan_views(page: str) -> None:
    hrefs = {t: _html.resolve_one(page, plan_budget.tab(t))["href"] for t in ("year", "forecast")}
    assert hrefs == {"year": "/plan?tab=year", "forecast": "/plan?tab=forecast"}
    assert _html.resolve_one(page, plan_budget.tab("budget")).get("aria-current") == "page"


def test_override_item_links_to_the_override_form(page: str, cat_id: int) -> None:
    link = _html.resolve_one(page, plan_budget.override_item("Groceries"))
    assert link["href"] == f"/budget/rules/{cat_id}/overrides/new?year=2026&month=10"


def test_period_note_names_the_income_to_income_range() -> None:
    from datetime import date  # noqa: PLC0415 - local to the one test

    from budget_planner.web.view_models import period_note  # noqa: PLC0415

    assert period_note(10, date(2026, 10, 7), date(2026, 11, 7)) == "oct = 7 oct → 7 nov"
