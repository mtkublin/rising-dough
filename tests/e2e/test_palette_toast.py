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

from tests.e2e.conftest import strip_id_prefix

pytestmark = pytest.mark.e2e

DESC = "due-palette-item"


def _open_palette(page: Page) -> None:
    page.keyboard.press("Control+k")
    expect(page.locator("#command-palette")).to_be_visible()


@pytest.mark.parametrize("route", ["/today", "/ledger"])
def test_palette_new_transaction_opens_add_slide_over(
    live_server: tuple[str, Path], page: Page, route: str
) -> None:
    base_url, _ = live_server
    page.goto(f"{base_url}{route}")
    _open_palette(page)
    page.locator("#command-palette .palette-item[data-action='new']").click()
    expect(page.locator("#command-palette")).not_to_be_visible()
    expect(page.locator("#modal-root .slide-over-root")).to_be_visible()


def test_palette_shortcuts_opens_dialog(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    page.goto(f"{base_url}/today")
    _open_palette(page)
    page.locator("#command-palette .palette-item[data-action='shortcuts']").click()
    expect(page.locator("#shortcuts-dialog")).to_be_visible()


def test_promote_all_due_toast_offers_undo(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "0.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories", form={"name": "Rent", "direction": "expense"}
    ).ok
    page.goto(f"{base_url}/accounts")
    account_id = strip_id_prefix(
        page.locator("tr[id^='account-']").first.get_attribute("id"), "account-"
    )
    page.goto(f"{base_url}/categories")
    category_id = strip_id_prefix(
        page.locator("[id^='category-']", has_text="Rent").first.get_attribute("id"),
        "category-",
    )
    resp = page.request.post(
        f"{base_url}/planned",
        form={
            "operation_date": dt.date.today().isoformat(),  # noqa: DTZ011
            "category_id": category_id,
            "account_id": account_id,
            "amount": "42.00",
            "description": DESC,
        },
    )
    assert resp.ok, resp.text()

    page.on("dialog", lambda d: d.accept())
    page.goto(f"{base_url}/today")
    upcoming = page.locator("#upcoming-root")
    expect(upcoming.get_by_text(DESC)).to_be_visible()

    page.get_by_role("button", name="Promote all due").click()
    toast = page.locator("#toast-root .rd-toast")
    expect(toast).to_have_class("rd-toast rd-toast--success")
    undo = toast.locator(".rd-toast__undo")
    expect(undo).to_have_count(1)
    expect(upcoming.get_by_text(DESC)).to_have_count(0)

    undo.click()
    expect(upcoming.get_by_text(DESC)).to_be_visible()
    page.goto(f"{base_url}/ledger?view=actual")
    expect(page.get_by_text(DESC)).to_have_count(0)
