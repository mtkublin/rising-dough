# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""INV-9: "which categories count" is one set across budget, forecast overlay and monthly budget (Q-030).

An archived expense category with a default budget is planted; the daily overlay and the monthly table must
attribute the same amount to it: nothing from its archive month onward, the full budget before it (ADR-0136
amendment 2026-11-22, T-Q279).
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.config import get_settings
from budget_planner.services import forecast, forecast_overlay, fx as fx_svc

U = 1
TODAY = date(2026, 11, 19)
ARCHIVED = 25  # "Bank Fees #17", archived in the demo data


@pytest.mark.parametrize(
    ("archived_at", "expected"),
    [
        ("2026-11-05T10:00:00.000Z", 0),  # archive month == the forecast month: reserves nothing
        ("2026-12-05T10:00:00.000Z", 100_000),  # archived later: November still reserves it
    ],
)
def test_archived_category_budget_affects_both_forecast_paths_equally(
    seeded: sqlite3.Connection, archived_at: str, expected: int
) -> None:
    seeded.execute(
        "INSERT INTO budget_defaults(user_id, category_id, amount) VALUES (?, ?, ?)",
        (U, ARCHIVED, 100_000),
    )
    seeded.execute("UPDATE categories SET deleted_at = ? WHERE id = ?", (archived_at, ARCHIVED))
    end = date(2026, 11, 30)
    month = date(2026, 11, 1)

    fx = fx_svc.converter_for(seeded, get_settings(), TODAY)

    def paths() -> tuple[int, int]:
        overlay = -sum(
            e.amount_minor
            for e in forecast_overlay.collect_budget_overlay(
                seeded,
                U,
                today=TODAY,
                end_date=end,
                primary_account_id=1,
                fx=fx,
            )
        )
        return overlay, forecast._planned_budget_per_month(seeded, U, TODAY, 1, fx=fx)[month]

    overlay_with, monthly_with = paths()
    seeded.execute("DELETE FROM budget_defaults WHERE category_id = ?", (ARCHIVED,))
    overlay_without, monthly_without = paths()
    assert overlay_with - overlay_without == monthly_with - monthly_without
    # Archived == soft-deleted here (``categories.deleted_at``); the archive month onward reserves nothing, in both paths.
    assert overlay_with - overlay_without == expected
