"""Today surface on the handoff markup (``pages/today.html``, T-UR07).

The app renders the handoff's Today markup; ``tests.ui_map.mockup.today`` exposes
the same names against the static handoff (fixed sample rows, no row ids), so one
journey runs on both targets. Row ids (``upcoming-planned-<id>``) and the figure
ids below exist only in the app: the handoff has fixed rows.
"""

from __future__ import annotations

from tests.ui_map.locator import Locator, by_id, role

# The hero heading is the "left to spend per day" label; there is no "Today" h1.
heading = role("heading", "left to spend per day", level=1)
upcoming = by_id("upcoming-list")


def upcoming_planned(planned_id: int) -> Locator:
    return by_id(f"upcoming-planned-{planned_id}")


def upcoming_recurring(rule_id: int) -> Locator:
    return by_id(f"upcoming-recurring-{rule_id}")


# Promote is a link into the promote dialog (a page link without script).
promote = role("link", "promote", exact=True)

# The afford result is one ``<output>`` holding one text run (as the handoff draws it, so the
# glyphs sit at the same sub-pixel positions): per-day and delta share it.
afford_per_day = by_id("afford-result")
afford_delta = by_id("afford-result")

# Every upcoming row in a ``/today/upcoming`` fragment (planned and recurring).
upcoming_rows = role("listitem").inside(upcoming)
promote_all_due = role("button", "promote all due")

hero_per_day = by_id("hero-per-day")  # the hero "left per day" figure
spent_bar = role("img", "percent spent")  # the hero bar: "N percent spent, M percent left"
