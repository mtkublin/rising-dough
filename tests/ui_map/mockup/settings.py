"""Settings surface against the handoff markup (``pages/settings/*``, category overlays; T-UR13).

Same function names as ``tests.ui_map.settings``. The handoff has fixed sample rows and no row ids,
so the id-parameterised builders return a sample row. Security and users names resolve on
the handoff pages and overlays (T-UR14).
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
theme_group = _app.theme_group
pref_terms = role("term").inside(panel)
pref_values = role("definition").inside(panel)
section_headings = role("heading", level=2)
new_category = _app.new_category
income_anchor = _app.income_anchor


def anchor_option(name: str) -> Locator:
    """The handoff has no income-anchor control; mirror the app builder on the same label."""
    return role("option", name, exact=True).inside(income_anchor)


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
    {
        "fx_table",
        "fx_row",
        "category_slot",
        "tabs",
        "modal_root",
        "password_summary",
        "forced_banner",
        "save_and_continue",
        "sign_out_instead",
        "settings_tab",
    }
)

tabs = _app.tabs
category_slot = _app.category_slot
modal_root = _app.modal_root
any_category_row = role("row", _SAMPLE_ROW)
form_name = category_name.inside(category_form)
form_income = category_income.inside(category_form)
form_expense = category_expense.inside(category_form)
form_create = create_category.inside(category_form)
edit_form_save = role("button", "save").inside(category_form)
edit_form_name = category_name.inside(category_form)
fx_table = _app.fx_table

# security and users (T-UR14: pages/settings/security, security--error, users; overlays/edit-user,
# delete-user, one-time-password)
security_heading = _app.security_heading
users_heading = _app.users_heading
password_form = role("region", "Password", exact=True)
current_password = _app.current_password
new_password = _app.new_password
confirm_password = _app.confirm_password
change_password_button = _app.change_password_button
passkeys = _app.passkeys
sessions = _app.sessions
session_signout = _app.session_signout
passkey_label = _app.passkey_label
add_passkey = _app.add_passkey
users_table = role("table", "Users")
new_password_toast = role("dialog", "one-time password")
new_password_value = role("status", "One-time password")
edit_form = _app.edit_form
edit_save = _app.edit_save
reset_dialog = _app.reset_dialog
reset_confirm = _app.reset_confirm
delete_confirm = _app.delete_confirm
one_time_dialog = _app.one_time_dialog
one_time_done = _app.one_time_done
user_email = _app.user_email
user_name = _app.user_name
user_is_admin = _app.user_is_admin
delete_dialog = _app.delete_dialog
delete_blocked = _app.delete_blocked
add_errors = _app.add_errors
flash_success = _app.flash_success
flash_error = _app.flash_error
# T-UR20a: invite dialogs and rows (the handoff overlays differ in ids; the app names are shared)
create_invite_link = _app.create_invite_link
create_invite_dialog = _app.create_invite_dialog
invite_email_field = _app.invite_email_field
invite_role_admin = _app.invite_role_admin
invite_submit = _app.invite_submit
invite_email_error = _app.invite_email_error
invite_link_dialog = _app.invite_link_dialog
invite_link_value = _app.invite_link_value
revoke_invite_dialog = _app.revoke_invite_dialog
revoke_invite_confirm = _app.revoke_invite_confirm
any_invite_row = _app.any_invite_row
flash_error_region = _app.flash_error_region
flash_error_close = _app.flash_error_close
# no handoff twin: the forced rotation page (T-UR20) and the 422 / throttle summary
save_and_continue = _app.save_and_continue
sign_out_instead = _app.sign_out_instead
password_summary = _app.password_summary
forced_banner = _app.forced_banner


def theme_option(value: str) -> Locator:
    return role("button", value, exact=True).inside(theme_group)


def settings_tab(label: str) -> Locator:
    """A settings tab by its accessible name; the handoff strip is plain links (T-UR97)."""
    return role("link", label, exact=True).inside(nav)


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
    return role("row", "partner@example.test")


def remove_user(name: str) -> Locator:
    return _app.remove_user(name)


def reset_user(name: str) -> Locator:
    return _app.reset_user(name)


def user_menu(name: str) -> Locator:
    return _app.user_menu(name)


def edit_user_item(name: str) -> Locator:
    return _app.edit_user_item(name)


def passkey_remove(name: str) -> Locator:
    return _app.passkey_remove(name)


def invite_row(invite_id: int) -> Locator:
    return _app.invite_row(invite_id)


def invite_menu_item(label_text: str, invite_id: int) -> Locator:
    return _app.invite_menu_item(label_text, invite_id)
