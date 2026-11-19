"""C-06 next_due drift with blank day_of_month; C-13 occurrences before start_date."""

import datetime as dt

import _common  # noqa: F401

from budget_planner.domain.enums import Cadence
from budget_planner.services.recurring import advance_next_due, generate_occurrences
from budget_planner.domain.recurring import RecurringRule  # noqa: F401

# C-06: monthly rule starting Jan 31, blank day-of-month; walk 5 advances
d = dt.date(2026, 1, 31)
seq = [d]
for _ in range(5):
    d = advance_next_due(Cadence.MONTHLY, d, None, None, None)
    seq.append(d)
print("C-06 blank dom, start 2026-01-31:", [x.isoformat() for x in seq])
d = dt.date(2026, 1, 31)
seq = [d]
for _ in range(5):
    d = advance_next_due(Cadence.MONTHLY, d, None, 31, None)
    seq.append(d)
print("C-06 explicit dom=31 (control)  :", [x.isoformat() for x in seq])

# C-13: rule starting 2026-01-20 with day_of_month=5 -> occurrence before start?
from budget_planner.services.recurring import _build_lookup_stub  # noqa: E402

stub = _build_lookup_stub(
    cadence=Cadence.MONTHLY, start_date=dt.date(2026, 1, 20), end_date=None, day_of_month=5, month_of_year=None
)
occ = generate_occurrences(stub, dt.date(2026, 1, 1), dt.date(2026, 3, 31))
print("C-13 start=2026-01-20 dom=5 occurrences:", [o.occurrence_date.isoformat() for o in occ])
