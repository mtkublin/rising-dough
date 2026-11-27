"""Plan · budget tab on the Rising Dough markup (T-UR11, ADR-0107).

The handoff (``pages/plan/budget.html``) and the app render the same markup, so
one module serves both targets (``--target=app`` and ``--target=mockup``). The
shared period nav, picker and row menu names live in ``rd_fragments``.
"""

from __future__ import annotations

import re

from tests.ui_map.locator import Locator, by_id, role

hero = role("region", "budget left")
heading = role("heading", "budget left", level=1)
panel = role("region", "Budget")

# Plan view tabs (budget | year | forecast | analytics)
tabs = role("navigation", "Plan view")


def tab(name: str) -> Locator:
    return role("link", name, exact=True).inside(tabs)


# The category table
table = role("table", re.compile(r"^Budget by category(?! without)"))
table_region = role("region", re.compile(r"^Budget by category(?! without)"))
rows = role("row").inside(table)
total_row = role("row", re.compile(r"^Total\b")).inside(table)
column_headers = role("columnheader").inside(table)


# Categories without a budget: a collapsed disclosure under the table (R14, R20)
disclosure = role("button", re.compile(r"without a budget$"))
unbudgeted_table = role("table", re.compile(r"^Budget by category without a budget"))
unbudgeted_rows = role("row").inside(unbudgeted_table)
unbudgeted_table_region = role("region", re.compile(r"^Budget by category without a budget"))


def unbudgeted_row(category_name: str) -> Locator:
    return role("row", category_name).inside(unbudgeted_table)


def unbudgeted_cells(category_name: str) -> Locator:
    return role("cell").inside(unbudgeted_row(category_name))


def unbudgeted_status_cell(category_name: str) -> Locator:
    """The STATUS cell (4th) of an unbudgeted row: it holds the "set budget" button."""
    return role("cell", re.compile(r"set budget")).inside(unbudgeted_row(category_name))


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


def edit_budget_item(category_name: str) -> Locator:
    """The row menu item of a budgeted row (R4: "edit budget", was "override")."""
    return role("menuitem", "edit budget", exact=True).inside(row_menu(category_name))


def set_budget_button(category_name: str) -> Locator:
    """The visible "set budget" button in the status cell of an unbudgeted row (F4.6c, R20)."""
    return role("button", "set budget", exact=True).inside(unbudgeted_row(category_name))


no_budget_hint = by_id("budget-hint")
"""One line shown only while no expense category has a budget."""


def menu_cancel(category_name: str) -> Locator:
    return role("menuitem", "cancel", exact=True).inside(row_menu(category_name))


# The period trigger's name is the month label (its ▾ is aria-hidden)
period_trigger = role("button", re.compile(r"\b\d{4}\b")).inside(
    role("group", "Period", exact=True)
)
