"""Override dialog form parsing (T-UR11b): submitted strings to a removal or a 422 field message.

The save form is parsed by ``budget_forms.parse_override``; this module adds what the dialogs
need around it: the human message and field of each rejection, the scope a dialog opens on,
the month a dialog shows again after a bad submission, and the remove confirm's form.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Final

from budget_planner.web import plan_year_view
from budget_planner.web.params import MAX_YEAR, MIN_YEAR, parse_int

MONTHS_IN_YEAR: Final = 12
YEAR_ORIGIN: Final = "year"  # the year grid's inline editor posts this: no default tier from there

_REJECTIONS: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        "invalid tier": ("tier", "choose where the override applies"),
        "invalid amount": ("amount", "enter an amount of 0 or more"),
        "invalid month": ("month", "pick a month from 1 to 12"),
        "invalid year": ("year", "enter a year"),
    }
)
_AMOUNT_FALLBACK: Final = ("amount", "enter a valid amount")


def rejection(error: str | None) -> tuple[str, str]:
    """``(field, human message)`` of a ``parse_override`` error string."""
    return _REJECTIONS.get(error or "", _AMOUNT_FALLBACK)


def scope(raw: str | None) -> str:
    """The scope radio a dialog opens on; anything unknown means this month only."""
    return raw if raw in plan_year_view.TIERS else plan_year_view.TIER_ONE_OFF


def shown_target(
    category_id: int, category_name: str, *, year: str, month: str, today: date
) -> plan_year_view.OverrideTarget:
    """The month a dialog shows again after a rejected submission (today's when unreadable)."""
    return plan_year_view.OverrideTarget(
        category_id,
        category_name,
        parse_int(year, minimum=MIN_YEAR, maximum=MAX_YEAR) or today.year,
        parse_int(month, minimum=1, maximum=MONTHS_IN_YEAR) or today.month,
    )


@dataclass(frozen=True, slots=True)
class ParsedRemoval:
    """A removal (``month``, and ``year`` for a one-off) or the field messages that refuse it."""

    month: int | None
    year: int | None
    errors: Mapping[str, str]


def parse_removal(tier: str, month: str, year: str) -> ParsedRemoval:
    """Validate the remove confirm; a recurring removal carries no year."""
    one_off = tier == plan_year_view.TIER_ONE_OFF
    errors: dict[str, str] = {}
    if not one_off and tier != plan_year_view.TIER_RECURRING:
        errors["tier"] = _REJECTIONS["invalid tier"][1]
    parsed_month = parse_int(month, minimum=1, maximum=MONTHS_IN_YEAR)
    if parsed_month is None:
        errors["month"] = _REJECTIONS["invalid month"][1]
    parsed_year = parse_int(year, minimum=MIN_YEAR, maximum=MAX_YEAR) if one_off else None
    if one_off and parsed_year is None:
        errors["year"] = _REJECTIONS["invalid year"][1]
    return ParsedRemoval(parsed_month, parsed_year, MappingProxyType(errors))
