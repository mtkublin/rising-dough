"""E2E: phone layout at 375px (T-UR61 R10, T-UR62 R11, T-UR63 R12).

Inputs render at >= 16px so mobile browsers do not auto-zoom on focus, the ledger filter
from/to fields neither overlap nor leave the viewport, and the repeats formula component keeps
its category control inside the dialog.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, ViewportSize, expect

from tests.e2e import db_probe
from tests.ui_map import entries, rd_shell
from tests.ui_map.locator import by_id, role, to_playwright

pytestmark = pytest.mark.e2e

PHONE: ViewportSize = {"width": 375, "height": 812}
MIN_FONT_PX = 16
FILTERS_TOGGLE = role("button", "filters", exact=True)
FILTERS_EXTRA = by_id("f-extra")
FILTER_FROM = by_id("f-from")
FILTER_TO = by_id("f-to")

# Visible text-like controls under ``root`` whose computed font size is below the minimum.
_SMALL_FIELDS_JS = """
([rootSel, min]) => {
  const root = rootSel ? document.querySelector(rootSel) : document;
  const skip = new Set(['hidden', 'checkbox', 'radio', 'submit', 'button', 'file', 'range']);
  return [...root.querySelectorAll('input, select, textarea')]
    .filter((el) => !skip.has(el.type) && el.getClientRects().length > 0)
    .map((el) => ({
      id: el.id || el.name || el.className,
      px: parseFloat(getComputedStyle(el).fontSize),
    }))
    .filter((f) => f.px < min);
}
"""

# Visible controls under ``root`` that leave the root or the viewport, or overlap each other.
_LAYOUT_PROBLEMS_JS = """
(rootSel) => {
  const root = document.querySelector(rootSel);
  const rr = root.getBoundingClientRect();
  const sel = 'input:not([type=radio]), select, button, .rd-segmented, .rd-comp__of';
  const boxes = [...root.querySelectorAll(sel)]
    .filter((el) => el.getClientRects().length > 0 && !el.closest('[hidden]'))
    .map((el) => ({ name: el.id || el.name || el.className || el.tagName,
                    r: el.getBoundingClientRect() }));
  const out = [];
  for (const b of boxes) {
    if (b.r.left < rr.left - 1 || b.r.right > rr.right + 1 || b.r.left < 0
        || b.r.right > window.innerWidth) out.push('outside ' + b.name);
  }
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i].r, c = boxes[j].r;
      if (a.left < c.right - 1 && c.left < a.right - 1 && a.top < c.bottom - 1
          && c.top < a.bottom - 1) out.push('overlap ' + boxes[i].name + ' / ' + boxes[j].name);
    }
  }
  return out;
}
"""

# Visible select / text / date controls under ``root`` whose shown text (selected option, value,
# or placeholder) is wider than the content box. A date adds the native picker icon (24px).
_CLIPPED_VALUES_JS = """
(rootSel) => {
  const root = document.querySelector(rootSel);
  const ctx = document.createElement('canvas').getContext('2d');
  const out = [];
  for (const el of root.querySelectorAll('input, select')) {
    if (el.getClientRects().length === 0 || el.closest('[hidden]')) continue;
    if (['hidden', 'checkbox', 'radio', 'submit', 'button'].includes(el.type)) continue;
    const cs = getComputedStyle(el);
    ctx.font = cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
    let text = el.placeholder || '';
    if (el.tagName === 'SELECT') text = el.selectedOptions[0] ? el.selectedOptions[0].text : '';
    else if (el.type === 'date') text = el.value ? '26/11/2026' : 'dd/mm/yyyy';
    else if (el.value) text = el.value;
    const icon = el.type === 'date' ? 24 : 0;
    const avail = el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    const need = ctx.measureText(text).width + icon;
    if (need > avail + 0.5 || el.scrollWidth > el.clientWidth) {
      out.push((el.id || el.name || el.className) + ' needs ' + Math.round(need)
               + ' has ' + Math.round(avail));
    }
  }
  return out;
}
"""


def _clipped(page: Page, root: str) -> list[str]:
    result: list[str] = page.evaluate(_CLIPPED_VALUES_JS, root)
    return result


def _small(page: Page, root: str | None = None) -> list[dict[str, object]]:
    result: list[dict[str, object]] = page.evaluate(_SMALL_FIELDS_JS, [root, MIN_FONT_PX])
    return result


def open_new_entry(page: Page) -> None:
    """Open the new-entry dialog from the phone tab bar."""
    to_playwright(page, rd_shell.tabbar_new_entry).click()
    expect(to_playwright(page, entries.dialog)).to_be_visible()


def _seed(base_url: str, db_path: Path, page: Page) -> None:
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "0.00"},
    ).ok
    for name, direction in (("Salary", "income"), ("Savings", "expense")):
        assert page.request.post(
            f"{base_url}/categories", form={"name": name, "direction": direction}
        ).ok
    assert db_probe.account_id(db_path, "Checking")


def test_today_and_ledger_inputs_are_16px_and_filters_fit(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    page.set_viewport_size(PHONE)
    page.goto(f"{base_url}/today")
    assert _small(page) == []
    page.goto(f"{base_url}/ledger")
    page.wait_for_function("typeof window.htmx === 'object'")
    to_playwright(page, FILTERS_TOGGLE).click()
    expect(to_playwright(page, FILTERS_EXTRA)).to_be_visible()
    assert _small(page) == []
    assert page.evaluate(_LAYOUT_PROBLEMS_JS, "#f-extra") == []
    to_playwright(page, FILTER_FROM).fill("2026-11-26")
    to_playwright(page, FILTER_TO).fill("2026-11-27")
    assert _clipped(page, "#f-extra") == []
    from_box = to_playwright(page, FILTER_FROM).bounding_box()
    to_box = to_playwright(page, FILTER_TO).bounding_box()
    assert from_box is not None
    assert to_box is not None
    assert from_box["x"] >= 0
    assert to_box["x"] + to_box["width"] <= PHONE["width"]
    # side by side or stacked, never overlapping
    assert from_box["x"] + from_box["width"] <= to_box["x"] + 1 or (
        from_box["y"] + from_box["height"] <= to_box["y"] + 1
    )


@pytest.mark.parametrize("tab", ["happened", "planned", "repeats"])
def test_new_entry_tabs_inputs_are_16px(
    live_server: tuple[str, Path], page: Page, tab: str
) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Credit Card Platinum", "currency": "PLN", "opening_balance": "0.00"},
    ).ok
    page.set_viewport_size(PHONE)
    page.goto(f"{base_url}/today")
    page.wait_for_function("typeof window.htmx === 'object'")
    open_new_entry(page)
    if tab != "happened":
        link = to_playwright(page, getattr(entries, f"tab_{tab}"))
        link.click()
        expect(link).to_have_attribute("aria-current", "page")
    assert _small(page, "dialog") == []
    to_playwright(page, entries.field_account).select_option(label="Credit Card Platinum")
    assert _clipped(page, "dialog") == []


def test_repeats_formula_component_fits_the_phone(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    page.set_viewport_size(PHONE)
    page.goto(f"{base_url}/today")
    page.wait_for_function("typeof window.htmx === 'object'")
    open_new_entry(page)
    to_playwright(page, entries.tab_repeats).click()
    to_playwright(page, entries.amount_formula).evaluate("el => el.click()")
    expect(to_playwright(page, entries.formula_group)).to_be_visible()
    assert _small(page, "dialog") == []
    assert page.evaluate(_LAYOUT_PROBLEMS_JS, "fieldset.rd-comp") == []
    # the category control keeps a usable width
    trigger = to_playwright(page, entries.formula_pick).first.bounding_box()
    assert trigger is not None
    assert trigger["width"] >= 120
