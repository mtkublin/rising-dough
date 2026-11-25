"""Ledger surface (Actual view) against the handoff markup (``pages/ledger/actual*.html``).

Same names as ``tests.ui_map.ledger``. The handoff has fixed sample rows and no
row ids, so the id-parameterised builders return a sample row. The planned and
recurring views, the dialogs and the form helpers have no Actual-page twin
(``NO_HANDOFF_TWIN``); they delegate to the app map so ``surface("ledger",
"mockup")`` stays total, and the resolve test skips them.
"""

from __future__ import annotations

from bs4 import Tag

from tests.ui_map import _html, ledger as _app
from tests.ui_map.locator import Locator, label, role

heading = role("heading", "spent this period", level=1)
table = role("table", "Transactions")
table_container = table  # the handoff has no swap wrapper; the table is the region
filters_form = role("search", "Filter transactions")
filter_search = role("searchbox").inside(filters_form)
filter_category = label("category").inside(filters_form)
pagination = role("navigation", "Pages")
older_button = role("link", "older")
newer_button = role("link", "newer")  # shown from page 2 (the sample page is the first)
recently_deleted_link = role("link", "recently deleted")
_NAV = role("navigation", "Ledger view")

_SAMPLE = "Zakupy spożywcze"  # a groceries row (menu title carries the amount)
_SAMPLE_DAY = "SAT 31 OCT"

# Names the handoff Actual page does not render with a stable twin.
NO_HANDOFF_TWIN = frozenset(
    {
        "bulk_bar",
        "hero_figure",
        "menu_items",
        "txn_row_ids",
        "day_heads",
        "chips",
        "color_rules",
        "planned_row",
        "recurring_row",
        "skip_next",
        "deleted_row",
        "restore",
        "column_header",
        "table_rows",
        "recurring_expand",
        "menu_actions",
        "form_in",
        "controls",
        "control",
        "named_input",
        "view_row_actions",
        "row_kebab",
        "row_menu_item",
        "combobox_option",
        "entry_tab",
        "overlay_field",
        "combo_option",
        "row_action",
        "planned_promote",
        "planned_edit",
        "planned_menu",
        "recurring_menu",
        "formula_source",
    }
)
bulk_bar = _app.bulk_bar  # hidden until a row is selected; no twin
hero_figure = _app.hero_figure


def row(tx_id: int) -> Locator:
    return role("row", _SAMPLE).inside(table)


def row_menu(tx_id: int) -> Locator:
    return role("button", "Row menu").inside(row(tx_id))


def row_cells(tx_id: int) -> Locator:
    return role("cell").inside(row(tx_id))


def select_box(tx_id: int) -> Locator:
    return role("checkbox", "Select Zakupy").inside(row(tx_id))


def view_table(view: str) -> Locator:
    return table


def view_tab(name: str) -> Locator:
    return role("link", name).inside(_NAV)


def day_head(day_label: str) -> Locator:
    return role("row", _SAMPLE_DAY)


def menu_items(source: _html.Source, tx_id: int) -> dict[str, Tag]:
    return _app.menu_items(source, tx_id)


def txn_row_ids(source: _html.Source) -> list[str]:
    return _app.txn_row_ids(source)


def day_heads(source: _html.Source) -> list[str]:
    return _app.day_heads(source)


def chips(source: _html.Source) -> dict[str, str | None]:
    return _app.chips(source)


def color_rules(source: _html.Source) -> str:
    return _app.color_rules(source)


def planned_row(planned_id: int) -> Locator:
    return _app.planned_row(planned_id)


def recurring_row(rule_id: int) -> Locator:
    return _app.recurring_row(rule_id)


def skip_next(rule_id: int) -> Locator:
    return _app.skip_next(rule_id)


def deleted_row(kind: str, entity_id: int) -> Locator:
    return _app.deleted_row(kind, entity_id)


def restore(kind: str, entity_id: int) -> Locator:
    return _app.restore(kind, entity_id)


def column_header(name: str) -> Locator:
    return _app.column_header(name)


def table_rows(view: str) -> Locator:
    return _app.table_rows(view)


def recurring_expand(rule_id: int) -> Locator:
    return _app.recurring_expand(rule_id)


def menu_actions(source: _html.Source, row: Locator) -> dict[str, Tag]:
    return _app.menu_actions(source, row)


def form_in(source: _html.Source, container: Locator) -> Tag:
    return _app.form_in(source, container)


def controls(source: _html.Source, field: Locator) -> list[Tag]:
    return _app.controls(source, field)


def control(source: _html.Source, field: Locator) -> Tag:
    return _app.control(source, field)


def named_input(form: Tag, name: str) -> Tag:
    return _app.named_input(form, name)


def view_row_actions(view: str) -> Locator:
    return _app.view_row_actions(view)


def row_kebab(row_loc: Locator) -> Locator:
    return _app.row_kebab(row_loc)


def row_menu_item(row_loc: Locator, name: str) -> Locator:
    return _app.row_menu_item(row_loc, name)


def combobox_option(name: str) -> Locator:
    return _app.combobox_option(name)


def entry_tab(name: str) -> Locator:
    return _app.entry_tab(name)


def overlay_field(field: Locator) -> Locator:
    return _app.overlay_field(field)


def combo_option(name: str) -> Locator:
    return _app.combo_option(name)


def row_action(name: str) -> Locator:
    return _app.row_action(name)


def planned_promote(planned_id: int) -> Locator:
    return _app.planned_promote(planned_id)


def planned_edit(planned_id: int) -> Locator:
    return _app.planned_edit(planned_id)


def planned_menu(planned_id: int) -> Locator:
    return _app.planned_menu(planned_id)


def recurring_menu(rule_id: int) -> Locator:
    return _app.recurring_menu(rule_id)


def formula_source(category_name: str) -> Locator:
    return _app.formula_source(category_name)
