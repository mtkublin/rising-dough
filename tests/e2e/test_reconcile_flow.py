"""E2E: reconcile an account, confirm adjustment transaction created."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.e2e.forms import add_happened, wait_for_htmx
from tests.ui_map import accounts, ledger
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e


def test_reconcile_creates_adjustment_transaction(
    live_server: tuple[str, Path],
    page: Page,
) -> None:
    base_url, db_path = live_server

    # Seed account with opening 100.00; add an expense of 40.00 → derived 60.00.
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "100.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories",
        form={"name": "Food", "direction": "expense"},
    ).ok

    account_id = db_probe.account_id(db_path, "Checking")

    page.goto(f"{base_url}/ledger?view=actual")
    add_happened(
        page,
        category="Food",
        account="Checking",
        amount="40.00",
        day="2026-01-15",
        note="snack",
    )

    # Reconcile through the account row's form: bank says 70.00 -> +10.00 adjustment.
    page.goto(f"{base_url}/accounts")
    wait_for_htmx(page)
    to_playwright(page, accounts.reconcile_button(account_id)).click()
    expect(to_playwright(page, accounts.reconcile_dialog)).to_be_visible()
    to_playwright(page, accounts.reconcile_actual).fill("70.00")
    with page.expect_response(
        lambda r: r.url.endswith("/reconcile") and r.request.method == "POST"
    ) as resp:
        to_playwright(page, accounts.reconcile_record).click()
    assert resp.value.ok, resp.value.text()

    # Account card now shows 70.00.
    page.goto(f"{base_url}/accounts")
    expect(to_playwright(page, accounts.row(account_id))).to_contain_text("70.00")

    # DB: one adjustment transaction of +10.00 (direction = adjustment, signed).
    adjustments = db_probe.rows(
        db_path,
        "SELECT t.amount FROM transactions t JOIN categories c ON c.id = t.category_id"
        " WHERE c.direction = 'adjustment' AND t.deleted_at IS NULL",
    )
    assert adjustments == [(1000,)]

    # The unified ledger shows the 10.00 adjustment row.
    page.goto(f"{base_url}/ledger?view=actual")
    table = to_playwright(page, ledger.table_container)
    expect(table).to_contain_text("10.00")
    expect(table).to_contain_text("auto-reconciliation")
