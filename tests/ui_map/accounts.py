"""Accounts surface on the handoff markup (``pages/accounts.html``, T-UR08)."""

from __future__ import annotations

import re as _re

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


# --- new / edit dialogs (UR08b; handoff overlays new-account*, edit-account*) ---
new_dialog = role("dialog", "new account", exact=True)
account_form = by_id("account-form")  # the new dialog's field group; the edit dialog has none
create_account = role("button", "[ create account ]")
save_account = role("button", "[ save ]")
form_name = label("name", exact=True)
form_currency = label("currency", exact=True)
form_type = label("type", exact=True)
form_credit_limit = label("credit limit", exact=True)
form_opening_balance = label("Opening balance")
form_counts_as = role("radiogroup", "counts as")
form_liability = role("radio", "liability")
form_errors = by_id("error-summary")  # the 422 summary (the hero error is a second alert)
currency_options = by_id("iso-codes")


def edit_dialog(name: str) -> Locator:
    return role("dialog", f"edit account \u00b7 {name}", exact=True)


# --- delete: confirm, blocked (handoff overlays delete-account*) ---
def delete_dialog(name: str) -> Locator:
    return role("alertdialog", f"Delete {name}?", exact=True)


def blocked_dialog(name: str) -> Locator:
    return role("alertdialog", f"Can\u2019t delete {name}", exact=True)


delete_confirm = role("button", "delete account", exact=True)
blocked_ok = role("button", "[ ok ]", exact=True)
blocked_link = role("link", _re.compile(r"^view "))


def menu_item(label_text: str) -> Locator:
    return role("menuitem", label_text, exact=True)


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
