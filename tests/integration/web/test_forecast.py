"""T-037 + T-127 forecast router."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.repositories import accounts as accounts_repo
from tests.ui_map import _html, plan

USER_ID = 1


@pytest.fixture
def seeded(_migrated: Settings) -> int:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=100000)
        )
        return acc.id
    finally:
        conn.close()


def test_index(client: TestClient, seeded: int) -> None:
    """T-R50 — Plotly replaced by server-rendered SVG (ADR-0054)."""
    r = client.get("/forecast")
    assert r.status_code == 200
    assert _html.exists(r.text, plan.forecast_chart)
    assert _html.exists(r.text, plan.forecast_table)


def test_monthly_table_row_count(client: TestClient, seeded: int) -> None:
    r = client.get("/forecast/view?horizon_months=5")
    assert _html.count(r.text, plan.forecast_rows) == 5 + 1  # header row


def test_planned_budget_column_present(client: TestClient, seeded: int) -> None:
    r = client.get("/forecast")
    assert _html.exists(r.text, plan.forecast_planned_header)


def test_forecast_nav_link_present(client: TestClient, seeded: int) -> None:
    """Rising Dough v2 collapses Forecast under /plan?tab=forecast — the rail
    exposes 'Plan' and the Forecast page is reachable via the Plan hub."""
    r = client.get("/forecast")
    links = _html.resolve(r.text, plan.plan_nav_link)
    assert any(link.get("href") == "/plan" for link in links)
