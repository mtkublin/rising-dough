"""E2E (T-D154): command palette actions and the promote-all-due Undo toast.

Runs under the prod CSP (see the ``page`` fixture). Pre-fix: the palette's
"New transaction" / "Shortcuts" items dispatched an event nobody handled, and
the toast JS read ``kind`` / ``undo_href`` while the server sends ``variant`` /
``undo_url`` / ``undo_payload``.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.ui_map import ledger, shell, today
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

DESC = "due-palette-item"


def _open_palette(page: Page) -> None:
    page.keyboard.press("Control+k")
    expect(to_playwright(page, shell.palette)).to_be_visible()


@pytest.mark.parametrize("route", ["/today", "/ledger"])
def test_palette_new_transaction_opens_add_slide_over(
    live_server: tuple[str, Path], page: Page, route: str
) -> None:
    base_url, _ = live_server
    page.goto(f"{base_url}{route}")
    _open_palette(page)
    to_playwright(page, shell.palette_option("New transaction")).click()
    expect(to_playwright(page, shell.palette)).not_to_be_visible()
    expect(to_playwright(page, shell.slideover)).to_be_visible()


def test_palette_shortcuts_opens_dialog(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    page.goto(f"{base_url}/today")
    _open_palette(page)
    to_playwright(page, shell.palette_option("Shortcuts")).click()
    expect(to_playwright(page, shell.shortcuts_dialog)).to_be_visible()


def test_promote_all_due_toast_offers_undo(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "0.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories", form={"name": "Rent", "direction": "expense"}
    ).ok
    account_id = db_probe.account_id(db_path, "Checking")
    category_id = db_probe.category_id(db_path, "Rent")
    resp = page.request.post(
        f"{base_url}/planned",
        form={
            "operation_date": dt.date.today().isoformat(),  # noqa: DTZ011
            "category_id": str(category_id),
            "account_id": str(account_id),
            "amount": "42.00",
            "description": DESC,
        },
    )
    assert resp.ok, resp.text()
    planned_row = today.upcoming_planned(db_probe.planned_id(db_path, DESC))

    page.on("dialog", lambda d: d.accept())
    page.goto(f"{base_url}/today")
    expect(to_playwright(page, planned_row)).to_be_visible()

    to_playwright(page, today.promote_all_due).click()
    toast_undo = to_playwright(page, shell.undo_button)
    expect(toast_undo).to_have_count(1)
    expect(to_playwright(page, planned_row)).to_have_count(0)
    assert db_probe.txn_amounts(db_path, DESC) == [4200]

    toast_undo.click()
    expect(to_playwright(page, planned_row)).to_be_visible()
    assert db_probe.txn_amounts(db_path, DESC) == []
    page.goto(f"{base_url}/ledger?view=actual")
    expect(to_playwright(page, ledger.table_container)).not_to_contain_text(DESC)
