"""Accounts surface."""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, label, role

heading = role("heading", "Net worth", level=1)
create_account = role("button", "Create account")
new_account_button = role("button", "New account")
planned_total = by_id("accounts-planned-total")


def row(account_id: int) -> Locator:
    return by_id(f"account-{account_id}")


def snapshot_button(account_id: int) -> Locator:
    return role("button", f"Snapshot account {account_id}")


# --- create / edit form (slide-over) ---
account_form = by_id("account-form")  # create form only; edit form has no id
form_name = label("Name")
form_currency = label("Currency")
form_credit_limit = label("Credit limit")
form_errors = role("alert")

# --- reconcile dialog ---
reconcile_dialog = role("dialog")
reconcile_actual = label("Your bank says")
reconcile_available = label("Available")
reconcile_available_help = by_id("rec-available-help")

# --- last-checked fragment ---
last_checked_row = role("listitem")

# --- snapshot fragment (bare list item) ---
snapshot_item = role("listitem")


# --- T-UT08b: reconcile + create from the page -------------------------------
def reconcile_button(account_id: int) -> Locator:
    return role("button", "Reconcile").inside(row(account_id))


reconcile_record = role("button", "Record").inside(reconcile_dialog)
