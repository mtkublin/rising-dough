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


def nav_link(label: str) -> Locator:
    """Primary navigation link by its visible label (Today, Ledger, ...)."""
    return role("link", label).inside(primary_nav)
