# Guard docstrings and teaching messages are prose; long lines are intentional.
"""INV-8: tier resolution parity (8a) and one notion of "today" (8b, Q-031)."""

from __future__ import annotations

import datetime as real_dt
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from budget_planner import clock
from budget_planner.clock import DEFAULT_DISPLAY_TIMEZONE
from budget_planner.config import Settings
from budget_planner.domain.budgets import NewBudgetOneOffOverride
from budget_planner.repositories import budgets as budgets_repo
from budget_planner.services import budget
from budget_planner.web.deps import get_today

U = 1


def test_8a_resolve_budget_equals_yearly_grid_on_every_cell(seeded: sqlite3.Connection) -> None:
    budgets_repo.set_one_off(
        seeded, U, NewBudgetOneOffOverride(category_id=7, year=2026, month=11, amount=0)
    )
    grid = {
        r.category_id: r
        for r in budget.yearly_grid(seeded, U, 2026, display_timezone=DEFAULT_DISPLAY_TIMEZONE)
    }
    bad = [
        (cat_id, m)
        for cat_id, row in grid.items()
        for m in range(1, 13)
        if budget.resolve_budget(seeded, U, cat_id, 2026, m) != row.cells[m - 1].amount_minor
    ]
    assert not bad, bad[:5]


def test_8b_every_surface_shares_the_display_timezone_today() -> None:
    """Q-031 / ADR-0140: around Warsaw midnight on a UTC host every surface sees one date."""
    settings = Settings(display_timezone="Europe/Warsaw")
    frozen_utc = datetime(2026, 11, 19, 23, 30, tzinfo=real_dt.UTC)
    warsaw_today = frozen_utc.astimezone(ZoneInfo("Europe/Warsaw")).date()

    with clock.frozen(frozen_utc):
        assert clock.today_local(settings) == warsaw_today
        assert get_today(settings) == warsaw_today
    assert warsaw_today != frozen_utc.date()
