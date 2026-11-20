"""Today surface."""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, role

heading = role("heading", "Today", level=1)
upcoming = by_id("upcoming-root")


def upcoming_planned(planned_id: int) -> Locator:
    return by_id(f"upcoming-planned-{planned_id}")


def upcoming_recurring(rule_id: int) -> Locator:
    return by_id(f"upcoming-recurring-{rule_id}")


promote = role("button", "Promote")
