# ruff: noqa: E501 - throwaway diagnostic with an inline JS recorder, never merged
"""QFIX12 DIAGNOSTIC (throwaway): deterministic note-vs-swap race scenarios (route holds)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, Route, expect

from tests.e2e.ui_actions import choose_account, choose_category
from tests.ui_map import entries, rd_shell
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

_RECORDER = """
() => {
  window.__trace = [];
  const t = () => Math.round(performance.now());
  const log = (k, d) => window.__trace.push([t(), k, d]);
  for (const ev of ['htmx:beforeRequest','htmx:beforeSwap','htmx:afterSwap','htmx:afterSettle',
                    'htmx:configRequest','htmx:abort','htmx:sendAbort','htmx:responseError']) {
    document.body.addEventListener(ev, (e) => {
      const d = e.detail || {};
      const p = d.pathInfo ? d.pathInfo.requestPath : (d.requestConfig ? d.requestConfig.path : '');
      const tg = d.target || e.target;
      log(ev, {path: p, target: tg && (tg.id || tg.className), elt: e.target && (e.target.id || e.target.tagName)});
    }, true);
  }
  document.addEventListener('input', (e) => {
    if (e.target && e.target.name) log('input', {name: e.target.name, value: e.target.value});
  }, true);
  document.addEventListener('focusin', (e) => {
    log('focusin', {id: e.target.id || e.target.name || e.target.tagName});
  }, true);
  const hasNote = (n) => !!(n.querySelector && n.querySelector('[name=description]')) || n.name === 'description';
  new MutationObserver((recs) => {
    for (const r of recs) {
      for (const n of r.removedNodes) {
        if (n.nodeType === 1) log('removed', {node: (n.id || n.className || n.tagName), hasNote: hasNote(n), parent: r.target.id || r.target.className});
      }
      for (const n of r.addedNodes) {
        if (n.nodeType === 1) log('added', {node: (n.id || n.className || n.tagName), hasNote: hasNote(n), parent: r.target.id || r.target.className});
      }
    }
  }).observe(document.body, {childList: true, subtree: true});
}
"""


class Hold:
    """Hold matching requests (route.continue_ is called later from the test body)."""

    def __init__(self, page: Page, match: Any) -> None:
        self.held: list[Route] = []
        self.on = True
        self.match = match
        page.route(lambda url: bool(match(url)), self._handle)

    def _handle(self, route: Route) -> None:
        if self.on:
            self.held.append(route)
        else:
            route.continue_()

    def release(self) -> int:
        self.on = False
        n = len(self.held)
        for r in self.held:
            r.continue_()
        self.held.clear()
        return n


def _is_tab(url: str) -> bool:
    return "/add?" in url and "hero=1" not in url and "when=planned" in url


def _is_hero(url: str) -> bool:
    return "/add?" in url and "hero=1" in url


def _setup(base_url: str, page: Page) -> list[str]:
    consoles: list[str] = []
    page.on("console", lambda m: consoles.append(m.text))
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "500.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories", form={"name": "Groceries", "direction": "expense"}
    ).ok
    page.goto(f"{base_url}/today")
    page.evaluate(_RECORDER)
    to_playwright(page, rd_shell.new_entry).click()
    expect(to_playwright(page, entries.dialog)).to_be_visible()
    return consoles


def _dump(page: Page, what: str, reads: Any, consoles: list[str]) -> str:
    return (
        "DIAG "
        + what
        + " "
        + json.dumps(
            {
                "reads": reads,
                "trace": page.evaluate("() => window.__trace || []"),
                "console": consoles,
                "dialog_html": to_playwright(page, entries.dialog).evaluate("el => el.outerHTML"),
            },
            default=str,
        )
    )


def _reads(page: Page, note: Any, times: tuple[int, ...] = (0, 50, 200, 500, 1500)) -> list[Any]:
    out: list[Any] = []
    for t in times:
        page.wait_for_timeout(t)
        out.append((t, note.input_value()))
    return out


def test_a_fill_while_tab_swap_held(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    consoles = _setup(base_url, page)
    hold = Hold(page, _is_tab)
    to_playwright(page, entries.tab_planned).click()
    page.wait_for_timeout(300)
    note = to_playwright(page, entries.field_note)
    note.fill("typed-a")
    page.wait_for_timeout(100)
    released = hold.release()
    expect(to_playwright(page, entries.tab_planned)).to_have_attribute("aria-current", "page")
    reads = _reads(page, note)
    assert released == 1
    assert all(v == "typed-a" for _, v in reads), _dump(page, "A", reads, consoles)


def test_b_fill_immediately_after_swap(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    consoles = _setup(base_url, page)
    to_playwright(page, entries.tab_planned).click()
    expect(to_playwright(page, entries.tab_planned)).to_have_attribute("aria-current", "page")
    note = to_playwright(page, entries.field_note)
    note.fill("typed-b")
    reads = _reads(page, note)
    assert all(v == "typed-b" for _, v in reads), _dump(page, "B", reads, consoles)


def test_b2_fill_right_after_click_no_wait(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    consoles = _setup(base_url, page)
    to_playwright(page, entries.tab_planned).click()
    note = to_playwright(page, entries.field_note)
    note.fill("typed-b2")
    expect(to_playwright(page, entries.tab_planned)).to_have_attribute("aria-current", "page")
    reads = _reads(page, note)
    assert all(v == "typed-b2" for _, v in reads), _dump(page, "B2", reads, consoles)


def test_c_fill_while_hero_held(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    consoles = _setup(base_url, page)
    to_playwright(page, entries.tab_planned).click()
    expect(to_playwright(page, entries.tab_planned)).to_have_attribute("aria-current", "page")
    hold = Hold(page, _is_hero)
    to_playwright(page, entries.category_search).click()
    query = to_playwright(page, entries.category_query)
    query.fill("Groceries")
    query.press("Enter")
    page.wait_for_timeout(300)
    note = to_playwright(page, entries.field_note)
    note.fill("typed-c")
    page.wait_for_timeout(100)
    released = hold.release()
    page.wait_for_timeout(300)
    reads = _reads(page, note)
    assert released >= 1
    assert all(v == "typed-c" for _, v in reads), _dump(page, "C", reads, consoles)


@pytest.mark.parametrize("order", ["tab_first", "hero_first"])
def test_d_both_held(live_server: tuple[str, Path], page: Page, order: str) -> None:
    base_url, _ = live_server
    consoles = _setup(base_url, page)
    choose_category(page, "Groceries")
    choose_account(page, "Checking")
    tab_hold = Hold(page, _is_tab)
    hero_hold = Hold(page, _is_hero)
    to_playwright(page, entries.tab_planned).click()
    page.wait_for_timeout(200)
    note = to_playwright(page, entries.field_note)
    note.fill("typed-d")
    to_playwright(page, entries.field_account.inside(entries.dialog)).select_option(index=0)
    first, second = (tab_hold, hero_hold) if order == "tab_first" else (hero_hold, tab_hold)
    first.release()
    page.wait_for_timeout(200)
    second.release()
    page.wait_for_timeout(500)
    note = to_playwright(page, entries.field_note)
    reads = _reads(page, note)
    assert all(v == "typed-d" for _, v in reads), _dump(page, "D-" + order, reads, consoles)
