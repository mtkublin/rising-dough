"""Locators for the shared dialog shell (T-UR04e, ADR-0107 section 2).

One shell, three roles: a standard ``dialog`` named after its title, a confirm
``alertdialog`` (destructive) and the blocked ``alertdialog`` (no form). Wave 6b
dialogs reuse these helpers with their own title text.
"""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, role


def dialog(title: str) -> Locator:
    """Standard dialog by its heading (``aria-labelledby`` points at the title)."""
    return role("dialog", title, exact=True)


def alert_dialog(title: str) -> Locator:
    """Confirm or blocked dialog (``role=alertdialog``) by its heading."""
    return role("alertdialog", title, exact=True)


def close_button(scope: Locator) -> Locator:
    return role("button", "Close", exact=True).inside(scope)


def action(scope: Locator, label: str) -> Locator:
    """A footer action: button or link by its visible label."""
    return role("button", label, exact=True).inside(scope)


def action_link(scope: Locator, label: str) -> Locator:
    return role("link", label, exact=True).inside(scope)


def field_error(scope: Locator, name: str) -> Locator:
    """The ``▲ message`` line under a field of a failed save (id ``field-<name>-error``, Q18)."""
    return by_id(f"field-{name}-error").inside(scope)


def hero_amount(scope: Locator, label: str = "Amount") -> Locator:
    return role("textbox", label, exact=True).inside(scope)


# Dev gallery (/dev/shell, T-UR04e)
dev_menu_button = role("button", "Row menu")
dev_standard = dialog("new account")
dev_sheet = dialog("new entry")
dev_confirm = alert_dialog("Delete Investments E?")
dev_blocked = alert_dialog("Can\u2019t delete Checking")
