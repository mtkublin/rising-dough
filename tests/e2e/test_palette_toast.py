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
from tests.ui_map import entries, ledger, rd_shell, shell, today
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

DESC = "due-palette-item"


def _open_palette(page: Page) -> None:
    page.keyboard.press("Control+k")
    expect(to_playwright(page, rd_shell.palette_dialog)).to_be_visible()


def test_palette_new_entry_opens_the_new_entry_dialog(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _ = live_server
    page.goto(f"{base_url}/dev/components")
    _open_palette(page)
    to_playwright(page, rd_shell.palette_option("New entry")).click()
    expect(to_playwright(page, rd_shell.palette_dialog)).not_to_be_visible()
    expect(to_playwright(page, entries.dialog)).to_be_visible()


def test_palette_shortcuts_opens_dialog(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    page.goto(f"{base_url}/dev/components")
    _open_palette(page)
    to_playwright(page, rd_shell.palette_option("Shortcuts")).click()
    expect(to_playwright(page, rd_shell.shortcuts_dialog)).to_be_visible()


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

    # A successful undo reloads the page once its region refreshes finish (T-Q317): wait for that
    # reload so it cannot interrupt the navigation below.
    with page.expect_event("load"):
        toast_undo.click()
    expect(to_playwright(page, planned_row)).to_be_visible()
    assert db_probe.txn_amounts(db_path, DESC) == []
    page.goto(f"{base_url}/ledger?view=actual")
    expect(to_playwright(page, ledger.table_container)).not_to_contain_text(DESC)


@pytest.mark.parametrize("opener", ["button", "key", "palette"])
def test_new_entry_opens_in_place_on_the_ledger(
    live_server: tuple[str, Path], page: Page, opener: str
) -> None:
    base_url, _ = live_server
    page.goto(f"{base_url}/ledger?view=planned")
    if opener == "button":
        to_playwright(page, rd_shell.new_entry).click()
    elif opener == "key":
        page.keyboard.press("n")
    else:
        _open_palette(page)
        to_playwright(page, rd_shell.palette_option("New entry")).click()
    expect(to_playwright(page, entries.dialog)).to_be_visible()
    assert page.url == f"{base_url}/ledger?view=planned"


def test_phone_tabbar_plus_opens_in_place(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    page.set_viewport_size({"width": 375, "height": 800})
    page.goto(f"{base_url}/ledger")
    to_playwright(page, rd_shell.tabbar_new_entry).click()
    expect(to_playwright(page, entries.dialog)).to_be_visible()
    assert page.url == f"{base_url}/ledger"


_OVERFLOW_JS = """() => [...document.querySelectorAll('body *')].filter((el) => {
  const r = el.getBoundingClientRect();
  if (r.width === 0 || r.right <= innerWidth) return false;
  for (let p = el.parentElement; p; p = p.parentElement) {
    const o = getComputedStyle(p).overflowX;
    if (o === 'auto' || o === 'scroll' || o === 'hidden' || o === 'clip') return false;
  }
  return true;
}).map((el) => el.tagName + '.' + el.className)"""


def test_no_horizontal_overflow_at_375_on_today_and_the_dialog(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _ = live_server
    page.set_viewport_size({"width": 375, "height": 800})
    page.goto(f"{base_url}/today")
    assert page.evaluate("document.documentElement.scrollWidth") == 375
    assert page.evaluate(_OVERFLOW_JS) == []
    to_playwright(page, rd_shell.tabbar_new_entry).click()
    expect(to_playwright(page, entries.dialog)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth") == 375
    assert page.evaluate(_OVERFLOW_JS) == []


_ACTIONS_CLIPPED_JS = """() => {
  const wrap = document.querySelector('.rd-table-scroll');
  const right = wrap.getBoundingClientRect().right;
  const cells = [...document.querySelectorAll('tbody td.rd-row__actions')];
  const clipped = cells.flatMap((td) => [td, ...td.querySelectorAll('a, button')])
    .filter((el) => el.getBoundingClientRect().right > right + 0.5).length;
  return { cells: cells.length, clipped, scrolls: wrap.scrollWidth > wrap.clientWidth };
}"""


def test_schedule_actions_cells_fully_visible_at_1024(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "0.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories", form={"name": "Rent", "direction": "expense"}
    ).ok
    common = {
        "category_id": str(db_probe.category_id(db_path, "Rent")),
        "account_id": str(db_probe.account_id(db_path, "Checking")),
    }
    assert page.request.post(
        f"{base_url}/planned",
        form={**common, "operation_date": "2030-01-20", "amount": "25.00", "description": "p1"},
    ).ok
    assert page.request.post(
        f"{base_url}/recurring",
        form={
            **common,
            "cadence": "monthly",
            "start_date": "2030-01-15",
            "default_amount": "50.00",
            "default_description": "r1",
        },
    ).ok
    page.set_viewport_size({"width": 1024, "height": 768})
    for view in ("planned", "recurring"):
        page.goto(f"{base_url}/ledger?view={view}&date_from=2030-01-01&date_to=2030-12-31")
        probe = page.evaluate(_ACTIONS_CLIPPED_JS)
        assert probe == {"cells": 1, "clipped": 0, "scrolls": False}, view
