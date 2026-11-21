# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""INV-9: "which categories count" is one set across budget, forecast overlay and monthly budget (Q-030).

An archived expense category that still has a default budget is planted; the daily overlay (``include_deleted=True``)
and the monthly table (live categories only) must attribute the same amount to it.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.repositories import budgets as budgets_repo, categories as categories_repo
from budget_planner.services import forecast

U = 1
TODAY = date(2026, 11, 19)
ARCHIVED = 25  # "Bank Fees #17", archived in the demo data


@pytest.mark.xfail(
    strict=True,
    reason="Q-030: the daily overlay includes archived categories, the monthly table does not",
)
def test_archived_category_budget_affects_both_forecast_paths_equally(
    seeded: sqlite3.Connection,
) -> None:
    budgets_repo.set_default(seeded, U, NewBudgetDefault(category_id=ARCHIVED, amount=100_000))
    cats = {c.id: c.direction for c in categories_repo.list_all(seeded, U, include_deleted=True)}
    end = date(2026, 11, 30)
    month = date(2026, 11, 1)

    def paths() -> tuple[int, int]:
        overlay = -sum(
            e.amount_minor for e in forecast._collect_budget_overlay(seeded, U, TODAY, end, cats, 1)
        )
        return overlay, forecast._planned_budget_per_month(seeded, U, TODAY, 1)[month]

    overlay_with, monthly_with = paths()
    seeded.execute("DELETE FROM budget_defaults WHERE category_id = ?", (ARCHIVED,))
    overlay_without, monthly_without = paths()
    assert overlay_with - overlay_without == monthly_with - monthly_without
