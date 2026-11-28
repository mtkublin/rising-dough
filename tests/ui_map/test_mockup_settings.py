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
SECURITY = _page("settings/security.html")
SECURITY_ERROR = _page("settings/security--error.html")
USERS = _page("settings/users.html")
EDIT_USER = _page("overlays/edit-user.html")
DELETE_USER = _page("overlays/delete-user.html")
RESET_USER = _page("overlays/reset-password.html")
ONE_TIME = _page("overlays/one-time-password.html")
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
    ("security heading", SECURITY, M.security_heading),
    ("security tab", SECURITY, M.tab("security")),
    ("security password form", SECURITY, M.password_form),
    ("security current", SECURITY, M.current_password),
    ("security new", SECURITY, M.new_password),
    ("security confirm", SECURITY, M.confirm_password),
    ("security change button", SECURITY, M.change_password_button),
    ("security passkeys", SECURITY, M.passkeys),
    ("security passkey label", SECURITY, M.passkey_label),
    ("security add passkey", SECURITY, M.add_passkey),
    ("security sessions", SECURITY, M.sessions),
    ("security sign out", SECURITY, M.session_signout),
    ("security error field", SECURITY_ERROR, M.password_error("current_password")),
    ("users heading", USERS, M.users_heading),
    ("users tab", USERS, M.tab("users")),
    ("users table", USERS, M.users_table),
    ("users row", USERS, M.user_row(2)),
    ("users edit item", USERS, M.edit_user_item("partner@example.test")),
    ("users reset item", USERS, M.reset_user("partner@example.test")),
    ("users delete item", USERS, M.remove_user("partner@example.test")),
    ("edit user dialog", EDIT_USER, M.edit_form),
    ("edit user email", EDIT_USER, M.user_email),
    ("edit user name", EDIT_USER, M.user_name),
    ("edit user admin", EDIT_USER, M.user_is_admin),
    ("users row menu", USERS, M.user_menu("partner@example.test")),
    ("edit user save", EDIT_USER, M.edit_save),
    ("delete user dialog", DELETE_USER, M.delete_dialog),
    ("delete user confirm", DELETE_USER, M.delete_confirm),
    ("reset dialog", RESET_USER, M.reset_dialog),
    ("reset confirm", RESET_USER, M.reset_confirm),
    ("one-time done", ONE_TIME, M.one_time_done),
    ("one-time dialog", ONE_TIME, M.new_password_toast),
    ("one-time value", ONE_TIME, M.new_password_value),
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
