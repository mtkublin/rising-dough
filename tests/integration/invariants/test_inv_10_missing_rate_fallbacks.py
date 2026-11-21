# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""INV-10: one missing FX rate (EUR to PLN, nothing cached, network down) degrades the same way everywhere (Q-007)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.repositories import accounts as accounts_repo
from budget_planner.services import budget, forecast
from budget_planner.web import today_data
from tests.integration.invariants.conftest import offline_http

U = 1


@pytest.mark.xfail(
    strict=True,
    reason="Q-007: budget and today degrade silently to the native amount, forecast raises (HTTP 500)",
)
def test_missing_rate_degrades_consistently(seeded: sqlite3.Connection) -> None:
    today = date.today()  # noqa: DTZ011
    eur = accounts_repo.create(
        seeded, U, NewAccount(name="EUR", currency="EUR", opening_balance=100_000)
    ).id
    outcomes: dict[str, str] = {}
    converted = budget.base_amount_converter(seeded, U, today=today)(eur, 100_000)
    outcomes["budget"] = f"returns {converted}"
    _, _, fortune_base = today_data.collect_account_rows(seeded, U, "PLN")
    outcomes["today"] = f"returns {fortune_base}"
    try:
        forecast.forecast(
            seeded,
            U,
            http=offline_http(),
            today=today,
            horizon_days=0,
            base_currency="PLN",
            include_budget_overlay=False,
        )
        outcomes["forecast"] = "returns ok"
    except Exception as exc:
        outcomes["forecast"] = f"raises {type(exc).__name__}"
    assert len({v.split()[0] for v in outcomes.values()}) == 1, outcomes
