# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""INV-10: one missing FX rate (EUR to PLN, nothing cached) degrades the same way everywhere (Q-007, ADR-0139)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from budget_planner import clock
from budget_planner.config import Settings, get_settings
from budget_planner.domain.accounts import NewAccount
from budget_planner.repositories import accounts as accounts_repo
from budget_planner.services import budget, forecast, fx
from budget_planner.web import today_data

U = 1


def test_missing_rate_degrades_consistently(seeded: sqlite3.Connection) -> None:
    today = clock.today_local(Settings())
    eur = accounts_repo.create(
        seeded, U, NewAccount(name="EUR", currency="EUR", opening_balance=100_000)
    ).id
    converter = fx.converter_for(seeded, get_settings(), today)
    surfaces: dict[str, Callable[[], object]] = {
        "budget": lambda: budget.planned_base_amounts(seeded, U, today=today)(eur, 100_000),
        "today": lambda: today_data.collect_account_rows(seeded, U, converter),
        "forecast": lambda: forecast.forecast(
            seeded, U, converter, today, 0, include_budget_overlay=False
        ),
    }
    outcomes: dict[str, str] = {}
    for name, call in surfaces.items():
        try:
            call()
            outcomes[name] = "returns"
        except Exception as exc:
            outcomes[name] = type(exc).__name__
    assert set(outcomes.values()) == {"FxUnavailableError"}, outcomes
