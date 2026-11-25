# ruff: noqa: E501, PLR0915 - throwaway diagnostic with an inline JS recorder, never merged
"""QFIX11 DIAGNOSTIC (throwaway): planned-from-Today note stress with an event trace."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.e2e.ui_actions import choose_account, choose_category, save_entry
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


@pytest.mark.parametrize("i", range(int(os.environ.get("DIAG_N", "100"))))
def test_diag_planned_note_stress(live_server: tuple[str, Path], page: Page, i: int) -> None:
    base_url, db_path = live_server
    if page.context.browser is not None and page.context.browser.browser_type.name != "chromium":
        pytest.skip("CDP throttling is Chromium only")
    if True:
        cdp = page.context.new_cdp_session(page)
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 8})
    steps: list[tuple[int, str]] = []
    t0 = time.monotonic()

    def mark(what: str) -> None:
        steps.append((round((time.monotonic() - t0) * 1000), what))

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
    mark("recorder installed")
    to_playwright(page, rd_shell.new_entry).click()
    expect(to_playwright(page, entries.dialog)).to_be_visible()
    mark("dialog visible")
    to_playwright(page, entries.tab_planned).click()
    expect(to_playwright(page, entries.tab_planned)).to_have_attribute("aria-current", "page")
    mark("planned tab current")
    choose_category(page, "Groceries")
    mark("category chosen")
    choose_account(page, "Checking")
    mark("account chosen")
    soon = datetime.now(tz=UTC).date() + timedelta(days=2)
    to_playwright(page, entries.field_due).fill(soon.isoformat())
    mark("due filled")
    to_playwright(page, entries.hero_amount).fill("25.00")
    mark("amount filled")
    note = to_playwright(page, entries.field_note)
    note.fill("today-planned")
    mark("note filled")
    try:
        expect(note).to_have_value("today-planned", timeout=1500)
    except AssertionError as exc:
        mark("note LOST")
        raise AssertionError(
            "DIAG LOST "
            + json.dumps(
                {
                    "iter": i,
                    "steps": steps,
                    "trace": page.evaluate("() => window.__trace || []"),
                    "console": consoles,
                    "dialog_html": to_playwright(page, entries.dialog).evaluate(
                        "el => el.outerHTML"
                    ),
                },
                default=str,
            )
        ) from exc
    mark("note asserted")
    value = note.input_value()
    mark(f"note read before save: {value!r}")
    html = to_playwright(page, entries.dialog).evaluate("el => el.outerHTML")
    posted = ""
    stored: list[tuple[int, str, str | None]] = []
    try:
        posted = save_entry(page, "planned")
        mark("saved")
        stored = db_probe.rows(
            db_path, "SELECT id, description, deleted_at FROM planned_transactions"
        )
    finally:
        trace = []
    ok = value == "today-planned" and [r[1] for r in stored] == ["today-planned"]
    if not ok:
        raise AssertionError(
            "DIAG FAIL "
            + json.dumps(
                {
                    "iter": i,
                    "value": value,
                    "posted": posted,
                    "stored": stored,
                    "steps": steps,
                    "trace": trace,
                    "console": consoles,
                    "dialog_html": html,
                },
                default=str,
            )
        )
