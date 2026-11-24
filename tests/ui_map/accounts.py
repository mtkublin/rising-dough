"""Accounts surface on the handoff markup (``pages/accounts.html``, T-UR08)."""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, by_testid, label, role

# The hero label: "net worth · N accounts" on desktop, "net worth" on phone.
heading = role("heading", "net worth", level=1)
new_account_button = role("link", "+ new account")
new_account_cta = role("link", "[ new account ]")  # empty state call to action
planned_total = by_id("accounts-planned-total")

credit_utilisation = by_testid("credit-utilisation")
any_row = by_id("account-", prefix=True)
table = role("table", "Accounts and balances")


def row(account_id: int) -> Locator:
    return by_id(f"account-{account_id}")


def reconcile_button(account_id: int) -> Locator:
    return role("link", "reconcile", exact=True).inside(row(account_id))


def row_menu(account_id: int) -> Locator:
    return role("button", "Row menu").inside(row(account_id))


def snapshot_button(account_id: int) -> Locator:
    return role("button", f"Snapshot account {account_id}")


# --- create / edit form (slide-over); UR08b rewrites these with the dialogs ---
create_account = role("button", "Create account")
account_form = by_id("account-form")  # create form only; edit form has no id
form_name = label("Name")
form_currency = label("Currency")
form_credit_limit = label("Credit limit")
form_errors = role("alert")

# --- reconcile dialog (UR08b) ---
reconcile_dialog = role("dialog")
reconcile_actual = label("Your bank says")
reconcile_available = label("Available")
reconcile_available_help = by_id("rec-available-help")

# --- last-checked fragment ---
last_checked_row = role("listitem")

# --- snapshot fragment (bare list item) ---
snapshot_item = role("listitem")

reconcile_record = role("button", "Record").inside(reconcile_dialog)
