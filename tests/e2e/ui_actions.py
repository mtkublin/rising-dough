"""Small UI-map-driven actions shared by the e2e journeys (ADR-0106 section 2)."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import expect

from tests.ui_map import ledger, shell
from tests.ui_map.locator import Locator, to_playwright


def pick(page: Any, field: Locator, option: str, *, scope: Locator = shell.slideover) -> None:
    """Choose ``option`` in the combobox behind the labelled ``field`` (inside ``scope``)."""
    to_playwright(page, field.inside(scope)).click()
    to_playwright(page, ledger.combobox_option(option).inside(scope)).click()


def open_add_slide_over(page: Any) -> None:
    """Open the New entry slide-over from the top bar and wait for it."""
    assert page.evaluate("typeof window.htmx") == "object"
    to_playwright(page, shell.add_button).first.click()
    expect(to_playwright(page, shell.slideover)).to_be_visible()
