"""New-entry and promote dialogs (T-UR07b, ADR-0107).

Handoff: ``pages/overlays/new-entry--*``, ``promote--*``. One dialog named "new entry" with three
tabs (happened, planned, repeats) and one promote dialog per source (planned: "promote to actual ·
<category>", recurring: "promote · <category>"). Names resolve in the app and, through
``tests.ui_map.mockup.entries``, in the handoff overlays.
"""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, label, role

dialog = role("dialog", "new entry", exact=True)

# --- tabs (links that swap the dialog) ---
tab_happened = role("link", "happened", exact=True).inside(dialog)
tab_planned = role("link", "planned", exact=True).inside(dialog)
tab_repeats = role("link", "repeats", exact=True).inside(dialog)

# --- fields (labels are the handoff's; the posted names are the existing routes') ---
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
    """A recent-category radio (label text is the category name)."""
    return label(name, exact=True)


# --- promote dialogs ---
def promote_dialog(title: str) -> Locator:
    return role("dialog", title, exact=True)


promote_amount = role("textbox", "Amount", exact=True)
promote_date = label("date", exact=True)
promote_note = label("note", exact=True)
promote_submit = role("button", "[ promote ]", exact=True)

# --- edit-transaction dialog (T-UR09b; handoff overlays/edit-transaction*.html) ---
# Same field names as the new-entry dialog (account, date, note, save, cancel); these are the ones
# that differ: its title carries the category, the destination label is "destination".
edit_dialog = role("dialog", "edit transaction")
edit_amount = role("textbox", "Amount", exact=True).inside(edit_dialog)
edit_category_group = role("group", "category", exact=True).inside(edit_dialog)
edit_category_search = role("button").inside(edit_category_group)
edit_category_query = role("combobox", "Search categories", exact=True).inside(edit_dialog)
edit_dest = label("destination", exact=True)
edit_save = role("button", "[ save ]", exact=True).inside(edit_dialog)
edit_dialog_title = role("heading", "edit transaction").inside(edit_dialog)
toast_undo = role("button", "undo", exact=True)  # the toast after a delete (T-UR09b)
edit_hero_error = by_id("field-amount-error")

# --- app only: ids the server renders ---
edit_opener = role("region", "Edit transaction", exact=True)  # plain page load: asks the edit route
opener = role("region", "New entry", exact=True)  # plain page load: asks /add for the dialog
credit_line = by_id("credit-line")
summary = by_id("error-summary")
hero_refresh = by_id("hero-refresh")  # hidden: carries the hero refresh trigger (T-UR04g)

# --- formula components (repeats tab, formula mode) ---
formula_percent = role("textbox", "Percentage", exact=True).inside(formula_group)
formula_subtract = role("radio", "subtract", exact=True).inside(formula_group)
formula_add_component = role("button", "+ add component", exact=True).inside(formula_group)
formula_pick = role("button", "pick categories", exact=True).inside(formula_group)
formula_result = role("status").inside(formula_group)
