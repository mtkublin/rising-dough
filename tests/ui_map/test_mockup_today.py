"""Every ``today`` name resolves against the handoff markup (T-UT09)."""

from __future__ import annotations

import pytest

from tests.ui_map import _html, today as app_today
from tests.ui_map.locator import Locator
from tests.ui_map.mockup import today as mockup_today
from tests.ui_map.mockup_routes import HANDOFF_ROOT, ROUTES, handoff_page
from tests.ui_map.target import public_names, surface

TODAY_HTML = (HANDOFF_ROOT / "pages" / "today.html").read_text(encoding="utf-8")


def _locators() -> list[tuple[str, Locator]]:
    out: list[tuple[str, Locator]] = []
    for name in sorted(public_names(mockup_today)):
        value = getattr(mockup_today, name)
        out.append((name, value(1) if callable(value) else value))
    return out


def test_variant_defines_every_app_name() -> None:
    assert public_names(app_today) <= public_names(mockup_today)


@pytest.mark.parametrize(
    ("name", "loc"), _locators(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_name_resolves_in_handoff(name: str, loc: Locator) -> None:
    assert _html.count(TODAY_HTML, loc) >= 1, name


def test_surface_selects_by_target() -> None:
    assert surface("today", "app") is app_today
    assert surface("today", "mockup") is mockup_today


def test_every_mapped_route_points_at_an_existing_page() -> None:
    missing = [r for r, p in ROUTES.items() if not (HANDOFF_ROOT / p).is_file()]
    assert missing == []


def test_handoff_page_matches_concrete_ids() -> None:
    assert handoff_page("/accounts/7/edit") == "pages/overlays/edit-account.html"
    with pytest.raises(KeyError):
        handoff_page("/nope")
