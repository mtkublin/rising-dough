"""UI map: one locator module per surface (ADR-0106 section 2).

Tests never spell markup. They import a surface module and use its names::

    from tests.ui_map import ledger, _html
    from tests.ui_map.locator import to_playwright

    _html.exists(response.text, ledger.row(tx_id))           # server-side
    to_playwright(page, ledger.row(tx_id)).click()           # Playwright

Each name is a ``Locator`` (constant) or a function returning one (record
ids as arguments). Prefer role + accessible name, then label, then
documented ``id``; ``testid`` only where those are ambiguous; never CSS
classes. Migrating a surface to the redesign means editing its module here.
"""

from tests.ui_map import accounts, auth, errors, ledger, plan, settings, shell, today

__all__ = ["accounts", "auth", "errors", "ledger", "plan", "settings", "shell", "today"]
