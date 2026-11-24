"""Today surface against the handoff markup (``pages/today.html``).

Same names as ``tests.ui_map.today``. The handoff has fixed sample rows and no
row ids, so the id-parameterised builders return the sample row; handoff-only
differences are noted per name.
"""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, role

# The hero heading is the "left to spend per day" label; there is no "Today" h1.
heading = role("heading", "left to spend per day", level=1)
upcoming = by_id("upcoming-list")  # the app's ``upcoming-root`` has no handoff twin

_SAMPLE_PLANNED = "Annual insurance"  # overdue planned row (promote--planned overlay)
_SAMPLE_RECURRING = "Fixed Costs"  # recurring row (promote--recurring overlay)


def upcoming_planned(planned_id: int) -> Locator:
    return role("listitem", _SAMPLE_PLANNED).inside(upcoming)


def upcoming_recurring(rule_id: int) -> Locator:
    return role("listitem", _SAMPLE_RECURRING).inside(upcoming)


# Handoff promote is a link into the promote overlay page, not a button.
promote = role("link", "promote", exact=True)

# The handoff shows the afford result as one ``<output>``: per-day and delta share it.
afford_per_day = by_id("afford-result")
afford_delta = by_id("afford-result")  # no ``afford-delta`` id in the handoff
upcoming_rows = role("listitem").inside(upcoming)
promote_all_due = role("button", "promote all due")

# Names with no handoff twin (the handoff has fixed sample markup without these ids).
NO_HANDOFF_TWIN: frozenset[str] = frozenset()
hero_per_day = by_id("hero-per-day")
spent_bar = role("img", "percent spent")
