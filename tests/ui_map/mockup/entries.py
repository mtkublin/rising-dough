"""New-entry and promote dialogs against the handoff overlays.

Pages: ``pages/overlays/new-entry--*``, ``promote--*``. Same names as ``tests.ui_map.entries``. The
handoff dialog ids are generated (``dlg-172``) and its tab links point at the other overlay pages;
labels and roles match the app's.
"""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, label, role

dialog = role("dialog", "new entry", exact=True)

tab_happened = role("link", "happened", exact=True).inside(dialog)
tab_planned = role("link", "planned", exact=True).inside(dialog)
tab_repeats = role("link", "repeats", exact=True).inside(dialog)

hero_amount = role("textbox", "Amount", exact=True).inside(dialog)
category_group = role("group", "category", exact=True).inside(dialog)
category_search = role("button").inside(category_group)
category_query = role("combobox", "Search categories", exact=True).inside(dialog)
category_chosen = by_id("catpick-new-entry-picked")
field_account = label("account", exact=True)
field_date = label("date", exact=True)
field_due = label("due date", exact=True)
field_note = label("note", exact=True)
field_start = label("start", exact=True)
field_stop = label("stop · optional", exact=True)
field_day = label("day of month", exact=True)
amount_fixed = label("fixed value", exact=True)
amount_formula = label("formula ƒ", exact=True)
cadence_group = role("radiogroup", "cadence", exact=True)
cadence_quarterly = label("quarterly", exact=True)
field_dest = label("destination account", exact=True)
formula_group = role("group", "formula", exact=True)
save = role("button", "[ save ]", exact=True).inside(dialog)
cancel = role("button", "cancel", exact=True).inside(dialog)
alert = role("alert")


def category_option(name: str) -> Locator:
    return label(name, exact=True)


def promote_dialog(title: str) -> Locator:
    return role("dialog", title, exact=True)


promote_amount = role("textbox", "Amount", exact=True)
promote_date = label("date", exact=True)
promote_note = label("note", exact=True)
promote_submit = role("button", "[ promote ]", exact=True)

# --- edit-transaction dialog (T-UR09b) ---
edit_dialog = role("dialog", "edit transaction")
edit_amount = role("textbox", "Amount", exact=True).inside(edit_dialog)
edit_category_group = role("group", "category", exact=True).inside(edit_dialog)
edit_category_search = role("button").inside(edit_category_group)
edit_category_query = role("combobox", "Search categories", exact=True).inside(edit_dialog)
edit_dest = label("destination", exact=True)
edit_save = role("button", "[ save ]", exact=True).inside(edit_dialog)
edit_hero_error = by_id("hero-amount-error")
edit_dialog_title = role("heading", "edit transaction").inside(edit_dialog)
toast_undo = role("button", "undo", exact=True)

# Server-rendered ids with no handoff twin (the credit line is a plain paragraph there).
NO_HANDOFF_TWIN = frozenset(
    {
        "credit_line",
        "formula_percent",
        "formula_subtract",
        "formula_add_component",
        "formula_pick",
        "formula_result",
        "summary",
        "opener",
        "category_chosen",
        "category_query",  # the handoff search panel is hidden until opened
        "field_dest",
        "edit_opener",
        "edit_category_query",  # the handoff search panel is hidden until opened
        "toast_undo",
        "hero_refresh",
    }
)
opener = role("region", "New entry", exact=True)
edit_opener = role("region", "Edit transaction", exact=True)
credit_line = by_id("credit-line")
summary = by_id("error-summary")
hero_refresh = by_id("hero-refresh")

# Formula components: same markup as the app; the e2e journeys drive the app, not the handoff.
formula_percent = role("textbox", "Percentage", exact=True).inside(formula_group)
formula_subtract = role("radio", "subtract", exact=True).inside(formula_group)
formula_add_component = role("button", "+ add component", exact=True).inside(formula_group)
formula_pick = role("button", "pick categories", exact=True).inside(formula_group)
formula_result = role("status").inside(formula_group)
