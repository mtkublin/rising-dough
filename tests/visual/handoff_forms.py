"""Form fill and submit recipes of the handoff overlay dialogs (T-UR00b, ADR-0147).

The handoff shows some dialogs with typed values (``new-account--filled``) or after a
failed save (``--error``). ``handoff_openers`` fetches the empty dialog into
``#modal-root``; each recipe then drives that dialog the way a user does: it fills the
fields with the values the handoff file shows and, for an error state, submits so the app
answers with its own validation error. The caller applies ``FREEZE_CSS`` afterwards.

Differences between the app dialog and the handoff (an ``as of`` field, field order, copy)
are not bridged here: the screenshot comparison reports them and an app item fixes them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from playwright.sync_api import Page

Recipe = Callable[[Page], None]

_TIMEOUT_MS: Final = 15000
_DIALOG: Final = "#modal-root dialog[open]"


def _fill(page: Page, selector: str, value: str) -> None:
    page.fill(f"{_DIALOG} {selector}", value)


def _submit_invalid(page: Page) -> None:
    """Submit past the browser's ``required`` check and wait for the app's answer.

    The answer is whatever the app sends: a 422 dialog with its field errors, or (a gap the
    comparison then shows) no error at all.
    """
    page.evaluate("sel => { document.querySelector(sel).noValidate = true; }", f"{_DIALOG} form")
    with page.expect_response(lambda r: r.request.method == "POST", timeout=_TIMEOUT_MS):
        page.click(f"{_DIALOG} button[type=submit]")
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT_MS)


def _settle(page: Page) -> None:
    """Leave no focus ring or text selection: the handoff files show neither."""
    page.evaluate("() => { document.activeElement?.blur(); getSelection()?.removeAllRanges(); }")


def _new_account_filled(page: Page) -> None:
    """Handoff: 1,250.00 EUR, name Revolut EUR, type bank, an asset."""
    _fill(page, "input[name=opening_balance]", "1,250.00")
    _fill(page, "input[name=name]", "Revolut EUR")
    _fill(page, "input[name=currency]", "EUR")
    _settle(page)


def _new_account_error(page: Page) -> None:
    """Handoff: empty name, currency XYZ, opening balance 0.00."""
    _fill(page, "input[name=currency]", "XYZ")
    _submit_invalid(page)
    _settle(page)


def _new_category_filled(page: Page) -> None:
    """Handoff: Pets, expense, the sky colour."""
    _fill(page, "input[name=name]", "Pets")
    page.check(f"{_DIALOG} .rd-swatch[data-color=sky] input", force=True)
    _settle(page)


def _new_category_error(page: Page) -> None:
    """Handoff: the name Takeaway (it exists), expense, default colour."""
    _fill(page, "input[name=name]", "Takeaway")
    _submit_invalid(page)
    _settle(page)


# Overlay page stem (pages/overlays/<stem>.html) -> recipe run after the dialog is open.
DIALOG_SUBMITS: Final[dict[str, Recipe]] = {
    "new-account--filled": _new_account_filled,
    "new-account--error": _new_account_error,
    "new-category--filled": _new_category_filled,
    "new-category--error": _new_category_error,
}


def dialog_recipe(page: str) -> Recipe | None:
    """The recipe of an overlay page (``pages/overlays/<stem>.html``), None when it has none."""
    return DIALOG_SUBMITS.get(page.removeprefix("pages/overlays/").removesuffix(".html"))
