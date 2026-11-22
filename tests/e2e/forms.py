"""Shared helpers for e2e tests that drive the real slide-over forms (T-Q248, T-Q278).

Everything goes through the UI map (ADR-0106 section 2); no CSS selectors.
"""

from __future__ import annotations

from playwright.sync_api import Page

from tests.e2e.ui_actions import open_add_slide_over, pick
from tests.ui_map import ledger, shell
from tests.ui_map.locator import to_playwright

PANEL = shell.slideover


def wait_for_htmx(page: Page) -> None:
    """Block until htmx has loaded, so a click is not swallowed before it binds."""
    page.wait_for_function("typeof window.htmx === 'object'")


def add_happened(
    page: Page, *, category: str, account: str, amount: str, day: str, note: str
) -> None:
    """Open the Happened overlay on the current page and submit it."""
    wait_for_htmx(page)
    open_add_slide_over(page)
    pick(page, ledger.field_category, category)
    pick(page, ledger.field_account, account)
    to_playwright(page, ledger.overlay_field(ledger.field_amount)).fill(amount)
    to_playwright(page, ledger.overlay_field(ledger.field_date)).fill(day)
    to_playwright(page, ledger.overlay_field(ledger.field_note)).fill(note)
    with page.expect_response(
        lambda r: r.url.endswith("/transactions") and r.request.method == "POST"
    ) as resp:
        to_playwright(page, ledger.overlay_add_entry).click()
    assert resp.value.ok, resp.value.text()
