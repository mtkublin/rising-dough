"""Browser recipes of four new-entry handoff overlays beyond the plain tabs (T-UR00b, ADR-0147).

``new-entry--happened`` / ``--planned`` / ``--repeats-fixed`` are plain ``/add?when=<tab>`` fetches
(``reference_map.OVERLAY_DIALOGS``). The four states here need the user's input:

* ``new-entry--error``: the dialog submitted with the amount 0.00 and no category (a real
  browser submit, so the CSRF token travels with the form); the app answers with its 422 dialog.
* ``new-entry--over-limit``: 13,000.00 on Credit Card (12,521.63 left), shown by the live
  limit preview.
* ``new-entry--repeats-formula``: the repeats tab with the amount switched to ``formula ƒ`` and
  Takeaway picked first, the first component filled as 12 % of Salary and day 31 (client-side
  reveal plus the formula preview).
* ``new-entry--phone-sheet``: the handoff file is the happened dialog (no extra markup); the
  bottom sheet is the same dialog at the phone viewport, so it maps to ``/add?when=happened``
  in ``PHONE_SHEET_DIALOGS`` and needs no recipe.

The page is the overlay's base page (Today), already loaded.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Final

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

Recipe = Callable[[Page], None]

_TIMEOUT_MS: Final = 15000
_DIALOG: Final = "#modal-root dialog[open]"
# Overlay page -> the dialog route it is the same state as (no input needed).
PHONE_SHEET_DIALOGS: Final[dict[str, str]] = {
    "pages/overlays/new-entry--phone-sheet.html": "/add?when=happened",
}


def _open(page: Page, when: str) -> None:
    page.evaluate(
        "url => window.htmx.ajax('GET', url, {target: '#modal-root', swap: 'innerHTML'})",
        f"/add?when={when}",
    )
    page.wait_for_selector(_DIALOG, timeout=_TIMEOUT_MS)


def _scroll_back_up(page: Page) -> None:
    """The dialog scrolled while its fields were filled; the user scrolls back up to the amount."""
    page.evaluate(
        """sel => document.querySelectorAll(`${sel}, ${sel} *`).forEach(
            (el) => { if (el.scrollTop > 0) el.scrollTop = 0; })""",
        _DIALOG,
    )


def _error(page: Page) -> None:
    """Submit the happened dialog with amount 0.00 (the handoff value); wait for the 422 dialog."""
    _open(page, "happened")
    page.select_option("#modal-root select[name=account_id]", label="Credit Card")
    page.fill("#modal-root [data-js='amount-input']", "0.00")
    page.fill("#modal-root input[name=description]", "Takeaway")  # the handoff's note
    page.click(f"{_DIALOG} button[type=submit]")
    page.wait_for_selector("#modal-root .rd-field__error", timeout=_TIMEOUT_MS)
    # The dialog focuses the amount and selects it; the user's next key (End) puts the caret back.
    page.wait_for_timeout(150)  # amount-input.js selects a frame after focus
    page.press("#modal-root [data-js='amount-input']", "End")
    page.mouse.move(0, 0)  # the pointer rests off the save button, as in the handoff (no hover)


def _over_limit(page: Page) -> None:
    """13,000.00 on Credit Card: wait for the over-limit line of the live preview."""
    _open(page, "happened")
    # Amount first, then category and account: each pick refreshes the hero, which shows the typed
    # amount grouped (13,000.00).
    page.fill("#modal-root [data-js='amount-input']", "13000.00")
    page.locator("#modal-root .rd-chip-option", has_text="Takeaway").click()
    page.select_option("#modal-root select[name=account_id]", label="Credit Card")
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT_MS)  # the hero refresh settles first
    page.fill("#modal-root input[name=description]", "Takeaway")  # the handoff's note
    page.click("#modal-root [data-js='amount-input']")  # back into the amount, caret at its end
    page.wait_for_timeout(150)  # amount-input.js selects a frame after focus
    # The file shows the amount from its first digit (the phone's hero is narrower than 13,000.00
    # and the file's value is not scrolled): Home puts the caret and the scroll back at the start.
    page.press("#modal-root [data-js='amount-input']", "Home")
    # The form's change event (a field losing focus) refreshes the preview with all three values;
    # an earlier hero refresh can swallow it, so it is sent again until the line shows.
    line = page.locator("#modal-root .rd-credit-line--over")
    for _ in range(4):
        page.dispatch_event("#modal-root dialog[open] form", "change")
        with contextlib.suppress(PlaywrightTimeoutError):
            line.wait_for(timeout=3000)
            break
    else:
        line.wait_for(timeout=_TIMEOUT_MS)
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT_MS)  # the grouped hero is back


def _repeats_formula(page: Page) -> None:
    """Repeats tab, amount switched to formula, component 1 = 12 % of Salary."""
    _open(page, "repeats")
    page.locator("#modal-root .rd-chip-option", has_text="Takeaway").click()
    page.select_option("#modal-root select[name=account_id]", label="Credit Card")
    page.locator("#modal-root .rd-segmented__option", has_text="formula").click()
    page.fill("#modal-root input[name='components[0][percent]']", "12")
    page.click("#modal-root [data-js='multiselect']")
    page.locator("#modal-root .rd-msel__opt", has_text="Salary").click()
    page.click("#modal-root [data-js='multiselect']")  # close the category list again
    page.wait_for_selector("#modal-root .rd-msel", state="hidden", timeout=_TIMEOUT_MS)
    page.fill("#modal-root input[name=day_of_month]", "31")
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT_MS)  # the formula preview settles
    # The file shows the close button with its focus ring and no hover (README "Normalised state"):
    # a keyboard user's Shift+Tab back to the dialog start lands there; the pointer rests off.
    _scroll_back_up(page)
    page.keyboard.press("Shift")  # keyboard modality, so :focus-visible shows the ring
    page.focus(f"{_DIALOG} .rd-dialog__close")
    page.mouse.move(0, 0)


NEWENTRY_RECIPES: Final[dict[str, Recipe]] = {
    "pages/overlays/new-entry--error.html": _error,
    "pages/overlays/new-entry--over-limit.html": _over_limit,
    "pages/overlays/new-entry--repeats-formula.html": _repeats_formula,
}


def _typed(page: Page, *, due: str = "", day: str = "") -> None:
    """The dialog as the handoff shows it once worked on: 35.50 on Credit Card, Takeaway, a note.

    Amount first (each pick refreshes the hero), then category, account, the extra field of the
    tab and the note; the user ends in the amount.
    """
    amount = "#modal-root [data-js='amount-input']"
    page.fill(amount, "35.50")
    page.locator("#modal-root .rd-chip-option", has_text="Takeaway").click()
    page.select_option("#modal-root select[name=account_id]", label="Credit Card")
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT_MS)
    if due:
        page.fill("#modal-root input[name=operation_date]", due)
    if day:
        page.fill("#modal-root input[name=day_of_month]", day)
    page.fill("#modal-root input[name$='description']", "Takeaway")
    page.click(amount)
    page.wait_for_timeout(150)  # amount-input.js selects a frame after focus
    page.press(amount, "End")
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT_MS)
    _scroll_back_up(page)


def typed_happened(page: Page) -> None:
    _typed(page)
    page.locator("#modal-root .rd-credit-line").wait_for(timeout=_TIMEOUT_MS)


def _typed_planned(page: Page) -> None:
    _typed(page, due="2026-11-15")


def _typed_repeats(page: Page) -> None:
    _typed(page, day="31")


# Dialog pages the harness opens from their route (``OVERLAY_DIALOGS``): the typed state follows.
DIALOG_RECIPES: Final[dict[str, Recipe]] = {
    "pages/overlays/new-entry--happened.html": typed_happened,
    "pages/overlays/new-entry--phone-sheet.html": typed_happened,
    "pages/overlays/new-entry--planned.html": _typed_planned,
    "pages/overlays/new-entry--repeats-fixed.html": _typed_repeats,
}


def dialog_recipe(page: str) -> Recipe | None:
    """What the user types into a dialog the harness opened from its route, None when nothing."""
    return DIALOG_RECIPES.get(page)


def newentry_recipe(page: str) -> Recipe | None:
    """The recipe of one of the input-driven new-entry overlays, None when it has none."""
    return NEWENTRY_RECIPES.get(page)
