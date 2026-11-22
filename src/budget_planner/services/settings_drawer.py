"""Settings drawer view model (T-Q267): which tab is active and what each tab shows.

Pure read service over the category, FX and preference services; the router only parses the
``tab`` query value and renders the returned context (ADR-0130 thin web, ADR-0142).
"""

from __future__ import annotations

import sqlite3
from typing import Final, Literal, get_args

from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.services import (
    categories as categories_service,
    fx as fx_service,
    preferences as preferences_service,
)

TabKind = Literal["categories", "fx", "prefs"]
_VALID_TABS: Final[tuple[TabKind, ...]] = get_args(TabKind)
DEFAULT_TAB: Final[TabKind] = "categories"
_FX_LIMIT: Final = 50


def coerce_tab(raw: str | None) -> TabKind:
    """Return a valid tab identifier, defaulting to Categories on absent/invalid."""
    for valid in _VALID_TABS:
        if raw == valid:
            return valid
    return DEFAULT_TAB


def _live_income(categories: list[Category]) -> list[Category]:
    return [c for c in categories if c.direction is Direction.INCOME and c.deleted_at is None]


def _categories_context(conn: sqlite3.Connection, user_id: int) -> dict[str, object]:
    all_cats = list(categories_service.list_all(conn, user_id))
    return {
        "categories": all_cats,
        # ADR-0056 section 8: grouped sections (Expense, Income, System).
        "expense_categories": [
            c for c in all_cats if (not c.is_system) and c.direction is Direction.EXPENSE
        ],
        "income_categories": [
            c for c in all_cats if (not c.is_system) and c.direction is Direction.INCOME
        ],
        "system_categories": [c for c in all_cats if c.is_system],
        # Mirror the Preferences income-anchor control at the top of the tab.
        "anchor_income_categories": _live_income(all_cats),
        "current_anchor_id": preferences_service.get_income_anchor_category_id(conn, user_id),
    }


def _prefs_context(conn: sqlite3.Connection, user_id: int) -> dict[str, object]:
    # ADR-0031 section 1: the income anchor selector lives here.
    return {
        "income_categories": _live_income(list(categories_service.list_all(conn, user_id))),
        "current_anchor_id": preferences_service.get_income_anchor_category_id(conn, user_id),
    }


def drawer_context(
    conn: sqlite3.Connection, user_id: int, raw_tab: str | None
) -> dict[str, object]:
    """Template context for the Settings page / drawer with ``raw_tab`` active."""
    tab = coerce_tab(raw_tab)
    context: dict[str, object] = {"active_tab": tab}
    if tab == "categories":
        context.update(_categories_context(conn, user_id))
    elif tab == "fx":
        context["fx_rates"] = fx_service.list_recent_rates(conn, limit=_FX_LIMIT)
    else:
        context.update(_prefs_context(conn, user_id))
    return context
