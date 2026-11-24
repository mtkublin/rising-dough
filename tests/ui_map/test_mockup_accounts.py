"""Every ``accounts`` name resolves against the handoff markup (T-UT09, T-UR08)."""

from __future__ import annotations

import pytest

from tests.ui_map import _html, accounts as app_accounts
from tests.ui_map.locator import Locator
from tests.ui_map.mockup import accounts as mockup_accounts
from tests.ui_map.mockup_routes import HANDOFF_ROOT, handoff_page
from tests.ui_map.target import public_names, surface

ACCOUNTS_HTML = (HANDOFF_ROOT / "pages" / "accounts.html").read_text(encoding="utf-8")
EMPTY_HTML = (HANDOFF_ROOT / "pages" / "accounts--empty.html").read_text(encoding="utf-8")


def _locators() -> list[tuple[str, Locator]]:
    out: list[tuple[str, Locator]] = []
    for name in sorted(public_names(mockup_accounts) - mockup_accounts.NO_HANDOFF_TWIN):
        value = getattr(mockup_accounts, name)
        out.append((name, value(1) if callable(value) else value))
    return out


def test_variant_defines_every_app_name() -> None:
    assert public_names(app_accounts) <= public_names(mockup_accounts)


@pytest.mark.parametrize(
    ("name", "loc"), _locators(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_name_resolves_in_handoff(name: str, loc: Locator) -> None:
    assert _html.count(ACCOUNTS_HTML, loc) >= 1, name


def test_empty_state_call_to_action_resolves_in_the_empty_page() -> None:
    assert _html.count(EMPTY_HTML, mockup_accounts.new_account_cta) == 1
    assert _html.count(EMPTY_HTML, mockup_accounts.new_account_button) == 1


def test_surface_selects_by_target() -> None:
    assert surface("accounts", "app") is app_accounts
    assert surface("accounts", "mockup") is mockup_accounts


def test_empty_route_maps_to_the_empty_page() -> None:
    assert handoff_page("/accounts?state=empty") == "pages/accounts--empty.html"
