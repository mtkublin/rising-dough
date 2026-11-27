"""Ledger surface: actual, planned and recurring views."""

from __future__ import annotations

from bs4 import Tag

from tests.ui_map import _html
from tests.ui_map.locator import Locator, by_id, by_testid, label, role

heading = role("heading", level=1)
table = by_id("txn-table")
form = by_id("txn-form")
form_slot = by_id("txn-form-slot")
pagination = role("navigation", "Pages")
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
    """The 'Row menu' trigger inside a transaction row (the new shell's popover menu)."""
    return role("button", "Row menu").inside(row(tx_id))


def skip_next(rule_id: int) -> Locator:
    return role("menuitem", "skip next").inside(recurring_row(rule_id))


table_container = by_id("ledger-table")
filters_form = by_id("ledger-filters")


def deleted_row(kind: str, entity_id: int) -> Locator:
    """A row in 'Recently deleted' (``kind``: txn | planned | category)."""
    return by_id(f"deleted-{kind}-{entity_id}")


def restore(kind: str, entity_id: int) -> Locator:
    return role("button", "Restore").inside(deleted_row(kind, entity_id))


# --- T-UR09: the Actual view on the new shell --------------------------------
bulk_bar = by_id("ledger-bulk-bar")
newer_button = role("link", "newer")
hero_figure = by_id("ledger-spent")


export_menu = by_id("export-menu")


def export_hrefs(source: _html.Source) -> dict[str, str]:
    """Export menu links by label (``export as csv``); the popover is closed, so found by id."""
    menu = _html.resolve_one(source, by_id("export-menu"))
    return {a.get_text(strip=True): str(a.get("href")) for a in menu.find_all("a")}


def row_cells(tx_id: int) -> Locator:
    """The cells of a transaction row: select, description, category, amount, actions."""
    return role("cell").inside(row(tx_id))


def select_box(tx_id: int) -> Locator:
    return by_id(f"sel-{tx_id}")


def menu_items(source: _html.Source, tx_id: int) -> dict[str, Tag]:
    """Items of a transaction row menu keyed by label (edit, delete, cancel)."""
    menu = _html.resolve_one(source, by_id(f"menu-txn-{tx_id}"))
    return {el.get_text(strip=True): el for el in menu.find_all(None, {"role": "menuitem"})}


def txn_row_ids(source: _html.Source) -> list[str]:
    """Ids (``txn-N``) of the transaction rows of the Actual table, in page order."""
    table_root = _html.resolve_one(source, view_table("actual"))
    return [
        str(tr["id"])
        for tr in table_root.find_all("tr")
        if str(tr.get("id", "")).startswith("txn-")
    ]


def day_heads(source: _html.Source) -> list[str]:
    """Text of the day heading rows (``MON 02 NOV NET \u2212110.00``), in page order."""
    table_root = _html.resolve_one(source, view_table("actual"))
    return [
        " ".join(tr.get_text(" ").split())
        for tr in table_root.find_all("tr")
        if "rd-row--day" in (tr.get("class") or [])
    ]


def color_rules(source: _html.Source) -> str:
    """Custom-hue CSS rules of the table (`data-color-rules`), whitespace-free."""
    root = _html.resolve_one(source, by_id("ledger-table"))
    blocks = root.select("[data-color-rules]")
    return "".join("".join(str(block.get("data-color-rules", "")).split()) for block in blocks)


def chips(source: _html.Source) -> dict[str, str | None]:
    """Category chip text -> its ``data-color`` (None for the neutral chip)."""
    table_root = _html.resolve_one(source, view_table("actual"))
    return {
        c.get_text(strip=True): (str(c["data-color"]) if c.has_attr("data-color") else None)
        for c in table_root.find_all(class_="rd-chip")
    }


# --- forms (transaction / planned / recurring share labels) -----------------
planned_form = by_id("planned-form")
recurring_form = by_id("recurring-form")
slideover = role("dialog")
schedule_hero = by_id("ledger-hero")  # planned and recurring hero: label, figure, unit and note
field_date = label("Date")
field_amount = label("Amount")
field_category = label("Category")
field_account = label("Account")
field_dest_account = label("Dest")
field_note = label("Note")
field_description = label("Description")  # promote dialog
field_start = label("Start")
field_stop = label("Stop")
field_cadence = label("Cadence")

# --- tables -----------------------------------------------------------------
_TABLE_IDS = {"actual": "txn-table", "planned": "planned-table", "recurring": "recurring-table"}


