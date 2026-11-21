"""Settings surface: categories, currency, preferences, security, users."""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, label, role

# --- shell of every settings page ---
tabs = role("tablist")
tab_any = role("tab").inside(tabs)
drawer = role("dialog", "Settings")
drawer_title = by_id("drawer-title")

panel = role("tabpanel")
any_link = role("link")
heading = role("heading", level=1)
security_heading = role("heading", "Security", level=1)
users_heading = role("heading", "Users", level=1)
preferences_heading = role("heading", "Preferences")
fx_heading = role("heading", "FX cache")

# --- categories ---
new_category = role("button", "+ New category")
create_category = role("button", "Create category")
any_category_row = by_id("category-", prefix=True)
category_slot = by_id("cat-form-slot")
category_form = by_id("category-form")
category_name = label("Name")
category_default_colour = label("Use direction colour")
category_expense = label("Expense")
category_income = label("Income")
income_anchor = label("Income anchor")
form_errors = role("alert")

# --- security page ---
password_form = by_id("password-form")
current_password = label("Current password", exact=True)
new_password = label("New password", exact=True)
confirm_password = label("Confirm new password", exact=True)
change_password_button = role("button", "Change password")
save_and_continue = role("button", "Save and continue")
sign_out_instead = role("button", "Sign out instead")
password_summary = by_id("pw-summary")
forced_banner = role("note", "Your password needs rotating")
passkeys = by_id("passkeys")
sessions = by_id("sessions")
session_signout = role("button", "Sign out")
passkey_label = label("Label")
add_passkey = role("button", "Add passkey")

# --- users admin ---
users_table = by_id("users-table")
new_password_toast = by_id("new-password-toast")
new_password_value = by_id("new-password-value")
edit_form = by_id("user-edit-form")
user_email = label("Email", exact=True)
user_name = label("Name", exact=True)
user_is_admin = label("Admin")
create_user = role("button", "Create user")
add_errors = role("alert")
flash_success = role("status")
flash_error = role("alert")


def password_error(field_name: str) -> Locator:
    return by_id(f"pw-{field_name}-error")


def tab(name: str) -> Locator:
    return role("tab", name).inside(tabs)


def category_row(category_id: int) -> Locator:
    return by_id(f"category-{category_id}")


def edit_category(category_id: int) -> Locator:
    return role("link", f"Edit category {category_id}")


def archive_category(category_id: int) -> Locator:
    return role("link", f"Archive category {category_id}")


def user_row(user_id: int) -> Locator:
    return by_id(f"user-row-{user_id}")


def remove_user(name: str) -> Locator:
    return role("button", f"Remove {name}")


def reset_user(name: str) -> Locator:
    return role("button", f"Reset password for {name}")


def passkey_remove(name: str) -> Locator:
    return role("button", f"Remove passkey {name}")


# --- T-UT08b: category form, FX tab, preferences, toast undo ----------------
form_name = category_name.inside(category_form)
form_income = category_income.inside(category_form)
form_expense = category_expense.inside(category_form)
form_create = role("button", "Create category").inside(category_form)
edit_form_save = role("button", "Save").inside(by_id("cat-form-slot"))
edit_form_name = label("Name").inside(by_id("cat-form-slot"))
fx_table = role("table", "Cached FX rates")


def fx_row(pair: str) -> Locator:
    """A cached-rate row by its ``EUR → PLN`` pair text."""
    return role("row", pair).inside(fx_table)


pref_terms = role("term")
pref_values = role("definition")
prefs_panel_heading = role("heading", "Preferences", level=3)
