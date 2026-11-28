"""Category form parsing (T-Q266): raw form fields to a validated domain command or field errors.

Pure: no I/O. The router passes the submitted strings and either renders the errors or hands the
command to ``services.categories``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from budget_planner.domain import category_colors
from budget_planner.domain.categories import NewCategory, PatchCategory, normalise_color
from budget_planner.domain.enums import Direction
from budget_planner.domain.limits import name_error

_DIRECTIONS_BY_VALUE: Mapping[str, Direction] = MappingProxyType(
    {d.value: d for d in (Direction.INCOME, Direction.EXPENSE)}
)


DEFAULT_COLOUR: Final = "default"
"""``color`` value of the dialog's "default colour" radio. An empty value cannot carry the intent:
FastAPI reads an empty form value as absent, and absent means "leave the colour unchanged"."""


@dataclass(frozen=True)
class ParsedNewCategory:
    """Result of parsing the create form: a command, or per-field errors."""

    command: NewCategory | None
    errors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedCategoryPatch:
    """Result of parsing the edit form: a patch, or per-field errors."""

    patch: PatchCategory | None
    errors: dict[str, str] = field(default_factory=dict)


def validate_direction(value: str) -> Direction | None:
    """Return the direction only if user-pickable.

    T-115 / F1.6: transit + adjustment are reserved for seeded system categories (``Transit``,
    ``Reconciliation``) and must not reach the repository via a user POST.
    """
    return _DIRECTIONS_BY_VALUE.get(value)


def resolve_color_form(color: str | None, clear_color: str | None) -> tuple[str | None, bool]:
    """ADR-0048: return ``(hex_or_none, clear_requested)``.

    ``clear_color`` present means "reset to direction default" and wins over any ``color`` value
    the browser might send. ``color == DEFAULT_COLOUR`` (the dialog's "default colour" radio,
    T-UR13) means the same; an absent ``color`` leaves the colour unchanged.
    Raises ``ValueError`` via ``normalise_color`` on malformed hex.
    """
    if clear_color or color == DEFAULT_COLOUR:
        return None, True
    return normalise_color(color), False


def _name_and_color(
    name: str, color: str | None, clear_color: str | None
) -> tuple[dict[str, str], str | None, bool]:
    errors: dict[str, str] = {}
    if (bad_name := name_error(name)) is not None:
        errors["name"] = bad_name
    resolved: str | None = None
    cleared = False
    try:
        resolved, cleared = resolve_color_form(color, clear_color)
    except ValueError as exc:
        errors["color"] = str(exc)
    return errors, resolved, cleared


def parse_new_category(
    *, name: str, direction: str, color: str | None, clear_color: str | None
) -> ParsedNewCategory:
    """Validate the create form (direction, name, colour)."""
    errors, resolved, _ = _name_and_color(name, color, clear_color)
    parsed_direction = validate_direction(direction)
    if parsed_direction is None:
        errors = {"direction": "invalid direction", **errors}
    if errors or parsed_direction is None:
        return ParsedNewCategory(command=None, errors=errors)
    return ParsedNewCategory(
        command=NewCategory(name=name.strip(), direction=parsed_direction, color=resolved)
    )


def _keeps_stored_colour(color: str | None, stored: str | None) -> bool:
    """True when the posted colour is the dialog's own preselection for ``stored``.

    The dialog preselects the swatch nearest to a stored hue that is none of the ten swatches
    (D11-S). Posting that swatch back is an unchanged save: the stored hue stays, so a plain save
    never recolours a category. Picking another swatch, or the default, is a real change.
    """
    if not color or not stored:
        return False
    # ``color`` is already normalised by the form parser; the DB CHECK constrains ``stored``.
    posted, kept = color.lower(), stored.lower()
    return posted != kept and posted == category_colors.nearest_form_swatch(kept).cat


def parse_category_patch(
    *,
    name: str,
    color: str | None,
    clear_color: str | None,
    stored_color: str | None = None,
) -> ParsedCategoryPatch:
    """Validate the edit form (name, colour); ``stored_color`` is the category's current colour."""
    errors, resolved, cleared = _name_and_color(name, color, clear_color)
    if errors:
        return ParsedCategoryPatch(patch=None, errors=errors)
    if not cleared and _keeps_stored_colour(resolved, stored_color):
        resolved = None
    return ParsedCategoryPatch(
        patch=PatchCategory(name=name.strip(), color=resolved, clear_color=cleared)
    )
