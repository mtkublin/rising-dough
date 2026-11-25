"""Plan surface: budget, year grid, forecast, analytics."""

from __future__ import annotations

import re

from tests.ui_map.locator import Locator, by_id, by_testid, label, role

heading = role("heading", level=1)
override = role("button", "Override")
forecast_heading = role("heading", "Projected balance", level=1)


# --- /budget (legacy full page: hero, summary, rules, yearly) ---
budget_hero = by_id("left-daily-spend")
budget_hero_heading = role("heading", "Left to spend per day").inside(budget_hero)
change_anchor_link = role("link", "Change anchor").inside(budget_hero)
budget_summary = by_id("budget-summary")
budget_rules = by_id("budget-rules")
budget_breakdown = by_id("budget-breakdown")
breakdown_link = role("link", "Plan").inside(budget_breakdown)
budget_year_input = by_id("budget-year")
budget_month_select = by_id("budget-month")
summary_table = role("table").inside(budget_summary)
summary_headers = role("columnheader").inside(summary_table)
summary_totals_row = role("row", re.compile(r"^Total\b")).inside(summary_table)
yearly_section = by_id("budget-yearly")
yearly_year_input = by_id("yearly-year")

# --- override form (inline fragment on /plan, slide-over on /budget) ---
override_tier = role("radio")
override_amount = role("textbox")
override_save = role("button", "Save")
override_cancel = role("button", "Cancel")

# --- /forecast (legacy page, contract-pinned until T-UR15; the tab is plan_forecast) ---
forecast_view = by_id("forecast-view")
forecast_chart = by_id("forecast-chart")
forecast_table = by_id("forecast-monthly-table")
forecast_rows = role("row").inside(forecast_table)
forecast_planned_header = role("columnheader", "Planned budget").inside(forecast_table)
forecast_horizon = role("spinbutton", "Horizon (months)")
plan_nav_link = role("link", "Plan", exact=True)

# --- anchor select (rendered on settings, posted to /budget/preferences/income-anchor) ---
anchor_select = by_id("anchor-select")


def summary_row(category_name: str) -> Locator:
    return role("row", category_name).inside(summary_table)


def summary_cells(category_name: str) -> Locator:
    return role("cell").inside(summary_row(category_name))


def rule_default_input(category_id: int) -> Locator:
    return by_id(f"rule-default-{category_id}")


def yearly_input(category_id: int, month: int) -> Locator:
    return by_id(f"y-{category_id}-{month}")


def option_in(select: Locator) -> Locator:
    return role("option").inside(select)


chart_image = role("img")


def role_in(role_name: str, scope: Locator) -> Locator:
    return role(role_name).inside(scope)


def yearly_row(category_name: str) -> Locator:
    return role("row", category_name).inside(yearly_section)


def rules_override_button(category_name: str) -> Locator:
    return role("button", f"Add override for {category_name}", exact=True)


# --- T-UT08b: year-grid override popover and period navigation ---------------


previous_month = role("link", "Previous month")
next_month = role("link", "Next month")


# --- T-UT08a: existing e2e journeys ---
tier_one_off = label("This month only")


# --- T-Q278: budget tab, year tab, forecast tab ----------------------------
period_region = role("region", "Budget period")
period_per_day = by_testid("period-per-day")
budget_rows = by_id("budget-row-", prefix=True)
budget_row_cells = role("cell").inside(budget_rows)
budget_row_spent = role("progressbar", "Spent").inside(budget_rows)
remainder_bar = role("progressbar", re.compile("actual vs planned"))
