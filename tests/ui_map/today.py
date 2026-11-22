"""Today surface."""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, by_testid, role

heading = role("heading", "Today", level=1)
upcoming = by_id("upcoming-root")


def upcoming_planned(planned_id: int) -> Locator:
    return by_id(f"upcoming-planned-{planned_id}")


def upcoming_recurring(rule_id: int) -> Locator:
    return by_id(f"upcoming-recurring-{rule_id}")


promote = role("button", "Promote")

afford_per_day = by_testid("afford-per-day")
afford_delta = by_testid("afford-delta")

# Every upcoming row in an ``/today/upcoming`` fragment (planned and recurring).
upcoming_rows = by_id("upcoming-", prefix=True)

add_planned = role("button", "+ Planned")
add_recurring = role("button", "+ Recurring")
promote_all_due = role("button", "Promote all due")
confirm_promote = role("button", "Confirm")

hero_per_day = by_testid("hero-per-day")  # T-Q278: the hero "left per day" figure
spent_bar = role("progressbar", "Spent")
