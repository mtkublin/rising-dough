"""Settings ``ui_map`` names resolve against the handoff pages and overlays (T-UT09, T-UR13)."""

from __future__ import annotations

import pytest

from tests.ui_map import _html, settings as app_settings
from tests.ui_map.locator import Locator
from tests.ui_map.mockup import settings as mockup_settings
from tests.ui_map.mockup_routes import HANDOFF_ROOT, handoff_page
from tests.ui_map.target import public_names, surface


def _page(path: str) -> str:
    return (HANDOFF_ROOT / "pages" / path).read_text(encoding="utf-8")


CATEGORIES = _page("settings/categories.html")
FX = _page("settings/currency-fx.html")
PREFS = _page("settings/preferences.html")
NEW_CATEGORY = _page("overlays/new-category.html")
EDIT_CATEGORY = _page("overlays/edit-category.html")
ARCHIVE_CATEGORY = _page("overlays/archive-category.html")
M = mockup_settings

ON_PAGE: list[tuple[str, str, Locator]] = [
    ("categories heading", CATEGORIES, M.heading),
    ("categories new", CATEGORIES, M.new_category),
    ("categories anchor", CATEGORIES, M.income_anchor),
    ("categories tab", CATEGORIES, M.tab("categories")),
    ("categories fx tab", CATEGORIES, M.tab("currency & fx")),
    ("categories users tab", CATEGORIES, M.tab("users")),
    ("categories groups", CATEGORIES, M.section_headings),
    ("categories row", CATEGORIES, M.category_row(1)),
    ("categories edit", CATEGORIES, M.edit_category(1)),
    ("categories archive", CATEGORIES, M.archive_category(1)),
    ("fx heading", FX, M.heading),
    ("fx card", FX, M.fx_heading),
    ("fx tab", FX, M.tab("currency & fx")),
    ("prefs heading", PREFS, M.preferences_heading),
    ("prefs workspace", PREFS, M.prefs_panel_heading),
    ("prefs terms", PREFS, M.pref_terms),
    ("prefs values", PREFS, M.pref_values),
    ("prefs theme group", PREFS, M.theme_group),
    ("prefs theme dark", PREFS, M.theme_option("dark")),
    ("new dialog", NEW_CATEGORY, M.category_form),
    ("new name", NEW_CATEGORY, M.category_name),
    ("new expense", NEW_CATEGORY, M.category_expense),
    ("new income", NEW_CATEGORY, M.category_income),
    ("new default colour", NEW_CATEGORY, M.category_default_colour),
    ("new submit", NEW_CATEGORY, M.create_category),
    ("edit name", EDIT_CATEGORY, M.edit_form_name),
    ("edit save", EDIT_CATEGORY, M.edit_form_save),
    ("archive dialog", ARCHIVE_CATEGORY, M.archive_dialog),
    ("archive confirm", ARCHIVE_CATEGORY, M.archive_confirm),
]


def test_variant_defines_every_app_name() -> None:
    assert public_names(app_settings) <= public_names(mockup_settings)


@pytest.mark.parametrize(("name", "html", "loc"), ON_PAGE, ids=[row[0] for row in ON_PAGE])
def test_name_resolves_in_handoff(name: str, html: str, loc: Locator) -> None:
    assert _html.count(html, loc) >= 1, name


def test_surface_selects_by_target() -> None:
    assert surface("settings", "app") is app_settings
    assert surface("settings", "mockup") is mockup_settings


def test_routes_map_to_the_handoff_pages() -> None:
    assert handoff_page("/settings?tab=fx") == "pages/settings/currency-fx.html"
    assert handoff_page("/categories/4/edit") == "pages/overlays/edit-category.html"
