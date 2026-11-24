"""Accounts surface against the handoff markup (``pages/accounts.html``).

Same names as ``tests.ui_map.accounts``. The handoff has fixed sample rows and
no row ids, so the id-parameterised builders return a sample row.
"""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, label, role

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
        "create_account",
        "account_form",
        "form_name",
        "form_currency",
        "form_credit_limit",
        "form_errors",
        "reconcile_dialog",
        "reconcile_actual",
        "reconcile_available",
        "reconcile_available_help",
        "last_checked_row",
        "snapshot_item",
        "reconcile_record",
        "new_account_cta",
    }
)
planned_total = by_id("accounts-planned-total")


def snapshot_button(account_id: int) -> Locator:
    return role("button", f"Snapshot account {account_id}")


create_account = role("button", "Create account")
account_form = by_id("account-form")
form_name = label("Name")
form_currency = label("Currency")
form_credit_limit = label("Credit limit")
form_errors = role("alert")
reconcile_dialog = role("dialog")
reconcile_actual = label("Your bank says")
reconcile_available = label("Available")
reconcile_available_help = by_id("rec-available-help")
last_checked_row = role("listitem")
snapshot_item = role("listitem")
reconcile_record = role("button", "Record").inside(reconcile_dialog)
