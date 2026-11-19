"""T-Q06 repro: recurrence boundary bugs (pure functions, no DB).

Run: uv run python docs/plans/quality-audit/repro/C/repro_recurrence_boundaries.py
"""

from __future__ import annotations

import datetime as dt

from budget_planner.domain.enums import Cadence
from budget_planner.domain.recurring import RecurringRule
from budget_planner.services.recurring import advance_next_due, generate_occurrences

D = dt.date


def rule(cadence: Cadence, start: dt.date, dom: int | None, moy: int | None = None) -> RecurringRule:
    now = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    return RecurringRule(
        id=1, user_id=1, cadence=cadence, start_date=start, end_date=None, category_id=1,
        account_id=1, dest_account_id=None, default_amount=100, default_description=None,
        day_of_month=dom, month_of_year=moy, active=True, next_due=start,
        last_promoted_date=None, amount_formula=None, created_at=now, updated_at=now,
        deleted_at=None,
    )  # fmt: skip


print("== R1: anchor drift after a clamped month (day_of_month=None) ==")
r = rule(Cadence.MONTHLY, D(2026, 1, 31), None)
canon = [o.occurrence_date.isoformat() for o in generate_occurrences(r, D(2026, 1, 1), D(2026, 6, 30))]
print("canonical schedule      :", canon)
nd = D(2026, 1, 31)
walk = []
for _ in range(5):
    nd = advance_next_due(Cadence.MONTHLY, nd, None, None, None)  # type: ignore[assignment]
    walk.append(nd.isoformat())
print("next_due walk (promote) :", walk)
print("DRIFT" if walk[1:] != canon[2:6] else "ok")

print("\n== R2: yearly Feb-29 anchor never recovers after promote ==")
nd = D(2028, 2, 29)
walk = []
for _ in range(5):
    nd = advance_next_due(Cadence.YEARLY, nd, None, None, None)  # type: ignore[assignment]
    walk.append(nd.isoformat())
r = rule(Cadence.YEARLY, D(2028, 2, 29), None)
canon = [o.occurrence_date.isoformat() for o in generate_occurrences(r, D(2028, 1, 1), D(2033, 12, 31))]
print("canonical schedule :", canon)
print("next_due walk      :", walk)

print("\n== R3: occurrences emitted BEFORE rule.start_date (day_of_month < start.day) ==")
r = rule(Cadence.MONTHLY, D(2026, 3, 25), 20)
got = [o.occurrence_date.isoformat() for o in generate_occurrences(r, D(2026, 1, 1), D(2026, 5, 31))]
print("start_date=2026-03-25 day_of_month=20 ->", got)
print("BUG: occurrence before start_date" if any(g < "2026-03-25" for g in got) else "ok")
