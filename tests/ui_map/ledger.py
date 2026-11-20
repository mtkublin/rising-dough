"""Ledger surface: actual, planned and recurring views."""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, label, role

heading = role("heading", level=1)
table = by_id("txn-table")
form = by_id("txn-form")
form_slot = by_id("txn-form-slot")
pagination = role("navigation", "Pagination")
search = label("Search")
add_entry = role("button", "Add entry")
save = role("button", "Save")
promote = role("button", "Promote")
recently_deleted_heading = role("heading", "Recently deleted", level=1)


def row(tx_id: int) -> Locator:
    return by_id(f"txn-{tx_id}")


def planned_row(planned_id: int) -> Locator:
    return by_id(f"planned-p-{planned_id}")


def recurring_row(rule_id: int) -> Locator:
    return by_id(f"recurring-{rule_id}")


def row_menu(tx_id: int) -> Locator:
    """The 'Row actions' menu trigger inside a transaction row."""
    return role("button", "Row actions").inside(row(tx_id))


def skip_next(rule_id: int) -> Locator:
    return role("button", f"Skip next occurrence of rule {rule_id}")
