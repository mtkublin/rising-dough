"""Settings surface: categories, currency, preferences, security, users."""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, label, role

tabs = role("navigation", "Settings tabs")
new_category = role("button", "+ New category")
create_category = role("button", "Create category")
passkeys = by_id("passkeys")
users_table = by_id("users-table")
security_heading = role("heading", "Security", level=1)
users_heading = role("heading", "Users", level=1)
user_email = label("Email")


def tab(name: str) -> Locator:
    return role("link", name).inside(tabs)


def category_row(category_id: int) -> Locator:
    return by_id(f"category-{category_id}")


def edit_category(category_id: int) -> Locator:
    return role("button", f"Edit category {category_id}")


def user_row(user_id: int) -> Locator:
    return by_id(f"user-row-{user_id}")
