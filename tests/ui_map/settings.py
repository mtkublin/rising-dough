"""Settings surface: categories, currency, preferences, security, users."""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, label, role

# --- shell of every settings page ---
tabs = role("tablist")
tab_any = role("tab").inside(tabs)
panel = by_id("main")
any_link = role("link")
heading = role("heading", level=1)
security_heading = role("heading", "Security", level=1)
users_heading = role("heading", "Users", level=1)
preferences_heading = role("heading", "Preferences")
fx_heading = role("heading", "FX cache")

# --- categories (T-UR13: handoff pages/settings/categories and the category dialogs) ---
new_category = role("link", "+ new category")
create_category = role("button", "create category")
any_category_row = by_id("category-", prefix=True)
category_slot = by_id(
    "settings-categories"
)  # the list region that refetches on settings-categories-stale
category_form = role("dialog", "category")  # the new / edit category dialog
category_name = label("name", exact=True)
category_default_colour = label("default colour")
category_expense = label("\u2193 expense")
category_income = label("\u2191 income")
income_anchor = label("income anchor")
form_errors = role("alert")
archive_dialog = role("alertdialog")
archive_confirm = role("button", "archive", exact=True).inside(archive_dialog)
modal_root = by_id("modal-root")
section_headings = role("heading", level=2)  # Expense, Income, System group titles

# --- security page (T-UR14: handoff pages/settings/security, security--error) ---
password_form = by_id("password-form")
current_password = label("current password", exact=True)
new_password = label("new password", exact=True)
confirm_password = label("confirm new password", exact=True)
change_password_button = role("button", "Change password")
save_and_continue = role("button", "Save and continue")
sign_out_instead = role("button", "Sign out instead")
password_summary = by_id("pw-summary")
forced_banner = role("note", "Your password needs rotating")
passkeys = role("region", "Passkeys", exact=True)
sessions = role("region", "Active sessions", exact=True)
session_signout = role("button", "Sign out")
passkey_label = label("label")
add_passkey = role("button", "Add passkey")

# --- users admin (T-UR14: handoff pages/settings/users and the edit-user, delete-user overlays) ---
users_table = by_id("users-table")
new_password_toast = by_id("new-password-toast")
new_password_value = by_id("new-password-value")
edit_form = role("dialog", "edit user")
edit_save = role("button", "save").inside(edit_form)
reset_dialog = role("alertdialog", "reset")
reset_confirm = role("button", "reset password").inside(reset_dialog)
delete_confirm = role("button", "delete user").inside(role("alertdialog", "delete"))
one_time_dialog = role("dialog", "one-time password")
one_time_done = role("button", "done").inside(one_time_dialog)
user_email = label("email", exact=True)
user_name = label("name", exact=True)
user_is_admin = label("admin", exact=True)
delete_dialog = role("alertdialog", "delete")
delete_blocked = role("alertdialog", "can't delete")
add_errors = by_id("error-summary")
flash_success = role("status")
flash_error = role("alert")


def password_error(field_name: str) -> Locator:
    return by_id(f"{field_name.replace('_', '-')}-error")


def tab(name: str) -> Locator:
    return role("tab", name).inside(tabs)


def category_row(category_id: int) -> Locator:
    return by_id(f"category-{category_id}")


def edit_category(category_id: int) -> Locator:
    return role("link", "edit", exact=True).inside(category_row(category_id))


def archive_category(category_id: int) -> Locator:
    return role("link", "archive", exact=True).inside(category_row(category_id))


def user_row(user_id: int) -> Locator:
    return by_id(f"user-row-{user_id}")


def remove_user(name: str) -> Locator:
    return role("menuitem", "delete user").inside(role("row", name))


def reset_user(name: str) -> Locator:
    return role("menuitem", "reset password").inside(role("row", name))


def user_menu(name: str) -> Locator:
    """The row-menu button of a user row (not on your own row)."""
    return role("button", "Row menu").inside(role("row", name))


def edit_user_item(name: str) -> Locator:
    return role("menuitem", "edit user").inside(role("row", name))


def passkey_remove(name: str) -> Locator:
    return role("button", f"Remove passkey {name}")


# --- T-UT08b: category form, FX tab, preferences, toast undo ----------------
form_name = category_name.inside(category_form)
form_income = category_income.inside(category_form)
form_expense = category_expense.inside(category_form)
form_create = create_category.inside(category_form)
edit_form_save = role("button", "save").inside(category_form)
edit_form_name = category_name.inside(category_form)
fx_table = role("table", "Cached FX rates")


def fx_row(pair: str) -> Locator:
    """A cached-rate row by its ``EUR → PLN`` pair text."""
    return role("row", pair).inside(fx_table)


pref_terms = role("term").inside(panel)
pref_values = role("definition").inside(panel)
prefs_panel_heading = role("heading", "Workspace", level=2)
theme_group = role("group", "theme")


def theme_option(value: str) -> Locator:
    """One of the system / light / dark buttons in the Appearance card (T-UR27)."""
    return role("button", value, exact=True).inside(theme_group)
