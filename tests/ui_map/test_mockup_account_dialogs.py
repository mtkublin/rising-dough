"""The account dialog locators resolve on the handoff overlay pages (T-UR08b, ADR-0107)."""

from __future__ import annotations

import pytest

from tests.ui_map import _html, accounts
from tests.ui_map.locator import Locator, role
from tests.ui_map.mockup_routes import HANDOFF_ROOT

_OVERLAYS = HANDOFF_ROOT / "pages" / "overlays"

_CASES: tuple[tuple[str, Locator], ...] = (
    ("new-account", accounts.new_dialog),
    ("new-account", accounts.form_name),
    ("new-account", accounts.form_currency),
    ("new-account", accounts.form_type),
    ("new-account", accounts.form_opening_balance),
    ("new-account", accounts.form_counts_as),
    ("new-account", accounts.form_liability),
    ("new-account", accounts.currency_options),
    ("new-account", accounts.create_account),
    ("new-account--error", accounts.new_dialog),
    ("edit-account--liability", accounts.edit_dialog("Investments A")),
    ("edit-account--liability", accounts.save_account),
    ("delete-account", accounts.delete_dialog("Investments E")),
    ("delete-account", accounts.delete_confirm),
    ("delete-account--blocked", accounts.blocked_dialog("Checking")),
    ("delete-account--blocked", accounts.blocked_ok),
    ("delete-account--blocked", accounts.blocked_link),
    ("delete-account--blocked-planned", accounts.blocked_dialog("Investments D")),
    ("delete-account--blocked-planned", accounts.blocked_link),
)


@pytest.mark.parametrize(
    ("page", "loc"), _CASES, ids=[f"{p}-{i}" for i, (p, _) in enumerate(_CASES)]
)
def test_locator_resolves_on_overlay(page: str, loc: Locator) -> None:
    html = (_OVERLAYS / f"{page}.html").read_text(encoding="utf-8")
    assert _html.count(html, loc) >= 1


def test_row_menu_page_lists_the_account_actions() -> None:
    html = (_OVERLAYS / "row-menu--account.html").read_text(encoding="utf-8")
    assert _html.count(html, role("button", "Row menu")) >= 1
