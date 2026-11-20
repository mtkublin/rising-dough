"""Plan surface: budget, year grid, forecast, analytics."""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, role

heading = role("heading", level=1)
forecast_heading = role("heading", "Projected balance", level=1)
override = role("button", "Override")
year_selector = role("group", "Yearly budget year selector")
previous_year = role("button", "Previous year")
next_year = role("button", "Next year")
spend_by_category = role("img", "Spend by category")


def year_card(category_id: int) -> Locator:
    return by_id(f"year-card-{category_id}")


def year_cell(category_id: int, month: int) -> Locator:
    return by_id(f"yc-{category_id}-{month}")


def override_slot(category_id: int) -> Locator:
    return by_id(f"override-slot-{category_id}")
