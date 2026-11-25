"""Planned and recurring edit dialogs, the occurrence override and its removal (T-UR10, ADR-0107).

The handoff (``pages/overlays/edit-planned.html``, ``edit-recurring--*.html``,
``override--occurrence.html``, ``override--remove.html``) and the app render the same markup, so one
module serves both targets. Titles carry the category: ``edit planned · Car``,
``edit recurring rule · Taxes``, ``override occurrence · Fixed Costs``.
"""

from __future__ import annotations

from tests.ui_map import rd_dialogs
from tests.ui_map.locator import Locator, by_id, by_testid, label, role


def planned_dialog(category_name: str) -> Locator:
    return rd_dialogs.dialog(f"edit planned · {category_name}")


def recurring_dialog(category_name: str) -> Locator:
    return rd_dialogs.dialog(f"edit recurring rule · {category_name}")


def occurrence_dialog(category_name: str) -> Locator:
    return rd_dialogs.dialog(f"override occurrence · {category_name}")


def remove_dialog() -> Locator:
    return rd_dialogs.alert_dialog("Remove override?")


def hero_amount(scope: Locator) -> Locator:
    return rd_dialogs.hero_amount(scope)


def category_group(scope: Locator) -> Locator:
    return role("group", "category", exact=True).inside(scope)


def category_choice(scope: Locator, name: str) -> Locator:
    """A recent-category radio inside the dialog (label text is the category name)."""
    return label(name, exact=True).inside(scope)


def save(scope: Locator) -> Locator:
    return rd_dialogs.action(scope, "[ save ]")


def save_rule(scope: Locator) -> Locator:
    return rd_dialogs.action(scope, "[ save rule ]")


def cancel(scope: Locator) -> Locator:
    return rd_dialogs.action(scope, "cancel")


def keep(scope: Locator) -> Locator:
    return rd_dialogs.action(scope, "keep")


def remove(scope: Locator) -> Locator:
    return rd_dialogs.action(scope, "remove")


# --- fields (labels are the handoff's) ---
def field_account(scope: Locator) -> Locator:
    return label("account", exact=True).inside(scope)


def field_due(scope: Locator) -> Locator:
    return label("due date", exact=True).inside(scope)


def field_note(scope: Locator) -> Locator:
    return label("note", exact=True).inside(scope)


def field_start(scope: Locator) -> Locator:
    return label("start", exact=True).inside(scope)


def field_stop(scope: Locator) -> Locator:
    return label("stop · optional", exact=True).inside(scope)


def field_day(scope: Locator) -> Locator:
    return label("day of month", exact=True).inside(scope)


def field_dest(scope: Locator) -> Locator:
    return label("destination account", exact=True).inside(scope)


def amount_fixed(scope: Locator) -> Locator:
    return label("fixed value", exact=True).inside(scope)


def amount_formula(scope: Locator) -> Locator:
    return label("formula ƒ", exact=True).inside(scope)


def cadence_group(scope: Locator) -> Locator:
    return role("radiogroup", "cadence", exact=True).inside(scope)


def formula_group(scope: Locator) -> Locator:
    return role("group", "formula", exact=True).inside(scope)


def formula_percent(scope: Locator) -> Locator:
    """The percentage box of the only formula component."""
    return role("textbox", "Percentage", exact=True).inside(scope)


def formula_pick(scope: Locator) -> Locator:
    """The category picker of the first formula component (reads "pick categories" when empty)."""
    return role("button", "pick categories", exact=True).inside(scope)


def formula_option(scope: Locator, name: str) -> Locator:
    """A category checkbox of a formula component's picker."""
    return role("checkbox", name, exact=True).inside(scope)


# --- occurrence override: the month stepper ---
def month_group(scope: Locator) -> Locator:
    return role("group", "month", exact=True).inside(scope)


def month_prev(scope: Locator) -> Locator:
    return role("link", "Previous month", exact=True).inside(scope)


def month_next(scope: Locator) -> Locator:
    return role("link", "Next month", exact=True).inside(scope)


# --- opening from an Upcoming row (Today): the row menu holds "override" ---
def row_menu_button(row: Locator) -> Locator:
    return role("button", "Row menu", exact=True).inside(row)


def override_item(row: Locator) -> Locator:
    return role("menuitem", "override", exact=True).inside(row)


# --- app only: ids the server renders (no handoff twin) ---
def field_error(scope: Locator, name: str) -> Locator:
    """The ▲ line under field ``name`` of a failed save inside ``scope`` (Q18, no summary box)."""
    return by_id(f"field-{name}-error").inside(scope)


formula_result = by_testid("formula-preview")
category_chosen = by_id("catpick-edit-planned-picked")
