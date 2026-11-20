"""INV-9: "which categories count" is the same set in budget, forecast overlay and monthly budget.

An archived (soft-deleted) expense category that still has a default budget is planted.
budget.month_summary / forecast._planned_budget_per_month iterate live categories only
(list_all(include_deleted=False)); the daily overlay iterates directions_by_cat built with
include_deleted=True. The two Forecast outputs (daily series vs monthly table) then disagree.
"""

from __future__ import annotations

from datetime import date

import harness

from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.repositories import budgets as budgets_repo, categories as categories_repo
from budget_planner.services import budget, forecast

U = harness.USER_ID
TODAY = date(2026, 11, 19)
conn = harness.fresh_db()

ARCHIVED = 25  # "Bank Fees #17", deleted_at set in demo
budgets_repo.set_default(conn, U, NewBudgetDefault(category_id=ARCHIVED, amount=100_000))
cats = {c.id: c.direction for c in categories_repo.list_all(conn, U, include_deleted=True)}

overlay = forecast._collect_budget_overlay(conn, U, TODAY, date(2026, 11, 30), cats, 1)
overlay_total = -sum(e.amount_minor for e in overlay)
monthly = forecast._planned_budget_per_month(conn, U, TODAY, 1)
monthly_total = monthly[date(2026, 11, 1)]
summary = budget.month_summary(conn, U, 2026, 11, today=TODAY)
print({"overlay (daily series) total": overlay_total, "monthly planned_budget": monthly_total,
       "budget summary budgeted_minor": summary.totals.budgeted_minor})

# same query with the archived budget removed -> the delta is what each path attributes to it
conn.execute("DELETE FROM budget_defaults WHERE category_id = ?", (ARCHIVED,))
overlay2 = -sum(e.amount_minor for e in forecast._collect_budget_overlay(conn, U, TODAY, date(2026, 11, 30), cats, 1))
monthly2 = forecast._planned_budget_per_month(conn, U, TODAY, 1)[date(2026, 11, 1)]
d_overlay, d_monthly = overlay_total - overlay2, monthly_total - monthly2
print({"archived-category budget effect: overlay": d_overlay, "monthly": d_monthly})
harness.check("archived category budget affects both forecast paths equally", d_overlay == d_monthly)
