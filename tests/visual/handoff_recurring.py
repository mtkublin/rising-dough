"""Recurring-rule, transaction and override states of the handoff overlays (T-UR00b, ADR-0147).

Five handoff overlays show a dialog the user has already worked on, so they have no route of
their own: ``edit-recurring--empty`` / ``--incomplete`` / ``--picking`` are the Taxes formula
editor after the user edited a component, ``edit-transaction--error`` is the Takeaway edit
dialog answering a cleared amount, and ``override--remove`` is the "Remove override?" confirm
of the Big Purchases budget month.

Each state starts from a dialog route the harness already resolves (``handoff_openers``, the
sibling page named in ``STATE_SOURCE``; ids come from the seeded scratch DB, never a typed
id) and then does what a user does in the real page (``STATE_RECIPES``: clicks, typing and a
real submit so the CSRF token travels). ``override--remove`` is only a query on the budget
override route (``remove=1``), no recipe. The caller applies ``FREEZE_CSS`` afterwards.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Final

from playwright.sync_api import Page

from tests.visual.handoff_openers import opener_url

Recipe = Callable[[Page], None]

_TIMEOUT_MS: Final = 15000
_DIALOG: Final = "#modal-root dialog[open]"
_COMPONENT: Final = f"{_DIALOG} [data-js='formula-component']"

# Overlay stem -> (sibling overlay whose opener route it reuses, query appended to that route).
STATE_SOURCE: Final[dict[str, tuple[str, str]]] = {
    "edit-recurring--empty": ("edit-recurring--formula", ""),
    "edit-recurring--incomplete": ("edit-recurring--formula", ""),
    "edit-recurring--picking": ("edit-recurring--formula", ""),
    "edit-transaction--error": ("edit-transaction", ""),
    "override--remove": ("override--budget-month", "&remove=1"),
}


def _drop_second_component(page: Page) -> None:
    """The handoff's Taxes formula of these states has one component (the 19 % income one)."""
    page.locator(_COMPONENT).nth(1).locator("[data-js='formula-remove']").click()
    page.wait_for_function(
        "sel => document.querySelectorAll(sel).length === 1", arg=_COMPONENT, timeout=_TIMEOUT_MS
    )


def _clear_component(page: Page, index: int) -> None:
    """Empty the percentage and untick every category of component ``index`` (0-based)."""
    comp = page.locator(_COMPONENT).nth(index)
    comp.locator("input[name$='[percent]']").fill("")
    trigger = comp.locator("[data-js='multiselect']")
    trigger.click()
    page.wait_for_selector(f"{_COMPONENT} .rd-msel:not([hidden])", timeout=_TIMEOUT_MS)
    checked = comp.locator(".rd-msel__opt:has(input:checked)")
    while checked.count():
        checked.first.click()
    trigger.click()
    page.wait_for_selector(
        f"{_COMPONENT} .rd-msel:not([hidden])", state="detached", timeout=_TIMEOUT_MS
    )


def _empty(page: Page) -> None:
    _drop_second_component(page)
    _clear_component(page, 0)
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT_MS)


def _incomplete(page: Page) -> None:
    _clear_component(page, 1)
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT_MS)
    page.click(f"{_DIALOG} button[type=submit]")
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT_MS)


def _picking(page: Page) -> None:
    _drop_second_component(page)
    page.wait_for_load_state("networkidle", timeout=_TIMEOUT_MS)
    page.locator(f"{_COMPONENT} [data-js='multiselect']").first.click()
    page.wait_for_selector(f"{_COMPONENT} .rd-msel:not([hidden])", timeout=_TIMEOUT_MS)


def _transaction_error(page: Page) -> None:
    """Type a zero amount and save: the app answers 422 with the amount error in the dialog."""
    page.fill(f"{_DIALOG} [data-js='amount-input']", "0")
    page.click(f"{_DIALOG} button[type=submit]")
    page.wait_for_selector(
        f"{_DIALOG} .rd-dialog__hero-error, {_DIALOG} .rd-field__error", timeout=_TIMEOUT_MS
    )


# Overlay stem -> recipe run once the sourced dialog is open.
STATE_RECIPES: Final[dict[str, Recipe]] = {
    "edit-recurring--empty": _empty,
    "edit-recurring--incomplete": _incomplete,
    "edit-recurring--picking": _picking,
    "edit-transaction--error": _transaction_error,
}


def _stem(page: str) -> str:
    return page.removeprefix("pages/overlays/").removesuffix(".html")


STATE_PAGES: Final[frozenset[str]] = frozenset(f"pages/overlays/{n}.html" for n in STATE_SOURCE)


def state_opener_url(page: str, conn: sqlite3.Connection) -> str | None:
    """Dialog route a state starts from (ids resolved from the seed), None for other pages."""
    source = STATE_SOURCE.get(_stem(page))
    if source is None:
        return None
    base = opener_url(f"pages/overlays/{source[0]}.html", conn)
    return None if base is None else base + source[1]


def state_recipe(page: str) -> Recipe | None:
    """The user actions that bring the opened dialog into the handoff state, None when none."""
    return STATE_RECIPES.get(_stem(page))
