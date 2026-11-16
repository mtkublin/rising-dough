"""T-037 + T-127 forecast router."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.repositories import accounts as accounts_repo

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
    assert 'id="forecast-chart"' in r.text
    assert "rd-chart__svg" in r.text
    assert 'id="forecast-monthly-table"' in r.text


def test_horizon_param(client: TestClient, seeded: int) -> None:
    r = client.get("/forecast?horizon_months=6")
    assert r.status_code == 200
    assert "Horizon 6 months" in r.text


def test_horizon_bad_input_falls_back(client: TestClient, seeded: int) -> None:
    r = client.get("/forecast?horizon_months=notanumber")
    assert r.status_code == 200
    assert "Horizon 12 months" in r.text


def test_horizon_clamped(client: TestClient, seeded: int) -> None:
    r = client.get("/forecast?horizon_months=99999")
    assert r.status_code == 200
    assert "Horizon 60 months" in r.text


def test_horizon_min(client: TestClient, seeded: int) -> None:
    r = client.get("/forecast?horizon_months=0")
    assert r.status_code == 200
    assert "Horizon 1 month" in r.text


def test_view_fragment(client: TestClient, seeded: int) -> None:
    r = client.get("/forecast/view?horizon_months=3")
    assert r.status_code == 200
    assert "<html" not in r.text
    assert 'id="forecast-view"' in r.text
    assert 'id="forecast-chart"' in r.text
    assert 'id="forecast-monthly-table"' in r.text


def test_monthly_table_row_count(client: TestClient, seeded: int) -> None:
    r = client.get("/forecast/view?horizon_months=5")
    assert r.status_code == 200
    assert r.text.count('data-month="') == 5


def test_plotly_json_shape_monthly_granularity(client: TestClient, seeded: int) -> None:
    """T-R50 — chart is now server-rendered SVG with monthly ticks instead of a
    client-side Plotly JSON spec (ADR-0054)."""
    r = client.get("/forecast/view?horizon_months=4")
    assert "rd-chart__svg" in r.text
    # 4 months → 4 data-month entries in the monthly table fallback.
    assert r.text.count('data-month="') == 4


def test_planned_budget_column_present(client: TestClient, seeded: int) -> None:
    r = client.get("/forecast")
    assert r.status_code == 200
    assert ">Planned budget<" in r.text


def test_forecast_nav_link_present(client: TestClient, seeded: int) -> None:
    """Rising Dough v2 collapses Forecast under /plan?tab=forecast — the rail now
    exposes 'Plan' and the Forecast page is reachable via the Plan hub."""
    r = client.get("/forecast")
    assert r.status_code == 200
    assert 'href="/plan"' in r.text
    assert ">Plan<" in r.text
