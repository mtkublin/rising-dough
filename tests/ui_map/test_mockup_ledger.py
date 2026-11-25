"""Ledger Actual names resolve against the handoff markup (T-UT09, T-UR09)."""

from __future__ import annotations

import pytest

from tests.ui_map import _html, ledger as app_ledger
from tests.ui_map.locator import Locator
from tests.ui_map.mockup import ledger as mockup_ledger
from tests.ui_map.mockup_routes import HANDOFF_ROOT, handoff_page
from tests.ui_map.target import public_names, surface

_PAGES = HANDOFF_ROOT / "pages" / "ledger"
ACTUAL_HTML = (_PAGES / "actual.html").read_text(encoding="utf-8")
NO_MATCHES_HTML = (_PAGES / "actual--no-matches.html").read_text(encoding="utf-8")

# Locators defined as module constants that the sample page resolves.
_CONSTANTS = (
    "heading",
    "table",
    "filters_form",
    "filter_search",
    "filter_category",
    "pagination",
    "older_button",
    "recently_deleted_link",
)
_BUILDERS = ("row", "row_menu", "row_cells", "select_box")


def _locators() -> list[tuple[str, Locator]]:
    out: list[tuple[str, Locator]] = [(n, getattr(mockup_ledger, n)) for n in _CONSTANTS]
    out += [(n, getattr(mockup_ledger, n)(1)) for n in _BUILDERS]
    out.append(("view_table", mockup_ledger.view_table("actual")))
    out += [
        (f"view_tab:{v}", mockup_ledger.view_tab(v)) for v in ("actual", "planned", "recurring")
    ]
    out.append(("day_head", mockup_ledger.day_head("SAT 31 OCT")))
    return out


def test_variant_defines_every_app_name() -> None:
    assert public_names(app_ledger) <= public_names(mockup_ledger)


@pytest.mark.parametrize(
    ("name", "loc"), _locators(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_name_resolves_in_handoff(name: str, loc: Locator) -> None:
    assert _html.count(ACTUAL_HTML, loc) >= 1, name


def test_filter_bar_is_on_the_no_matches_page() -> None:
    assert _html.count(NO_MATCHES_HTML, mockup_ledger.filters_form) == 1
    assert _html.count(NO_MATCHES_HTML, mockup_ledger.heading) == 1


def test_surface_selects_by_target() -> None:
    assert surface("ledger", "app") is app_ledger
    assert surface("ledger", "mockup") is mockup_ledger


def test_ledger_routes_map_to_the_actual_page() -> None:
    assert handoff_page("/ledger") == "pages/ledger/actual.html"
    assert handoff_page("/ledger/table") == "pages/ledger/actual.html"
