"""T-D55 — after logout the back button never shows the cached ledger."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_back_button_after_logout_does_not_show_ledger(
    page: Page, live_server: tuple[str, Path]
) -> None:
    base_url, _ = live_server
    page.goto(f"{base_url}/ledger")
    expect(page).to_have_url(f"{base_url}/ledger")
    page.locator('form[action="/auth/logout"] button').first.click()
    expect(page).to_have_url(re.compile(r"/auth/login"))

    page.go_back()
    # no-store forces a refetch: the server answers with a login redirect.
    expect(page).to_have_url(re.compile(r"/auth/login"))
