"""Contract tests: plan read routes and redirects (T-UT04d, ADR-0106 section 1).

Status, redirect targets, content type, fragment-vs-page shape and auth only;
markup is read through the UI map.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.contract.conftest import covers
from tests.ui_map import _html, plan

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


# --- redirects ----------------------------------------------------------------


# --- GET /budget ---------------------------------------------------------------


@covers("GET /budget")
def test_budget_page_renders_sections_in_order(client: TestClient, cat_id: int) -> None:
    r = client.get("/budget?year=2026&month=10")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    ids = [
        s.get("id")
        for s in _html.resolve(r.text, plan.budget_hero)
        + _html.resolve(r.text, plan.budget_summary)
        + _html.resolve(r.text, plan.budget_rules)
        + _html.resolve(r.text, plan.yearly_section)
        + _html.resolve(r.text, plan.budget_breakdown)
    ]
    assert ids == [
        "left-daily-spend",
        "budget-summary",
        "budget-rules",
        "budget-yearly",
        "budget-breakdown",
    ]


@covers("GET /budget")
def test_budget_page_query_selects_the_month(client: TestClient) -> None:
    r = client.get("/budget?year=2026&month=11")
    assert r.status_code == 200
    assert _html.resolve_one(r.text, plan.budget_year_input).get("value") == "2026"
    selected = [
        o.get("value")
        for o in _html.resolve(r.text, plan.option_in(plan.budget_month_select))
        if o.has_attr("selected")
    ]
    assert selected == ["11"]


# --- GET /budget/yearly --------------------------------------------------------


@covers("GET /budget/yearly")
def test_yearly_fragment_is_a_fragment_for_the_requested_year(
    client: TestClient, cat_id: int
) -> None:
    r = client.get("/budget/yearly?year=2026")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert _html.exists(r.text, plan.yearly_section)
    assert _html.resolve_one(r.text, plan.yearly_year_input).get("value") == "2026"
    assert _html.exists(r.text, plan.yearly_input(cat_id, 7))
    assert not _html.exists(r.text, plan.heading)  # no page chrome


# --- GET /forecast, GET /forecast/view -----------------------------------------


@covers("GET /forecast")
def test_forecast_page_renders_chart_and_table(client: TestClient, account_id: int) -> None:
    r = client.get("/forecast")
    assert r.status_code == 200
    assert _html.exists(r.text, plan.forecast_heading)
    assert _html.exists(r.text, plan.forecast_chart)
    assert _html.exists(r.text, plan.forecast_table)
    assert _html.exists(r.text, plan.forecast_planned_header)
    horizon = _html.resolve_one(r.text, plan.forecast_horizon)
    assert horizon.get("value") == "12"


@covers("GET /forecast")
@pytest.mark.parametrize(
    ("query", "expected"),
    [("6", "6"), ("99999", "60"), ("0", "1")],
)
def test_forecast_horizon_is_parsed_and_clamped(
    client: TestClient, account_id: int, query: str, expected: str
) -> None:
    r = client.get(f"/forecast?horizon_months={query}")
    assert r.status_code == 200
    assert _html.resolve_one(r.text, plan.forecast_horizon).get("value") == expected


@covers("GET /forecast/view")
def test_forecast_view_is_a_fragment_with_one_row_per_month(
    client: TestClient, account_id: int
) -> None:
    r = client.get("/forecast/view?horizon_months=5")
    assert r.status_code == 200
    assert _html.exists(r.text, plan.forecast_view)
    assert _html.exists(r.text, plan.forecast_chart)
    assert _html.count(r.text, plan.forecast_rows) == 5 + 1  # header row
    assert not _html.exists(r.text, plan.forecast_heading)  # no page chrome


# --- GET /plan, GET /plan/analytics --------------------------------------------


@covers("GET /plan")
@pytest.mark.parametrize("tab", ["budget", "year", "forecast", "analytics", "bogus"])
def test_plan_hub_renders_every_tab(client: TestClient, cat_id: int, tab: str) -> None:
    r = client.get(f"/plan?tab={tab}")
    assert r.status_code == 200
    assert _html.exists(r.text, plan.heading)


@covers("GET /plan")
def test_plan_year_tab_exposes_year_cells(client: TestClient, cat_id: int) -> None:
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "10"})
    r = client.get("/plan?tab=year&year=2026")
    assert r.status_code == 200
    assert _html.exists(r.text, plan.year_cell(cat_id, 1))
    assert _html.exists(r.text, plan.year_card(cat_id))
