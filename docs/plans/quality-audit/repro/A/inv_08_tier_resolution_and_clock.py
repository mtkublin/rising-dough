"""INV-8a: resolve_budget() == yearly_grid() cell for every (category, month) (tier resolution).
INV-8b: the app's notion of "today" is one value: display-timezone date vs date.today().

8b simulates a host running in UTC at 2026-11-19 23:30 UTC == 2026-11-20 00:30 Europe/Warsaw:
routers using datetime.now(ZoneInfo(display_timezone)) say Nov 20, code using date.today() says Nov 19.
"""

from __future__ import annotations

import datetime as real_dt
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import harness

from budget_planner.domain.budgets import NewBudgetOneOffOverride
from budget_planner.repositories import budgets as budgets_repo
from budget_planner.services import budget

U = harness.USER_ID
conn = harness.fresh_db()

harness.banner("8a tier resolution parity (2026, incl. one-off = 0)")
budgets_repo.set_one_off(conn, U, NewBudgetOneOffOverride(category_id=7, year=2026, month=11, amount=0))
grid = {r.category_id: r for r in budget.yearly_grid(conn, U, 2026)}
bad = []
for cat_id, row in grid.items():
    for m in range(1, 13):
        if budget.resolve_budget(conn, U, cat_id, 2026, m) != row.cells[m - 1].amount_minor:
            bad.append((cat_id, m))
harness.check("resolve_budget == yearly_grid on all cells", not bad, str(bad[:5]))

harness.banner("8b 'today' under a UTC host at 23:30 UTC (= 00:30 Warsaw next day)")
frozen_utc = datetime(2026, 11, 19, 23, 30, tzinfo=real_dt.UTC)
warsaw_today = frozen_utc.astimezone(ZoneInfo("Europe/Warsaw")).date()
host_today = frozen_utc.astimezone(real_dt.UTC).date()  # what date.today() returns on a UTC host
print({"router-style (display tz)": warsaw_today, "date.today()-style (host UTC)": host_today})
harness.check("both notions of today agree", warsaw_today == host_today)

import re  # noqa: E402
from pathlib import Path  # noqa: E402

root = Path(harness.REPO_ROOT) / "src" / "budget_planner"
tzaware, naive = [], []
for p in root.rglob("*.py"):
    for i, line in enumerate(p.read_text().splitlines(), 1):
        if "ZoneInfo(settings.display_timezone)" in line and "now(" in line:
            tzaware.append(f"{p.relative_to(root)}:{i}")
        if re.search(r"\b(dt\.)?date\.today\(\)", line) and "today_d" not in line:
            naive.append(f"{p.relative_to(root)}:{i}")
print("display-tz 'today' sites:", len(tzaware))
print("host-clock date.today() sites:", len(naive))
print("\n".join(sorted(naive)))
