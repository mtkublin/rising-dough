"""Small UI-map-driven actions shared by the e2e journeys (ADR-0106 section 2)."""

from __future__ import annotations

from contextlib import suppress
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError, expect

from tests.ui_map import entries, ledger, rd_shell, shell
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


def open_new_entry(page: Any) -> None:
    """Open the new-entry dialog from the new shell's top bar and wait for it."""
    assert page.evaluate("typeof window.htmx") == "object"
    to_playwright(page, rd_shell.new_entry).click()
    expect(to_playwright(page, entries.dialog)).to_be_visible()


def submit_ok(page: Any, button: Locator, *, path: str) -> str:
    """Click ``button`` and wait for the server's answer to the post to ``path``, which must be 2xx.

    The dialog going away is not a barrier for the database (a reload or a swap can remove it
    around the request); the post's response is: the row is committed before the server answers.
    ``path`` is the exact URL path of the committing post (query string ignored): any other post
    (a formula or limit preview, an undo) would release the barrier before the row exists. A click
    that never posts there times out here, and a rejected post (422, 409, 500) fails with its
    body instead of surfacing later as an empty probe. Hero refresh GETs never match.
    """

    def is_post(response: Any) -> bool:
        posted = response.request.method == "POST"
        return bool(posted and urlsplit(response.url).path.rstrip("/") == path)

    with page.expect_response(is_post) as answer:
        to_playwright(page, button).click()
    assert answer.value.ok, (
        f"{answer.value.url} answered {answer.value.status}: {answer.value.text()}"
    )
    return str(answer.value.request.post_data)


ENTRY_PATHS = {"happened": "/transactions", "planned": "/planned", "repeats": "/recurring"}


def save_entry(page: Any, tab: str = "happened") -> str:
    """Save the new-entry dialog's ``tab`` (happened, planned, repeats) and wait for its commit.

    Only the entry's own post (``/transactions``, ``/planned`` or ``/recurring``) releases the
    barrier (see :func:`submit_ok`). Returns the posted form body.
    """
    return submit_ok(page, entries.save, path=ENTRY_PATHS[tab])


def choose_category(page: Any, name: str) -> None:
    """Pick ``name`` in the new-entry dialog's category search (recent radios are not needed)."""
    to_playwright(page, entries.category_search).click()
    query = to_playwright(page, entries.category_query)
    query.fill(name)
    with page.expect_response(_is_hero_refresh):  # the hero follows the category (sign)
        query.press("Enter")
    _settle(page)


def choose_account(page: Any, name: str) -> None:
    field = to_playwright(page, entries.field_account.inside(entries.dialog))  # not the filter bar
    if field.evaluate("el => el.selectedOptions[0].label") == name:
        return  # no change event, no refresh
    with page.expect_response(_is_hero_refresh):  # the hero follows the account (currency)
        field.select_option(label=name)
    _settle(page)


def _is_hero_refresh(response: Any) -> bool:
    return "hero=1" in response.url


HTMX_PENDING_JS = """
(() => {
  const inflight = new Set();
  window.__htmxPending = 0;
  const sync = () => { window.__htmxPending = inflight.size; };
  const key = (e) => (e.detail && (e.detail.xhr || e.detail.requestConfig)) || e.target;
  document.addEventListener('htmx:beforeRequest', (e) => { inflight.add(key(e)); sync(); });
  for (const name of ['htmx:afterRequest', 'htmx:sendError', 'htmx:responseError',
                      'htmx:sendAbort', 'htmx:afterSettle']) {
    document.addEventListener(name, (e) => { inflight.delete(key(e)); sync(); });
  }
})();
"""

_QUIET_JS = """
async () => {
  const busy = () =>
    (window.__htmxPending || 0) > 0 ||
    document.querySelector('.htmx-request, .htmx-swapping, .htmx-settling') !== null;
  const frame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const deadline = performance.now() + 5000;
  while (performance.now() < deadline) {
    if (!busy()) {
      await frame();
      await frame();
      if (!busy()) return true;  // held stable across two animation frames
    } else {
      await frame();
    }
  }
  return false;
}
"""

# (description, attempts) of every fill_stable that needed more than one attempt; the e2e
# conftest prints a summary line so CI logs show how often a swap beat a fill (QFIX13).
FILL_RETRIES: list[tuple[str, int]] = []
FILL_ATTEMPTS = 3


def quiesce(page: Any) -> None:
    """Block until no htmx request, swap or settle is in flight, stable across two frames."""
    # A navigation destroys the context: the new page has nothing in flight yet.
    with suppress(PlaywrightError):
        page.evaluate(_QUIET_JS)


def fill_stable(locator: Any, value: str) -> None:
    """Fill ``locator`` only while htmx is quiet and prove the value stuck (QFIX13).

    A hero refresh swap landing between Playwright's focus and text-insert steps would send the
    text to the element about to be replaced. Quiesce, fill, check; if the value was lost,
    quiesce and fill again (up to ``FILL_ATTEMPTS``). Retries are recorded in ``FILL_RETRIES``.
    """
    page = locator.page
    for attempt in range(1, FILL_ATTEMPTS + 1):
        quiesce(page)
        locator.fill(value)
        try:
            expect(locator).to_have_value(value, timeout=1500)
            quiesce(page)  # a swap queued behind the fill would still replace the field
            expect(locator).to_have_value(value, timeout=1500)
        except AssertionError:
            if attempt == FILL_ATTEMPTS:
                raise AssertionError(
                    f"fill of {value!r} was lost in all {attempt} attempts"
                ) from None
            continue
        if attempt > 1:
            FILL_RETRIES.append((str(locator), attempt))
        return


def _settle(page: Any) -> None:
    """Let the hero swap land before the amount is typed (it re-renders the amount input)."""
    quiesce(page)
