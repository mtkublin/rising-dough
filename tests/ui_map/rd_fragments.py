"""Locators for the shared Rising Dough template fragments (T-UR04, ADR-0107 §3-§5).

One module for the fragments used by more than one surface: category picker, formula,
amount input, period picker and nav, row menu, ledger pagination. The handoff boards and
the app render the same markup, so a page journey reuses these names.
"""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_testid, label, role

# Category picker
category_recent_radios = role("radio")  # the picker is the only radio group of its fragment
category_search_button = role("button", "search all")
category_panel = role("group", "Pick a category")
category_search_input = role("combobox", "Search categories")
category_list = role("listbox", "Categories")
category_options = role("option").inside(category_list)
category_new_button = role("button", "new category")  # inline create in the picker (T-UR68)


def category_option(name: str) -> Locator:
    """Searchable list row by category name."""
    return role("option", name).inside(category_list)


# Formula and components
formula = role("group", "formula")
formula_add = role("button", "add component")
formula_result = role("status").inside(formula)


def component_sign(number: int, sign: str) -> Locator:
    """Sign radio of a component: ``add`` or ``subtract``."""
    return role("radio", sign, exact=True).inside(role("radiogroup", f"Sign of component {number}"))


component_percents = role("textbox", "Percentage")  # one per component, in order


def component_remove(number: int) -> Locator:
    return role("button", f"Remove component {number}", exact=True)


# Amount input
def amount_field(text: str = "amount") -> Locator:
    """Labelled amount input (``label`` is the visible label text)."""
    return label(text, exact=True)


# Period nav and picker
period_nav = role("group", "Period", exact=True)
period_prev = role("link", "Previous period").inside(period_nav)
period_next = role("link", "Next period").inside(period_nav)
period_trigger = role("button", "▾").inside(period_nav)
period_picker = role("dialog", "Pick period")
period_prev_year = role("link", "Previous year").inside(period_picker)
period_next_year = role("link", "Next year").inside(period_picker)
# htmx marks this swapped node htmx-added/htmx-settling until it has bound the arrows (hx-get)
period_picker_head = by_testid("period-pick-head")


def period_cell(text: str) -> Locator:
    """Month or year link inside the picker."""
    return role("link", text, exact=True).inside(period_picker)


# Row menu
row_menu_button = role("button", "Row menu")
row_menu = role("menu", "Row actions")


def row_menu_item(text: str) -> Locator:
    """Any kind of item: link, HTMX get (opens a dialog), HTMX post, destructive or phone-only."""
    return role("menuitem", text, exact=True).inside(row_menu)


row_menu_cancel = row_menu_item("cancel")  # always appended; closes the popover


# Ledger pagination
pagination = role("navigation", "Pages")
older = role("link", "older").inside(pagination)
newer = role("link", "newer").inside(pagination)
recently_deleted = role("link", "recently deleted").inside(pagination)
