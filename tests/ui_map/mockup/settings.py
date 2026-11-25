"""Settings surface against the handoff markup (``pages/settings/*``, category overlays; T-UR13).

Same function names as ``tests.ui_map.settings``. The handoff has fixed sample rows and no row ids,
so the id-parameterised builders return a sample row. Security and users names (T-UR14) keep the
app locator.
"""

from __future__ import annotations

from tests.ui_map import settings as _app
from tests.ui_map.locator import Locator, by_id, role

nav = role("navigation", "Settings")
tab_any = role("link").inside(nav)
panel = by_id("main")
heading = role("heading", level=1)
fx_heading = role("heading", "FX cache")
preferences_heading = role("heading", "Preferences")
prefs_panel_heading = role("heading", "Workspace", level=2)
pref_terms = role("term").inside(panel)
pref_values = role("definition").inside(panel)
section_headings = role("heading", level=2)
new_category = _app.new_category
income_anchor = _app.income_anchor
any_link = role("link")

# --- category overlays (pages/overlays/new-category, edit-category, archive-category) ---
category_form = role("dialog", "category")
category_name = _app.category_name
category_default_colour = _app.category_default_colour
category_expense = _app.category_expense
category_income = _app.category_income
create_category = _app.create_category
archive_dialog = _app.archive_dialog
archive_confirm = _app.archive_confirm

_SAMPLE_ROW = "Groceries"

# Names the handoff pages and category overlays do not render (ids, wrappers, live regions).
NO_HANDOFF_TWIN = frozenset(
    {"fx_table", "fx_row", "category_slot", "tabs", "form_errors", "modal_root"}
)

tabs = _app.tabs
category_slot = _app.category_slot
form_errors = _app.form_errors
modal_root = _app.modal_root
any_category_row = role("row", _SAMPLE_ROW)
form_name = category_name.inside(category_form)
form_income = category_income.inside(category_form)
form_expense = category_expense.inside(category_form)
form_create = create_category.inside(category_form)
edit_form_save = role("button", "save").inside(category_form)
edit_form_name = category_name.inside(category_form)
fx_table = _app.fx_table

# security and users (T-UR14): app locators until that item
security_heading = _app.security_heading
users_heading = _app.users_heading
password_form = _app.password_form
current_password = _app.current_password
new_password = _app.new_password
confirm_password = _app.confirm_password
change_password_button = _app.change_password_button
save_and_continue = _app.save_and_continue
sign_out_instead = _app.sign_out_instead
password_summary = _app.password_summary
forced_banner = _app.forced_banner
passkeys = _app.passkeys
sessions = _app.sessions
session_signout = _app.session_signout
passkey_label = _app.passkey_label
add_passkey = _app.add_passkey
users_table = _app.users_table
new_password_toast = _app.new_password_toast
new_password_value = _app.new_password_value
edit_form = _app.edit_form
user_email = _app.user_email
user_name = _app.user_name
user_is_admin = _app.user_is_admin
create_user = _app.create_user
add_errors = _app.add_errors
flash_success = _app.flash_success
flash_error = _app.flash_error


def tab(name: str) -> Locator:
    return role("link", name).inside(nav)


def category_row(category_id: int) -> Locator:
    return role("row", _SAMPLE_ROW)


def edit_category(category_id: int) -> Locator:
    return role("link", "edit", exact=True).inside(category_row(category_id))


def archive_category(category_id: int) -> Locator:
    return role("link", "archive", exact=True).inside(category_row(category_id))


def fx_row(pair: str) -> Locator:
    return role("row", pair)


def password_error(field_name: str) -> Locator:
    return _app.password_error(field_name)


def user_row(user_id: int) -> Locator:
    return _app.user_row(user_id)


def remove_user(name: str) -> Locator:
    return _app.remove_user(name)


def reset_user(name: str) -> Locator:
    return _app.reset_user(name)


def passkey_remove(name: str) -> Locator:
    return _app.passkey_remove(name)
