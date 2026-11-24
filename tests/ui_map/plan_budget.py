"""Plan · budget tab on the Rising Dough markup (T-UR11, ADR-0107).

The handoff (``pages/plan/budget.html``) and the app render the same markup, so
one module serves both targets (``--target=app`` and ``--target=mockup``). The
shared period nav, picker and row menu names live in ``rd_fragments``.
"""

from __future__ import annotations

import re

from tests.ui_map.locator import Locator, role

hero = role("region", "budget left")
heading = role("heading", "budget left", level=1)
panel = role("region", "Budget")

# Plan view tabs (budget | year | forecast | analytics)
tabs = role("navigation", "Plan view")


def tab(name: str) -> Locator:
    return role("link", name, exact=True).inside(tabs)


# The category table
table = role("table", re.compile(r"^Budget by category"))
table_region = role("region", re.compile(r"^Budget by category"))
rows = role("row").inside(table)
total_row = role("row", re.compile(r"^Total\b")).inside(table)
column_headers = role("columnheader").inside(table)


def row(category_name: str) -> Locator:
    return role("row", category_name).inside(table)


def row_cells(category_name: str) -> Locator:
    return role("cell").inside(row(category_name))


def bar(category_name: str) -> Locator:
    return role("img").inside(row(category_name))


def row_menu_button(category_name: str) -> Locator:
    return role("button", "Row menu").inside(row(category_name))


def row_menu(category_name: str) -> Locator:
    return role("menu", f"{category_name} actions").inside(row(category_name))


def override_item(category_name: str) -> Locator:
    return role("menuitem", "override", exact=True).inside(row_menu(category_name))


def menu_cancel(category_name: str) -> Locator:
    return role("menuitem", "cancel", exact=True).inside(row_menu(category_name))


# The period trigger's name is the month label (its ▾ is aria-hidden)
period_trigger = role("button", re.compile(r"\b\d{4}\b")).inside(
    role("group", "Period", exact=True)
)
