"""Click and keystroke openers of the handoff overlay pages (T-UR00b, ADR-0147).

Some handoff overlays are client-side states with no dialog route: the command palette
(Ctrl+K), the shortcut sheet (``?``), the period popover, the row-action popovers and the
category picker inside the new-entry dialog. ``handoff_openers`` fetches routed dialogs;
here each recipe drives the app page the way a user does (the real click or key) so the
same state is open as in the handoff file, then waits until it is settled (the caller
applies ``FREEZE_CSS`` afterwards). The page is the overlay's base page, already loaded.

``override--year-cell`` clicks the Nights Out November cell: the app turns it into the inline
``rd-year-editor`` form the handoff shows (``app-year-cell.js``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from playwright.sync_api import Page

Recipe = Callable[[Page], None]

_TIMEOUT_MS: Final = 15000
_ROW_MENU: Final = "main [data-js='row-menu']"


def _palette(page: Page, query: str = "") -> None:
    page.keyboard.press("Control+k")
    page.wait_for_selector("#palette[open]", timeout=_TIMEOUT_MS)
    if query:
        page.fill("#palette [data-js='palette-input']", query)


def _shortcuts(page: Page) -> None:
    page.keyboard.press("?")
    page.wait_for_selector("#shortcuts[open]", timeout=_TIMEOUT_MS)


def _period_picker(page: Page) -> None:
    page.click("[data-js='period-trigger']")
    page.wait_for_selector(".rd-period-pick:popover-open", timeout=_TIMEOUT_MS)


def _row_menu(page: Page) -> None:
    """The first row menu opened from the keyboard: the handoff opens it on load (``data-open``) and
    focuses the first item with no pointer involved, so it shows the item's focus ring; a mouse
    click would not (``:focus-visible``), a keyboard user sees it."""
    page.locator(_ROW_MENU).first.focus()
    page.keyboard.press("Enter")
    page.wait_for_selector(".rd-menu:popover-open", timeout=_TIMEOUT_MS)
    page.mouse.move(0, 0)


def _year_cell_editor(page: Page) -> None:
    """Click the Nights Out November cell: it becomes the inline editor (``rd-year-editor``)."""
    page.click("main a.rd-year-cell[aria-label^='Nights Out, November: ']")
    page.wait_for_selector("main form[data-js='year-cell-editor']", timeout=_TIMEOUT_MS)
    # The handoff shows the field filled, with no text selection and no focus ring.
    page.evaluate("() => { document.activeElement?.blur(); getSelection()?.removeAllRanges(); }")


def _category_picker(page: Page, query: str = "") -> None:
    """The new-entry dialog (happened, 35.50) with its category picker open."""
    page.evaluate(
        "url => window.htmx.ajax('GET', url, {target: '#modal-root', swap: 'innerHTML'})",
        "/add?when=happened",
    )
    page.wait_for_selector("#modal-root dialog[open]", timeout=_TIMEOUT_MS)
    page.fill("#modal-root [data-js='amount-input']", "35.50")
    page.click("#modal-root [data-js='combobox-open']")
    page.wait_for_selector("#modal-root [data-js='combobox-input']", state="visible")
    if query:
        page.fill("#modal-root [data-js='combobox-input']", query)


def _palette_with(query: str) -> Recipe:
    return lambda page: _palette(page, query)


def _picker_with(query: str) -> Recipe:
    return lambda page: _category_picker(page, query)


# Overlay page stem (pages/overlays/<stem>.html) -> recipe.
CLICK_RECIPES: Final[dict[str, Recipe]] = {
    "command-palette": _palette,
    "command-palette--filtered": _palette_with("led"),
    "command-palette--no-match": _palette_with("pizza"),
    "shortcuts": _shortcuts,
    "period-picker": _period_picker,
    "period-picker--year": _period_picker,
    "row-menu--upcoming": _row_menu,
    "row-menu--budget": _row_menu,
    "row-menu--account": _row_menu,
    "row-menu--planned": _row_menu,
    "row-menu--recurring": _row_menu,
    "row-menu--transaction": _row_menu,
    "override--year-cell": _year_cell_editor,
    "category-picker": _category_picker,
    "category-picker--no-match": _picker_with("zoo"),
}


def click_recipe(page: str) -> Recipe | None:
    """The recipe of an overlay page (``pages/overlays/<stem>.html``), None when it has none."""
    return CLICK_RECIPES.get(page.removeprefix("pages/overlays/").removesuffix(".html"))
