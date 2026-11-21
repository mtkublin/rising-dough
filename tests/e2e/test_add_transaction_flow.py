"""E2E: create account → add transaction → see balance update."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.ui_map import accounts
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e


def test_add_transaction_updates_account_balance(
    live_server: tuple[str, Path],
    page: Page,
) -> None:
    base_url, db_path = live_server

    # 1. Create a Checking account with opening_balance 100.00 PLN.
    create_resp = page.request.post(
        f"{base_url}/accounts",
        form={
            "name": "Checking",
            "currency": "PLN",
            "opening_balance": "100.00",
        },
    )
    assert create_resp.ok, create_resp.text()

    # 2. Create an expense category "Groceries".
    cat_resp = page.request.post(
        f"{base_url}/categories",
        form={"name": "Groceries", "direction": "expense"},
    )
    assert cat_resp.ok, cat_resp.text()

    # 3. Look the created ids up in the scratch DB.
    account_id = db_probe.account_id(db_path, "Checking")
    category_id = db_probe.category_id(db_path, "Groceries")
    page.goto(f"{base_url}/accounts")
    checking = to_playwright(page, accounts.row(account_id))
    expect(checking).to_contain_text("Checking")
    # Opening balance renders as "100.00 zł".
    expect(checking).to_contain_text("100.00")

    # 4. Post a 20.00 expense transaction.
    txn_resp = page.request.post(
        f"{base_url}/transactions",
        form={
            "operation_date": "2026-01-15",
            "category_id": str(category_id),
            "account_id": str(account_id),
            "amount": "20.00",
            "description": "milk",
        },
    )
    assert txn_resp.ok, txn_resp.text()
    assert db_probe.txn_amounts(db_path, "milk") == [2000]

    # 5. Confirm balance on /accounts flipped to 80.00.
    page.goto(f"{base_url}/accounts")
    checking_card = to_playwright(page, accounts.row(account_id))
    expect(checking_card).to_contain_text("Checking")
    expect(checking_card).to_contain_text("80.00")
