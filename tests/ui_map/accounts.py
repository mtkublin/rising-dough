"""Accounts surface."""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, role

heading = role("heading", "Net worth", level=1)
create_account = role("button", "Create account")


def row(account_id: int) -> Locator:
    return by_id(f"account-{account_id}")


def snapshot_button(account_id: int) -> Locator:
    return role("button", f"Snapshot account {account_id}")
