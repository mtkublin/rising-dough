# Guard docstrings and teaching messages are prose; long lines are intentional.
"""INV-2: fortune / balance agree across implementations in base currency (Q-009)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget_planner.config import get_settings
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.fx import NewFxRate
from budget_planner.repositories import accounts as accounts_repo, fx as fx_repo
from budget_planner.services import balance, forecast, fortune
from budget_planner.web import today_data
from tests.integration.invariants.conftest import offline_http

U = 1
ORACLE = """
SELECT a.opening_balance + COALESCE((
  SELECT SUM(CASE
     WHEN t.account_id = a.id AND c.direction = 'income' THEN t.amount
     WHEN t.account_id = a.id AND c.direction = 'expense' THEN -t.amount
     WHEN t.account_id = a.id AND c.direction = 'transit' THEN -t.amount
     WHEN t.account_id = a.id AND c.direction = 'adjustment' THEN t.amount
     WHEN t.dest_account_id = a.id AND c.direction = 'transit' THEN t.amount
     ELSE 0 END)
  FROM transactions t JOIN categories c ON c.id = t.category_id
  WHERE t.deleted_at IS NULL AND t.operation_date <= ?
    AND (t.account_id = a.id OR t.dest_account_id = a.id)), 0)
FROM accounts a WHERE a.id = ?
"""


def derived_matches_oracle(conn: sqlite3.Connection, today: date) -> bool:
    return all(
        balance.derive_balance(conn, U, a.id)
        == conn.execute(ORACLE, (today.isoformat(), a.id)).fetchone()[0]
        for a in accounts_repo.list_all(conn, U)
    )


def totals(conn: sqlite3.Connection, today: date) -> dict[str, int]:
    s = get_settings()
    fortune_result = fortune.compute_fortune(conn, U, s)
    _, _, fortune_base = today_data.collect_account_rows(conn, U, s.base_currency)
    series = forecast.forecast(
        conn, U, offline_http(), today, 0, s.base_currency, include_budget_overlay=False
    )
    return {
        "fortune.net_base": fortune_result.net_base,
        "today_data.fortune_base": fortune_base,
        "forecast.day0": series.days[0].totals_base_minor,
    }


def test_derive_balance_equals_sql_oracle(seeded: sqlite3.Connection) -> None:
    assert derived_matches_oracle(seeded, date.today())  # noqa: DTZ011


def test_pln_only_demo_totals_agree(seeded: sqlite3.Connection) -> None:
    t = totals(seeded, date.today())  # noqa: DTZ011
    assert t["fortune.net_base"] == t["today_data.fortune_base"] == t["forecast.day0"]


@pytest.mark.xfail(
    strict=True,
    reason="Q-009: fortune.net_base sums native amounts, forecast and today_data convert",
)
def test_foreign_currency_account_agrees_across_fortune_and_forecast(
    seeded: sqlite3.Connection,
) -> None:
    today = date.today()  # noqa: DTZ011
    accounts_repo.create(
        seeded, U, NewAccount(name="EUR Wallet", currency="EUR", opening_balance=100_000)
    )
    fx_repo.upsert_rate(
        seeded, NewFxRate(date=today, from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.30"))
    )
    t = totals(seeded, today)
    assert t["fortune.net_base"] == t["today_data.fortune_base"] == t["forecast.day0"], t
