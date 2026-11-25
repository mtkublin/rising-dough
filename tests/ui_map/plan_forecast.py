"""Plan · forecast tab on the Rising Dough markup (T-UR12, ADR-0107).

The handoff (``pages/plan/forecast.html``) and the app render the same markup, so one
module serves both targets. The plan tabs and period names live in ``plan_budget``.
"""

from __future__ import annotations

import re

from tests.ui_map.locator import Locator, label, role

hero = role("region", re.compile(r"^projected balance"))
heading = role("heading", re.compile(r"^projected balance"), level=1)
panel = role("region", "Forecast")

# Horizon buttons (6 / 12 / 24 / 60 months); the pressed one is the current horizon
horizon_group = role("group", "HORIZON · MONTHS")
horizon_buttons = role("button").inside(horizon_group)
horizon_selected = role("button", pressed=True).inside(horizon_group)


def horizon_button(months: int) -> Locator:
    return role("button", str(months), exact=True).inside(horizon_group)


# The chart: one focusable point per month, named "<Mon YYYY>: <balance> PLN, net <net>"
chart = role("img", re.compile(r"^Projected balance by month"))
chart_points = label(", net ")

# The table
table_section = role("region", "Projected balance by month")
table = role("table").inside(table_section)
rows = role("row").inside(table)
column_headers = role("columnheader").inside(table)
planned_header = role("columnheader", "PLANNED BUDGET").inside(table)


def row(month_label: str) -> Locator:
    """The table row of a month (``Oct 2026``)."""
    return role("row", month_label).inside(table)


def row_cells(month_label: str) -> Locator:
    return role("cell").inside(row(month_label))
