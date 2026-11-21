"""Ledger surface: actual, planned and recurring views."""

from __future__ import annotations

from bs4 import Tag

from tests.ui_map import _html
from tests.ui_map.locator import Locator, by_id, label, role

heading = role("heading", level=1)
table = by_id("txn-table")
form = by_id("txn-form")
form_slot = by_id("txn-form-slot")
pagination = role("navigation", "Pagination")
search = label("Search")
add_entry = role("button", "Add entry")
save = role("button", "Save")
promote = role("button", "Promote")
recently_deleted_heading = role("heading", "Recently deleted", level=1)


def row(tx_id: int) -> Locator:
    return by_id(f"txn-{tx_id}")


def planned_row(planned_id: int) -> Locator:
    return by_id(f"planned-p-{planned_id}")


def recurring_row(rule_id: int) -> Locator:
    return by_id(f"recurring-{rule_id}")


def row_menu(tx_id: int) -> Locator:
    """The 'Row actions' menu trigger inside a transaction row."""
    return role("button", "Row actions").inside(row(tx_id))


def skip_next(rule_id: int) -> Locator:
    return role("button", f"Skip next occurrence of rule {rule_id}")


table_container = by_id("ledger-table")
filters_form = by_id("ledger-filters")


def deleted_row(kind: str, entity_id: int) -> Locator:
    """A row in 'Recently deleted' (``kind``: txn | planned | category)."""
    return by_id(f"deleted-{kind}-{entity_id}")


def restore(kind: str, entity_id: int) -> Locator:
    return role("button", "Restore").inside(deleted_row(kind, entity_id))


# --- forms (transaction / planned / recurring share labels) -----------------
planned_form = by_id("planned-form")
recurring_form = by_id("recurring-form")
slideover = role("dialog")
form_errors = role("alert")
limit_preview = by_id("limit-preview")
field_date = label("Date")
field_amount = label("Amount")
field_category = label("Category")
field_account = label("Account")
field_dest_account = label("Dest")
field_note = label("Note")
field_start = label("Start")
field_stop = label("Stop")
field_cadence = label("Cadence")

# --- tables -----------------------------------------------------------------
_TABLE_IDS = {"actual": "txn-table", "planned": "planned-table", "recurring": "recurring-table"}


def view_table(view: str) -> Locator:
    """The inner ``<table>`` wrapper of a ledger view (actual | planned | recurring)."""
    return by_id(_TABLE_IDS[view])


def view_tab(name: str) -> Locator:
    """A segmented view tab (``Actual`` / ``Planned`` / ``Recurring``)."""
    return role("tab", name)


def column_header(name: str) -> Locator:
    return role("columnheader", name, exact=True)


def table_rows(view: str) -> Locator:
    return role("row").inside(view_table(view))


def day_head(day_label: str) -> Locator:
    """A day (or cadence) group header row, e.g. ``02 Nov``."""
    return role("row", day_label)


def recurring_expand(rule_id: int) -> Locator:
    """The (collapsed) override / formula detail row of a recurring rule."""
    return by_id(f"recurring-{rule_id}-expand")


_CONTROLS = frozenset({"input", "select", "textarea"})


def controls(source: _html.Source, field: Locator) -> list[Tag]:
    """Form controls behind a ``label`` locator (the resolver also yields the
    label's wrapper descendants; only the real controls are returned)."""
    return [el for el in _html.resolve(source, field) if el.name in _CONTROLS]


def control(source: _html.Source, field: Locator) -> Tag:
    found = controls(source, field)
    if len(found) != 1:
        raise LookupError(f"expected one control for {field!r}, found {len(found)}")
    return found[0]


any_row = by_id("txn-", prefix=True)
any_recurring_row = by_id("recurring-", prefix=True)
any_planned_row = by_id("planned-p-", prefix=True)
any_header = role("columnheader")

override_applied = role("status", "Override applied")
promote_dialog = role("dialog", "Promote recurring")
override_dialog = role("dialog", "Override occurrence")


def menu_actions(source: _html.Source, row: Locator) -> dict[str, Tag]:
    """Row-action menu items of a row, keyed by label.

    The kebab menu is collapsed (``hidden``) in the markup, so role locators skip
    it; navigate from the mapped row instead.
    """
    tag = _html.resolve_one(source, row)
    return {b.get_text(strip=True): b for b in tag.find_all("button", attrs={"role": "menuitem"})}


def form_in(source: _html.Source, container: Locator) -> Tag:
    """The ``<form>`` inside a mapped container (a dialog has no form role)."""
    tag = _html.resolve_one(source, container).find("form")
    if not isinstance(tag, Tag):
        raise LookupError(f"no form inside {container!r}")
    return tag


def named_input(form: Tag, name: str) -> Tag:
    el = form.find("input", attrs={"name": name})
    if not isinstance(el, Tag):
        raise LookupError(f"no input named {name!r}")
    return el


# --- T-UT08a: existing e2e journeys ---
filter_category = label("Category").inside(filters_form)
filter_search = role("searchbox").inside(filters_form)
older_button = role("button", "Older")
cancel_button = role("button", "Cancel")
add_rule_button = role("button", "Add rule")
next_month_button = role("button", "Next month")
any_virtual_planned_row = by_id("planned-v-", prefix=True)
row_actions = role("button", "Row actions")


def view_row_actions(view: str) -> Locator:
    """One 'Row actions' kebab per data row of a view (counts rows without id prefixes)."""
    return row_actions.inside(view_table(view))


def row_kebab(row_loc: Locator) -> Locator:
    return row_actions.inside(row_loc)


def row_menu_item(row_loc: Locator, name: str) -> Locator:
    return role("menuitem", name).inside(row_loc)


def combobox_option(name: str) -> Locator:
    """An option of the currently open combobox listbox (closed ones are hidden)."""
    return role("option", name, exact=True)


field_default_amount = role("textbox", "Amount", exact=True)  # recurring form (label sr-only)
