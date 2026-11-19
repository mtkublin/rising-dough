"""INV-7: period windows agree (no income anchor configured -> end-of-month fallback).

budget._resolve_anchor returns the LAST DAY of the month as the exclusive end of the committed
window [None, end) and uses (end - today).days as the daily-spend divisor; account_planned
.resolve_window returns last day + 1 (exclusive). Plant a 5000 expense on the last day (Nov 30)
and compare the DELTA each consumer sees.
"""

from __future__ import annotations

from datetime import date

import harness

from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.repositories import planned as planned_repo
from budget_planner.services import account_planned, budget

U = harness.USER_ID
TODAY = date(2026, 11, 19)
conn = harness.fresh_db()
conn.execute("DELETE FROM user_preferences WHERE key = 'income_anchor_category_id'")  # scratch only


def snapshot() -> tuple[int, int, int]:
    s = budget.month_summary(conn, U, 2026, 11, today=TODAY)
    win = account_planned.resolve_window(conn, U, TODAY)
    net1 = account_planned.planned_net_by_account(conn, U, win).get(1, 0)
    return s.totals.committed_minor + s.totals.unbudgeted_committed_minor, net1, s.days_until_next_income


b0, n0, days = snapshot()
for day in (date(2026, 11, 29), date(2026, 11, 30)):
    planned_repo.create(
        conn,
        U,
        NewPlannedTransaction(operation_date=day, category_id=7, account_id=1, amount=5000, description=str(day)),
    )
    b1, n1, _ = snapshot()
    print(f"item on {day}: budget committed delta={b1 - b0}, account_planned net delta={n1 - n0}")
    harness.check(f"budget counts item on {day}", b1 - b0 == 5000)
    harness.check(f"account_planned counts item on {day}", n1 - n0 == -5000)
    b0, n0 = b1, n1
true_days = (date(2026, 11, 30) - TODAY).days + 1
harness.check(
    "left-per-day divisor == days remaining incl. today..Nov 30",
    days == true_days,
    f"got {days}, inclusive count {true_days}",
)