def view_table(view: str) -> Locator:
    """The inner ``<table>`` wrapper of a ledger view (actual | planned | recurring)."""
    return by_id(_TABLE_IDS[view])


def view_tab(name: str) -> Locator:
    """A view tab link (``actual`` / ``planned`` / ``recurring``; the label carries the count)."""
    return role("link", name).inside(role("navigation", "Ledger view"))


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
    """Form controls behind a ``label`` locator.

    Kept (rather than a bare ``label()`` lookup) because ``label`` also matches
    any element carrying a matching ``aria-label`` (as Playwright does), e.g. the
    "Amount source" tablist next to the "Amount" input on the recurring form.
    """
    return [el for el in _html.resolve(source, field) if el.name in _CONTROLS]


def control(source: _html.Source, field: Locator) -> Tag:
    found = controls(source, field)
    if len(found) != 1:
        raise LookupError(f"expected one control for {field!r}, found {len(found)}")
    return found[0]


any_row = by_id("txn-", prefix=True)
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
    return {b.get_text(strip=True): b for b in tag.find_all(None, {"role": "menuitem"})}


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
filter_direction = label("direction").inside(filters_form)
filter_search = role("searchbox").inside(filters_form)
older_button = role("link", "older")
cancel_button = role("button", "Cancel")
add_rule_button = role("button", "Add rule")
next_month_button = role("button", "Next month")
any_virtual_planned_row = by_id("planned-v-", prefix=True)


def view_row_actions(view: str) -> Locator:
    """One row menu button per data row of a view (counts rows without id prefixes)."""
    return role("button", "Row menu").inside(view_table(view))


def row_kebab(row_loc: Locator) -> Locator:
    return role("button", "Row menu").inside(row_loc)


def row_menu_item(row_loc: Locator, name: str) -> Locator:
    return role("menuitem", name).inside(row_loc)


def combobox_option(name: str) -> Locator:
    """An option of the currently open combobox listbox (closed ones are hidden)."""
    return role("option", name, exact=True)


field_default_amount = role("textbox", "Amount", exact=True)  # recurring form (label sr-only)

formula_preview = by_testid("formula-preview")

# --- T-UT08b: add-entry overlay, row menus, Recently deleted -----------------
add_new = role("button", "+ Add")


def entry_tab(name: str) -> Locator:
    """A chip of the New entry overlay (``Happened`` / ``Planned`` / ``Repeats``)."""
    return role("tab", name).inside(slideover)


def overlay_field(field: Locator) -> Locator:
    """A form field (label locator) scoped to the open slide-over."""
    return field.inside(slideover)


def combo_option(name: str) -> Locator:
    """An option of an open combobox list inside the slide-over."""
    return role("option", name, exact=True).inside(slideover)


overlay_add_entry = add_entry.inside(slideover)
overlay_save = save.inside(slideover)
overlay_promote = promote.inside(slideover)
overlay_errors = role("alert").inside(slideover)
amount_source_formula = role("radio", "Formula").inside(slideover)
amount_source_fixed = role("radio", "Fixed value").inside(slideover)
rule_amount = role("textbox", "Amount", exact=True).inside(slideover)
formula_pick_sources = role("button", "pick sources").inside(slideover)
formula_coefficient = label("Coefficient (%)", exact=True).inside(slideover)
formula_sign_minus = role("radio", "\u2212", exact=True).inside(slideover)  # one per term
add_term = role("button", "+ Add term").inside(slideover)
save_rule = role("button", "Save rule").inside(slideover)
add_rule = role("button", "Add rule").inside(slideover)


def row_action(name: str) -> Locator:
    """A kebab menu item (``Edit`` / ``Delete`` / ``Promote`` / ...) once opened."""
    return role("menuitem", name, exact=True)


def planned_promote(planned_id: int) -> Locator:
    return role("link", "promote").inside(planned_row(planned_id))


def planned_edit(planned_id: int) -> Locator:
    return role("menuitem", "edit", exact=True).inside(planned_row(planned_id))


def planned_menu(planned_id: int) -> Locator:
    return role("button", "Row menu").inside(planned_row(planned_id))


def recurring_menu(rule_id: int) -> Locator:
    return role("button", "Row menu").inside(recurring_row(rule_id))


recently_deleted_link = role("link", "Recently deleted")


def formula_source(category_name: str) -> Locator:
    """A source-category checkbox of the (open) formula term picker."""
    return role("checkbox", category_name, exact=True).inside(slideover)
