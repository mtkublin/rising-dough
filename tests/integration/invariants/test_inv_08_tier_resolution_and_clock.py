# Guard docstrings and teaching messages are prose; long lines are intentional.
"""INV-8: tier resolution parity (8a) and one notion of "today" (8b, Q-031)."""

from __future__ import annotations

import datetime as real_dt
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from budget_planner.domain.budgets import NewBudgetOneOffOverride
from budget_planner.repositories import budgets as budgets_repo
from budget_planner.services import budget

U = 1


def test_8a_resolve_budget_equals_yearly_grid_on_every_cell(seeded: sqlite3.Connection) -> None:
    budgets_repo.set_one_off(
        seeded, U, NewBudgetOneOffOverride(category_id=7, year=2026, month=11, amount=0)
    )
    grid = {r.category_id: r for r in budget.yearly_grid(seeded, U, 2026)}
    bad = [
        (cat_id, m)
        for cat_id, row in grid.items()
        for m in range(1, 13)
        if budget.resolve_budget(seeded, U, cat_id, 2026, m) != row.cells[m - 1].amount_minor
    ]
    assert not bad, bad[:5]


@pytest.mark.xfail(
    strict=True,
    reason="Q-031: host-clock date.today() and the display-timezone date disagree around midnight",
)
def test_8b_display_timezone_today_equals_host_today() -> None:
    frozen_utc = datetime(2026, 11, 19, 23, 30, tzinfo=real_dt.UTC)
    warsaw_today = frozen_utc.astimezone(ZoneInfo("Europe/Warsaw")).date()
    host_today = frozen_utc.astimezone(
        real_dt.UTC
    ).date()  # what date.today() returns on a UTC host
    assert warsaw_today == host_today
