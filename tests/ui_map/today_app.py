"""App-only Today names with no handoff twin yet (T-UT04b).

``tests.ui_map.today`` must stay a subset of ``tests.ui_map.mockup.today``
(``test_variant_defines_every_app_name``). The names here have no handoff
counterpart, so they live apart; fold them into ``today.py`` together with
their mockup twins when the Today redesign wires them.
"""

from __future__ import annotations

from tests.ui_map.locator import by_id, by_testid, role

afford_per_day = by_testid("afford-per-day")
afford_delta = by_testid("afford-delta")

# Every upcoming row in an ``/today/upcoming`` fragment (planned and recurring).
upcoming_rows = by_id("upcoming-", prefix=True)

# --- T-UT08a: existing e2e journeys ---
add_planned = role("button", "+ Planned")
add_recurring = role("button", "+ Recurring")
promote_all_due = role("button", "Promote all due")
confirm_promote = role("button", "Confirm")
