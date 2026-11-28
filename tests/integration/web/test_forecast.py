"""T-037 + T-127 forecast router."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.repositories import accounts as accounts_repo
from tests.ui_map import _html, plan_forecast

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


def test_forecast_lands_on_the_plan_forecast_tab(client: TestClient, seeded: int) -> None:
    """T-UR15a: the old page is a redirect; the chart and table are the Plan hub's."""
    r = client.get("/forecast")
    assert r.status_code == 200
    assert _html.document_title(r.text) == "Plan · forecast · Rising Dough"
    assert _html.exists(r.text, plan_forecast.chart)
    assert _html.text_of(r.text, plan_forecast.horizon_selected) == "12"


def test_forecast_view_redirect_keeps_the_horizon(client: TestClient, seeded: int) -> None:
    r = client.get("/forecast/view?horizon_months=6")
    assert len(_html.resolve(r.text, plan_forecast.rows)[1:]) == 6  # minus the header row
    assert _html.text_of(r.text, plan_forecast.horizon_selected) == "6"
