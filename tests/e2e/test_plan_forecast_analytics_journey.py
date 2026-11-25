"""Plan · forecast and analytics tabs on either target (T-UR12; ADR-0106, ADR-0107).

``--target=mockup`` runs the journeys against ``pages/plan/forecast.html`` and
``pages/plan/analytics.html``; the default target runs them against ``/plan?tab=forecast`` and
``/plan?tab=analytics`` seeded with one account. The structure is asserted on both; horizon and
range switching reload ``#main`` on the app only (the handoff buttons are static).
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from tests.e2e.mockup_target import Journey
from tests.ui_map import plan_analytics, plan_budget, plan_forecast, rd_fragments
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e


def _find(journey: Journey, locator: Any) -> Any:
    return to_playwright(journey.page, locator)


def _seed_app(journey: Journey) -> None:
    """One PLN account so the projection has a starting balance (app target only)."""
    if journey.target != "app":
        return
    created = journey.page.request.post(
        f"{journey.base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "5000.00"},
    )
    assert created.ok


def _open(journey: Journey, path: str) -> None:
    _seed_app(journey)
    journey.goto(path)


def test_forecast_shows_hero_chart_table_and_the_horizon(journey: Journey) -> None:
    _open(journey, "/plan?tab=forecast")

    expect(_find(journey, plan_forecast.heading)).to_contain_text("projected balance")
    expect(_find(journey, plan_budget.tab("forecast"))).to_have_attribute("aria-current", "page")
    expect(_find(journey, plan_forecast.chart)).to_be_visible()
    expect(_find(journey, plan_forecast.table)).to_be_visible()
    expect(_find(journey, plan_forecast.planned_header)).to_be_visible()
    expect(_find(journey, plan_forecast.horizon_selected)).to_have_text("12")
    expect(_find(journey, plan_forecast.chart_points)).to_have_count(12)
    expect(_find(journey, plan_forecast.rows)).to_have_count(12 + 1)  # header row


def test_forecast_point_names_its_month_and_balance(journey: Journey) -> None:
    _open(journey, "/plan?tab=forecast")

    first = _find(journey, plan_forecast.chart_points).first
    expect(first).to_have_attribute("aria-label", re.compile(r"^\w{3} \d{4}: .*PLN, net "))


def test_horizon_buttons_reload_the_page_for_another_horizon(journey: Journey) -> None:
    if journey.target != "app":
        pytest.skip("the handoff horizon buttons are static")
    _open(journey, "/plan?tab=forecast")

    _find(journey, plan_forecast.horizon_button(24)).click()

    expect(_find(journey, plan_forecast.horizon_selected)).to_have_text("24")
    expect(_find(journey, plan_forecast.chart_points)).to_have_count(24)
    expect(_find(journey, plan_forecast.rows)).to_have_count(24 + 1)
    expect(journey.page).to_have_url(re.compile(r"tab=forecast&horizon=24"))


def test_analytics_shows_hero_spend_table_flow_chart_and_largest_items(journey: Journey) -> None:
    _open(journey, "/plan?tab=analytics")

    expect(_find(journey, plan_analytics.heading)).to_have_text("where it went")
    expect(_find(journey, plan_budget.tab("analytics"))).to_have_attribute("aria-current", "page")
    expect(_find(journey, rd_fragments.period_nav)).to_be_visible()
    expect(_find(journey, plan_analytics.range_selected)).to_have_text("month")
    expect(_find(journey, plan_analytics.spend_section)).to_be_visible()
    expect(_find(journey, plan_analytics.flow_section)).to_be_visible()
    expect(_find(journey, plan_analytics.largest_section)).to_be_visible()


def test_analytics_range_buttons_reload_the_page_for_another_range(journey: Journey) -> None:
    if journey.target != "app":
        pytest.skip("the handoff range buttons are static")
    _open(journey, "/plan?tab=analytics")

    _find(journey, plan_analytics.range_button("12 months")).click()

    expect(_find(journey, plan_analytics.range_selected)).to_have_text("12 months")
    expect(journey.page).to_have_url(re.compile(r"tab=analytics&period=trailing-12"))


def test_back_keeps_the_pressed_horizon_in_step_with_the_url(journey: Journey) -> None:
    if journey.target != "app":
        pytest.skip("the handoff horizon buttons are static")
    _open(journey, "/plan?tab=forecast")

    for months in (6, 12, 24):
        _find(journey, plan_forecast.horizon_button(months)).click()
        expect(journey.page).to_have_url(re.compile(rf"horizon={months}$"))
        expect(_find(journey, plan_forecast.chart_points)).to_have_count(months)
    journey.page.go_back()

    expect(journey.page).to_have_url(re.compile(r"horizon=12"))
    expect(_find(journey, plan_forecast.horizon_selected)).to_have_text("12")
    expect(_find(journey, plan_forecast.chart_points)).to_have_count(12)


def test_back_keeps_the_pressed_range_in_step_with_the_url(journey: Journey) -> None:
    if journey.target != "app":
        pytest.skip("the handoff range buttons are static")
    _open(journey, "/plan?tab=analytics")

    for name in ("year to date", "12 months"):
        _find(journey, plan_analytics.range_button(name)).click()
        expect(journey.page).to_have_url(
            re.compile(r"period=" + ("year&" if name[0] == "y" else "trailing-12&"))
        )
    journey.page.go_back()

    expect(journey.page).to_have_url(re.compile(r"period=year&"))
    expect(_find(journey, plan_analytics.range_selected)).to_have_text("year to date")
