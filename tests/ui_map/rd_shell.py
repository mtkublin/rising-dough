"""New (Rising Dough) app shell: skip link, rails, header, roots, dialogs, theme.

Locators for the handoff page shell (``layouts/base.html``, T-UR02). The app
and the handoff render the same markup, so ``tests.ui_map.mockup.shell``
re-exports these names and one journey runs on both targets. The old shell
(``tests.ui_map.shell``) stays for pages still on ``base.html``.
"""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, role

skip_link = role("link", "skip to content")
main = by_id("main")
header = role("banner")
brand_link = role("link", "Rising Dough").inside(header)

# Desktop rail (>= 768 px) and phone tab bar (< 768 px): one is hidden per width.
nav_desktop = role("navigation", "Main", exact=True)
nav_phone = role("navigation", "Main, phone", exact=True)

new_entry = role("link", "[ new entry ]").inside(header)
shortcuts_button = role("button", "Keyboard shortcuts")
settings_link = role("link", "settings").inside(header)
sign_out = role("button", "sign out")

# Page-level roots, present on every page.
flash_region = by_id("flash-region")
modal_root = by_id("modal-root")
drawer_root = by_id("drawer-root")
toast_root = by_id("toast-root")

# Global dialogs, rendered once, closed.
palette = by_id("palette")
palette_dialog = role("dialog", "Command palette")
palette_input = role("combobox", "Command").inside(palette)
palette_options = role("option").inside(palette)
shortcuts = by_id("shortcuts")
shortcuts_dialog = role("dialog", "keyboard shortcuts")
shortcuts_close = role("button", "Close").inside(shortcuts)

# Theme switch (Settings > Preferences in the handoff; also on the dev shell page).
theme_switch = role("group", "theme")


def nav_link(label: str) -> Locator:
    """Desktop rail link by its label (``today``, ``ledger``, ...)."""
    return role("link", label, exact=True).inside(nav_desktop)


def tab_link(label: str) -> Locator:
    """Phone tab-bar link by its label."""
    return role("link", label, exact=True).inside(nav_phone)


def palette_option(label: str) -> Locator:
    """Command-palette row by its label (``Go to Today``)."""
    return role("option", label).inside(palette)


def theme_option(value: str) -> Locator:
    """Theme button (``system``, ``light``, ``dark``)."""
    return role("button", value, exact=True).inside(theme_switch)
