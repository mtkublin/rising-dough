"""Every ``plan_forecast`` / ``plan_analytics`` name resolves in the handoff (T-UR12, ADR-0106)."""

from __future__ import annotations

import pytest

from tests.ui_map import _html, plan_analytics, plan_budget, plan_forecast
from tests.ui_map.locator import Locator
from tests.ui_map.mockup_routes import HANDOFF_ROOT, handoff_page

FORECAST = (HANDOFF_ROOT / "pages" / "plan" / "forecast.html").read_text(encoding="utf-8")
ANALYTICS = (HANDOFF_ROOT / "pages" / "plan" / "analytics.html").read_text(encoding="utf-8")

_FORECAST: dict[str, Locator] = {
    "hero": plan_forecast.hero,
    "heading": plan_forecast.heading,
    "panel": plan_forecast.panel,
    "horizon_group": plan_forecast.horizon_group,
    "horizon_buttons": plan_forecast.horizon_buttons,
    "horizon_selected": plan_forecast.horizon_selected,
    "horizon_button": plan_forecast.horizon_button(24),
    "chart": plan_forecast.chart,
    "chart_points": plan_forecast.chart_points,
    "table_section": plan_forecast.table_section,
    "table": plan_forecast.table,
    "rows": plan_forecast.rows,
    "column_headers": plan_forecast.column_headers,
    "planned_header": plan_forecast.planned_header,
    "row": plan_forecast.row("Oct 2026"),
    "row_cells": plan_forecast.row_cells("Oct 2026"),
    "tab": plan_budget.tab("analytics"),
}
_ANALYTICS: dict[str, Locator] = {
    "hero": plan_analytics.hero,
    "heading": plan_analytics.heading,
    "panel": plan_analytics.panel,
    "range_group": plan_analytics.range_group,
    "range_buttons": plan_analytics.range_buttons,
    "range_selected": plan_analytics.range_selected,
    "range_button": plan_analytics.range_button("12 months"),
    "spend_section": plan_analytics.spend_section,
    "spend_table": plan_analytics.spend_table,
    "spend_rows": plan_analytics.spend_rows,
    "spend_headers": plan_analytics.spend_headers,
    "spend_row": plan_analytics.spend_row("Taxes"),
    "spend_cells": plan_analytics.spend_cells("Taxes"),
    "spend_link": plan_analytics.spend_link("Taxes"),
    "share_bar": plan_analytics.share_bar("Taxes"),
    "flow_section": plan_analytics.flow_section,
    "flow_chart": plan_analytics.flow_chart,
    "flow_months": plan_analytics.flow_months,
    "largest_section": plan_analytics.largest_section,
    "largest_items": plan_analytics.largest_items,
}


@pytest.mark.parametrize("name", sorted(_FORECAST))
def test_forecast_name_resolves_in_handoff(name: str) -> None:
    assert _html.count(FORECAST, _FORECAST[name]) >= 1, name


@pytest.mark.parametrize("name", sorted(_ANALYTICS))
def test_analytics_name_resolves_in_handoff(name: str) -> None:
    assert _html.count(ANALYTICS, _ANALYTICS[name]) >= 1, name


def test_handoff_forecast_has_one_point_and_row_per_month() -> None:
    assert _html.count(FORECAST, plan_forecast.chart_points) == 12
    assert _html.count(FORECAST, plan_forecast.rows) == 12 + 1  # header row
    assert _html.text_of(FORECAST, plan_forecast.horizon_selected) == "12"


def test_handoff_analytics_has_a_row_per_spending_category_and_four_months() -> None:
    assert _html.count(ANALYTICS, plan_analytics.spend_rows) == 14 + 1  # header row
    assert _html.count(ANALYTICS, plan_analytics.flow_months) == 4
    assert _html.count(ANALYTICS, plan_analytics.largest_items) == 3
    assert _html.text_of(ANALYTICS, plan_analytics.range_selected) == "month"


def test_plan_routes_map_to_the_forecast_and_analytics_pages() -> None:
    assert handoff_page("/plan?tab=forecast") == "pages/plan/forecast.html"
    assert handoff_page("/plan?tab=analytics") == "pages/plan/analytics.html"
