"""Plan · analytics tab on the Rising Dough markup (T-UR12, ADR-0107).

The handoff (``pages/plan/analytics.html``) and the app render the same markup, so one
module serves both targets. The plan tabs and period names live in ``plan_budget``.
"""

from __future__ import annotations

import re

from tests.ui_map.locator import Locator, label, role

hero = role("region", "where it went")
heading = role("heading", "where it went", level=1)
panel = role("region", "Analytics")

# Range buttons (month / year to date / 12 months)
range_group = role("group", "Range")
range_buttons = role("button").inside(range_group)
range_selected = role("button", pressed=True).inside(range_group)


def range_button(name: str) -> Locator:
    return role("button", name, exact=True).inside(range_group)


# Spend by category
spend_section = role("region", "Spend by category")
spend_table = role("table").inside(spend_section)
spend_rows = role("row").inside(spend_table)
spend_headers = role("columnheader").inside(spend_table)


def spend_row(category: str) -> Locator:
    return role("row", category).inside(spend_table)


def spend_cells(category: str) -> Locator:
    return role("cell").inside(spend_row(category))


def spend_link(category: str) -> Locator:
    """The chip link of a row: named ``<category>: <amount> PLN, open in ledger``."""
    return role("link", re.compile(rf"^{re.escape(category)}: ")).inside(spend_row(category))


def share_bar(category: str) -> Locator:
    return role("img", re.compile(r"percent of spend$")).inside(spend_row(category))


# Income vs expense chart: one focusable month, named "<Mon YYYY>: income <n> PLN, expense <n> PLN"
flow_section = role("region", "Income vs expense")
flow_chart = role("img", re.compile(r"^Monthly income and expense")).inside(flow_section)
flow_months = label(", expense ")

# Largest single items
largest_section = role("region", "Largest single items")
largest_items = role("listitem").inside(largest_section)
