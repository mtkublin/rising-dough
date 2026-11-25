"""T-Q229 / ADR-0140: at Warsaw midnight on a UTC host every page agrees on one "today"."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from budget_planner import clock
from tests.ui_map import _html, plan_budget

# 22:30 UTC on 30 June is 00:30 on 1 July in Europe/Warsaw.
WARSAW_MIDNIGHT = datetime(2026, 6, 30, 22, 30, tzinfo=UTC)


def test_budget_defaults_to_the_display_zone_month(client: TestClient) -> None:
    with clock.frozen(WARSAW_MIDNIGHT):
        response = client.get("/budget")

    assert response.status_code == 200
    assert "July 2026" in _html.text_of(response.text, plan_budget.period_trigger)


def test_today_page_and_budget_page_share_the_display_zone_day(client: TestClient) -> None:
    with clock.frozen(WARSAW_MIDNIGHT):
        today_page = client.get("/today")
        budget_page = client.get("/budget")

    assert today_page.status_code == 200
    assert "July 2026" in _html.text_of(budget_page.text, plan_budget.period_trigger)
