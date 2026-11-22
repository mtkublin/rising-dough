"""App shell: navigation, flash/toast regions, modal root, palette, sign out."""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, role

main = by_id("main")
flash_region = by_id("flash-region")
flash_region_assertive = by_id("flash-region-assertive")
modal_root = by_id("modal-root")
toast_root = by_id("toast-root")
drawer_root = by_id("drawer-root")
palette = by_id("command-palette")
shortcuts_dialog = by_id("shortcuts-dialog")

primary_nav = role("navigation", "Primary navigation")
skip_link = role("link", "Skip to content")
sign_out = role("button", "Sign out")
brand_link = role("link", "Rising Dough")
nav_links = role("link").inside(primary_nav)
dialog = role("dialog")

palette_dialog = role("dialog", "Command palette")
palette_options = role("option").inside(palette)
shortcuts_options = role("option").inside(shortcuts_dialog)


def nav_link(label: str) -> Locator:
    """Primary navigation link by its visible label (Today, Ledger, ...)."""
    return role("link", label).inside(primary_nav)


def palette_option(label: str) -> Locator:
    """Command-palette row by its visible label (``Go to Today``)."""
    return role("option", label).inside(palette)


# --- T-UT08a: existing e2e journeys ---
add_button = role("button", "+ Add")  # top-bar add (opens the New entry slide-over)
slideover = role("dialog").inside(modal_root)
undo_button = role("button", "Undo").inside(toast_root)
