"""Settings page view models (T-UR13, ADR-0107, ADR-0136, ADR-0139).

Pure: turns the settings service context (``services.settings_drawer``), categories and cached FX
rates into the values the new-shell templates print. No I/O, no clock. Directions come from the
service's own grouping; wording from ``view_models.direction_label``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Final

from fastapi import Response

from budget_planner.domain import category_colors
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.domain.fx import FxRate
from budget_planner.web.http_headers import HTML_MEDIA_TYPE
from budget_planner.web.view_models import direction_label

_FORM_SWATCH_NAMES: Final[tuple[str, ...]] = (
    "red",
    "tangerine",
    "yellow",
    "leaf",
    "green",
    "jade",
    "sky",
    "indigo",
    "purple",
    "magenta",
)
_PRESET_HEX: Final[Mapping[str, str]] = MappingProxyType(
    {preset.name: preset.cat for preset in category_colors.PRESETS}
)
_HEX_COLOUR: Final = re.compile(r"#[0-9a-fA-F]{6}")
_GROUPS: Final[tuple[tuple[str, str, str], ...]] = (
    ("expense", "Expense", "expense_categories"),
    ("income", "Income", "income_categories"),
    ("system", "System", "system_categories"),
)


def category_not_found() -> Response:
    """The 404 the category dialog routes answer for a missing or foreign category."""
    return Response(status_code=404, content="category: not found", media_type=HTML_MEDIA_TYPE)


@dataclass(frozen=True, slots=True)
class CategoryRowView:
    """One category row of the settings list (handoff ``rows/category-row``)."""

    id: int
    name: str
    color_name: str
    colour_text: str
    is_system: bool


@dataclass(frozen=True, slots=True)
class CategoryGroupView:
    """A settings list section: Expense, Income or System, with its count."""

    key: str
    title: str
    caption: str
    count: int
    rows: tuple[CategoryRowView, ...]


def category_row_view(category: Category) -> CategoryRowView:
    """Row values; ``color_name`` is empty for the neutral default colour."""
    colour = category_colors.category_color(category.color)
    return CategoryRowView(
        id=category.id,
        name=category.name,
        color_name=colour.name or "",
        colour_text="custom colour" if category.color else "default colour",
        is_system=category.is_system,
    )


def _members(context: Mapping[str, object], key: str) -> list[Category]:
    value = context.get(key)
    return [c for c in value if isinstance(c, Category)] if isinstance(value, list) else []


def category_groups(context: Mapping[str, object]) -> tuple[CategoryGroupView, ...]:
    """Expense, Income and System sections (empty ones omitted); archived rows are never listed."""
    groups = tuple((key, title, _members(context, source)) for key, title, source in _GROUPS)
    return tuple(
        CategoryGroupView(
            key=key,
            title=title,
            caption=f"{title} categories",
            count=len(members),
            rows=tuple(category_row_view(c) for c in members),
        )
        for key, title, members in groups
        if members
    )


def category_color_rules(categories: Sequence[Category]) -> str:
    """Style rules for stored hues outside the presets (one per distinct hue)."""
    rules = (category_colors.category_color(c.color).rule for c in categories if c.color)
    return "".join(dict.fromkeys(rule for rule in rules if rule))


@dataclass(frozen=True, slots=True)
class SwatchView:
    """One colour swatch of the category dialog."""

    name: str
    hex: str
    checked: bool


@dataclass(frozen=True, slots=True)
class CategoryFormView:
    """Values of the new / edit category dialog."""

    title: str
    name: str
    direction_text: str
    expense_checked: bool
    income_checked: bool
    default_checked: bool
    swatches: tuple[SwatchView, ...]
    preview_color: str
    usage_text: str | None


def _picked_direction(category: Category | None, direction: str | None) -> Direction:
    if category is not None:
        return category.direction
    return Direction.INCOME if direction == Direction.INCOME.value else Direction.EXPENSE


def _picked_color(category: Category | None, color: str | None) -> str:
    if color is None and category is not None:
        return category.color or ""
    return color or ""


def category_form_view(
    category: Category | None,
    *,
    name: str | None = None,
    direction: str | None = None,
    color: str | None = None,
    usage_text: str | None = None,
) -> CategoryFormView:
    """Dialog values: the stored category first, submitted values (422 re-render) over them."""
    picked = _picked_direction(category, direction)
    picked_color = _picked_color(category, color)
    lowered = picked_color.lower()
    valid = _HEX_COLOUR.fullmatch(picked_color) is not None
    preview = category_colors.category_color(picked_color if valid else None)
    stored_name = category.name if category else ""
    return CategoryFormView(
        title=f"edit category · {category.name}" if category else "new category",
        name=stored_name if name is None else name,
        direction_text=direction_label(picked),
        expense_checked=picked is Direction.EXPENSE,
        income_checked=picked is Direction.INCOME,
        default_checked=not picked_color,
        swatches=tuple(
            SwatchView(name=swatch, hex=_PRESET_HEX[swatch], checked=_PRESET_HEX[swatch] == lowered)
            for swatch in _FORM_SWATCH_NAMES
        ),
        preview_color=preview.name or "",
        usage_text=usage_text,
    )


@dataclass(frozen=True, slots=True)
class FxRateRow:
    """One cached rate: pair text, as-of date, the rate as cached."""

    pair: str
    as_of: date
    rate_text: str


def fx_rate_rows(rates: Sequence[FxRate]) -> tuple[FxRateRow, ...]:
    """Cached rates as stored (``EUR → PLN``, the rate exactly as cached)."""
    return tuple(
        FxRateRow(
            pair=f"{r.from_ccy} → {r.to_ccy}",
            as_of=r.date,
            rate_text=str(r.rate),  # as stored; rate formatting belongs to services/fx
        )
        for r in rates
    )


def settings_page_context(raw: Mapping[str, object]) -> dict[str, object]:
    """Template context of a settings page: the service context plus its view models."""
    context = dict(raw)
    categories = context.get("categories")
    if isinstance(categories, list):
        context["groups"] = category_groups(context)
        context["color_rules"] = category_color_rules(
            [c for c in categories if isinstance(c, Category)]
        )
    rates = context.get("fx_rates")
    if isinstance(rates, list):
        context["fx_rows"] = fx_rate_rows([r for r in rates if isinstance(r, FxRate)])
    return context
