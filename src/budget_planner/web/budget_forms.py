"""Budget form parsing (T-Q266): submitted strings to an override command or an error message."""

from __future__ import annotations

from dataclasses import dataclass

from budget_planner.domain.budgets import (
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
    valid_month,
)
from budget_planner.domain.money import parse_amount_minor
from budget_planner.services.budget_rules import OverrideCommand
from budget_planner.web.params import parse_int

_TIERS = frozenset({"recurring", "one-off", "default"})


@dataclass(frozen=True)
class ParsedOverride:
    """A command, or the 422 message explaining why the form was rejected."""

    command: OverrideCommand | None
    error: str | None = None


def non_negative_amount(raw: str, currency: str) -> int | None:
    """Amount text to minor units; ``None`` when invalid or negative."""
    minor = parse_amount_minor(raw, currency)
    return None if minor is None or minor < 0 else minor


def parse_override(
    category_id: int, *, tier: str, month: str, year: str, amount: str, currency: str
) -> ParsedOverride:
    """Validate the Override slide-over form (ADR-0031 section 2)."""
    if tier not in _TIERS:
        return ParsedOverride(None, "invalid tier")
    minor = non_negative_amount(amount, currency) if amount.strip() else 0
    if minor is None:
        return ParsedOverride(None, "invalid amount")
    if tier == "default":
        return ParsedOverride(NewBudgetDefault(category_id=category_id, amount=minor))
    return _parse_dated(category_id, tier=tier, month=month, year=year, minor=minor)


def _parse_dated(
    category_id: int, *, tier: str, month: str, year: str, minor: int
) -> ParsedOverride:
    """Recurring (month) or one-off (year and month) override."""
    parsed_month = parse_int(month, maximum=None)
    if parsed_month is None or not valid_month(parsed_month):
        return ParsedOverride(None, "invalid month")
    if tier == "recurring":
        return ParsedOverride(
            NewBudgetRecurringOverride(category_id=category_id, month=parsed_month, amount=minor)
        )
    parsed_year = parse_int(year, maximum=None)
    if parsed_year is None:
        return ParsedOverride(None, "invalid year")
    return ParsedOverride(
        NewBudgetOneOffOverride(
            category_id=category_id, year=parsed_year, month=parsed_month, amount=minor
        )
    )
