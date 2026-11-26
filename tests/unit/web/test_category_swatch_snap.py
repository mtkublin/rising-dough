"""Edit-category dialog snaps a stored hue to the nearest dialog swatch (D11-S, ADR-0107)."""

from __future__ import annotations

import datetime as dt

from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.web.settings_view import category_form_view

_NOW = dt.datetime(2026, 10, 31, tzinfo=dt.UTC)


def _category(color: str | None) -> Category:
    return Category(
        id=7,
        user_id=1,
        name="Takeaway",
        direction=Direction.EXPENSE,
        is_system=False,
        color=color,
        created_at=_NOW,
        updated_at=_NOW,
        deleted_at=None,
    )


def _checked(color: str | None) -> list[str]:
    view = category_form_view(_category(color))
    return [s.name for s in view.swatches if s.checked]


def test_board_orange_shows_tangerine_in_the_dialog() -> None:
    view = category_form_view(_category("#ff9f43"))
    assert [s.name for s in view.swatches if s.checked] == ["tangerine"]
    assert view.preview_color == "tangerine"
    assert view.default_checked is False


def test_a_swatch_hue_selects_itself() -> None:
    assert _checked("#f97316") == ["tangerine"]


def test_no_colour_selects_the_default_and_no_swatch() -> None:
    view = category_form_view(_category(None))
    assert [s for s in view.swatches if s.checked] == []
    assert view.default_checked is True


def test_new_category_selects_the_default() -> None:
    view = category_form_view(None)
    assert [s for s in view.swatches if s.checked] == []
    assert view.default_checked is True
