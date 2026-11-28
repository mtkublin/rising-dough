"""Contract tests: plan read routes and redirects (T-UT04d, ADR-0106 section 1).

Status, redirect targets, content type, fragment-vs-page shape and auth only;
markup is read through the UI map.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.contract.conftest import covers
from tests.ui_map import _html, plan, plan_year

pytest_plugins = ("tests.contract.test_plan_support",)

READ_PATHS = (
    "/budget",
    "/budget/yearly?year=2026",
    "/forecast",
    "/forecast/view",
    "/plan",
)


@covers(
    "GET /budget",
    "GET /budget/yearly",
    "GET /forecast",
    "GET /forecast/view",
    "GET /plan",
)
@pytest.mark.parametrize("path", READ_PATHS)
def test_read_routes_redirect_anonymous_visitors_to_login(
    anon_client: TestClient, path: str
) -> None:
    r = anon_client.get(path, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login?next=")


# --- redirects (T-UR15a, operator decision Q13) -------------------------------

REDIRECTS = (
    ("GET /budget", "/budget", "/plan?tab=budget"),
    ("GET /budget", "/budget?year=2026&month=11", "/plan?tab=budget&year=2026&month=11"),
    ("GET /budget/yearly", "/budget/yearly?year=2026", "/plan?tab=year&year=2026"),
    ("GET /forecast", "/forecast", "/plan?tab=forecast"),
    ("GET /forecast", "/forecast?horizon_months=24", "/plan?tab=forecast&horizon=24"),
    ("GET /forecast", "/forecast?horizon_months=100000", "/plan?tab=forecast"),
    ("GET /forecast", "/forecast?horizon_months=abc", "/plan?tab=forecast"),
    ("GET /forecast", "/forecast?horizon_months=7", "/plan?tab=forecast"),
    ("GET /forecast/view", "/forecast/view?horizon_months=6", "/plan?tab=forecast&horizon=6"),
)


@covers("GET /budget", "GET /budget/yearly", "GET /forecast", "GET /forecast/view")
@pytest.mark.parametrize(("_route", "path", "location"), REDIRECTS)
def test_retired_pages_redirect_to_the_plan_hub(
    client: TestClient, _route: str, path: str, location: str
) -> None:
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == location


@covers("GET /budget")
def test_budget_redirect_lands_on_the_selected_month(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget?year=2026&month=11")
    assert r.status_code == 200
    assert str(r.url).endswith("/plan?tab=budget&year=2026&month=11")
    assert _html.exists(r.text, plan.heading)


@covers("GET /forecast")
def test_forecast_redirect_keeps_the_horizon(client: TestClient, account_id: int) -> None:
    r = client.get("/forecast?horizon_months=24")
    assert r.status_code == 200
    assert str(r.url).endswith("/plan?tab=forecast&horizon=24")


# --- GET /plan, GET /plan/analytics --------------------------------------------


@covers("GET /plan")
@pytest.mark.parametrize("tab", ["budget", "year", "forecast", "analytics", ""])
def test_plan_hub_renders_every_tab(client: TestClient, cat_id: int, tab: str) -> None:
    r = client.get(f"/plan?tab={tab}")
    assert r.status_code == 200
    assert _html.exists(r.text, plan.heading)


@covers("GET /plan")
def test_plan_year_tab_exposes_year_cells(client: TestClient, cat_id: int) -> None:
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "10"})
    r = client.get("/plan?tab=year&year=2026")
    assert r.status_code == 200
    assert _html.exists(r.text, plan_year.cell("Groceries", "January"))
    assert _html.exists(r.text, plan_year.row("Groceries"))
