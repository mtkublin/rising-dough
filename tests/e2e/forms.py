"""Shared helpers for e2e tests that drive the real entry forms (T-Q248, T-Q278, T-UR09).

Everything goes through the UI map (ADR-0106 section 2); no CSS selectors.
"""

from __future__ import annotations

from playwright.sync_api import Page

from tests.e2e.ui_actions import choose_account, choose_category, open_new_entry
from tests.ui_map import entries, shell
from tests.ui_map.locator import to_playwright

PANEL = shell.slideover


def wait_for_htmx(page: Page) -> None:
    """Block until htmx has loaded, so a click is not swallowed before it binds."""
    page.wait_for_function("typeof window.htmx === 'object'")


def add_happened(
    page: Page, *, category: str, account: str, amount: str, day: str, note: str
) -> None:
    """Open the new-entry dialog (happened tab) on the current new-shell page and submit it."""
    wait_for_htmx(page)
    open_new_entry(page)
    choose_category(page, category)
    choose_account(page, account)
    to_playwright(page, entries.hero_amount).fill(amount)
    to_playwright(page, entries.field_date.inside(entries.dialog)).fill(day)
    to_playwright(page, entries.field_note.inside(entries.dialog)).fill(note)
    with page.expect_response(
        lambda r: r.url.endswith("/transactions") and r.request.method == "POST"
    ) as resp:
        to_playwright(page, entries.save).click()
    assert resp.value.ok, resp.value.text()
