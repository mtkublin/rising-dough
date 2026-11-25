"""Accounts surface against the handoff markup (``pages/accounts.html``).

Same names as ``tests.ui_map.accounts``. The handoff has fixed sample rows and
no row ids, so the id-parameterised builders return a sample row.
"""

from __future__ import annotations

from tests.ui_map import accounts as _app
from tests.ui_map.locator import Locator, by_id, role

heading = role("heading", "net worth", level=1)
new_account_button = role("link", "+ new account")
new_account_cta = role("link", "[ new account ]")  # on ``accounts--empty.html``
table = role("table", "Accounts and balances")

_SAMPLE_ROW = "Investments A"  # first sample account (an asset)
_SAMPLE_CARD = "Credit Card"  # the liability with a credit limit
any_row = role("row", _SAMPLE_ROW).inside(table)
# The handoff's credit line is a ``role="img"`` bar inside the credit-card row.
credit_utilisation = role("img", "percent spent").inside(role("row", _SAMPLE_CARD))


def row(account_id: int) -> Locator:
    return role("row", _SAMPLE_ROW).inside(table)


def reconcile_button(account_id: int) -> Locator:
    return role("link", "reconcile", exact=True).inside(row(account_id))


def row_menu(account_id: int) -> Locator:
    return role("button", "Row menu").inside(row(account_id))


# Names the handoff accounts page does not render (dialogs live on the overlay pages,
# UR08b; the planned total is a hero sentence with no id) keep the app locator so
# ``surface("accounts", "mockup")`` stays total; the resolve test skips them.
NO_HANDOFF_TWIN = frozenset(
    {
        "planned_total",
        "snapshot_button",
        "new_dialog",
        "account_form",
        "create_account",
        "save_account",
        "form_name",
        "form_currency",
        "form_type",
        "form_credit_limit",
        "form_opening_balance",
        "form_counts_as",
        "form_liability",
        "form_name_error",
        "currency_options",
        "edit_dialog",
        "delete_dialog",
        "blocked_dialog",
        "delete_confirm",
        "blocked_ok",
        "blocked_link",
        "menu_item",
        "reconcile_dialog",
        "reconcile_actual",
        "reconcile_available",
        "reconcile_available_help",
        "last_checked_row",
        "snapshot_item",
        "reconcile_record",
        "reconcile_difference",
        "reconcile_preview",
        "reconcile_snapshot_option",
        "new_account_cta",
    }
)
planned_total = by_id("accounts-planned-total")


def snapshot_button(account_id: int) -> Locator:
    return role("button", f"Snapshot account {account_id}")


# The dialogs are the same markup in the app and the handoff (the overlay pages), so the
# twins are the app locators; ``test_mockup_account_dialogs`` resolves each on its overlay page.
new_dialog = _app.new_dialog
account_form = _app.account_form
create_account = _app.create_account
save_account = _app.save_account
form_name = _app.form_name
form_currency = _app.form_currency
form_type = _app.form_type
form_credit_limit = _app.form_credit_limit
form_opening_balance = _app.form_opening_balance
form_counts_as = _app.form_counts_as
form_liability = _app.form_liability
form_name_error = _app.form_name_error
currency_options = _app.currency_options


def edit_dialog(name: str) -> Locator:
    return _app.edit_dialog(name)


def delete_dialog(name: str) -> Locator:
    return _app.delete_dialog(name)


def blocked_dialog(name: str) -> Locator:
    return _app.blocked_dialog(name)


delete_confirm = _app.delete_confirm
blocked_ok = _app.blocked_ok
blocked_link = _app.blocked_link


def menu_item(label_text: str) -> Locator:
    return _app.menu_item(label_text)


reconcile_dialog = _app.reconcile_dialog
reconcile_actual = _app.reconcile_actual
reconcile_available = _app.reconcile_available
reconcile_available_help = _app.reconcile_available_help
reconcile_difference = _app.reconcile_difference
reconcile_preview = _app.reconcile_preview
reconcile_snapshot_option = _app.reconcile_snapshot_option
last_checked_row = role("listitem")
snapshot_item = role("listitem")
reconcile_record = _app.reconcile_record
