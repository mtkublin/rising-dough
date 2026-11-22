"""T-Q234: query-count budgets for /accounts, /forecast and /plan?tab=forecast.

World: ``N`` accounts (PLN, EUR, USD), ``R`` monthly rules, planned rows, ~17 posted
transactions per account, budgets (default + one-off) and FX rates. Each budget must hold
at BOTH the small (3 accounts / 3 rules) and large (12 / 12) world, i.e. it is O(1) in the
number of accounts and rules.

Statements per request measured BEFORE T-Q234 (``assert_max_queries`` counter, same world):

    route                 small (3/3)   large (12/12)
    /accounts                     584            2303
    /forecast                     771            1137
    /plan?tab=forecast            772            1138

AFTER T-Q234 (merged with the FX-converting spent of T-Q213): /accounts 19 and /forecast 64
(/plan 65) at both sizes. Budgets below
carry headroom (about +30 percent) so unrelated small changes do not flap the test.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from budget_planner.clock import DEFAULT_DISPLAY_TIMEZONE
from budget_planner.config import Settings, get_settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault, NewBudgetOneOffOverride
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    fx as fx_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as txn_repo,
)
from budget_planner.services import (
    balance as balance_svc,
    budget as budget_svc,
    budget_batch,
    forecast as forecast_svc,
    fx as fx_svc,
)
from tests.query_counting import make_assert_max_queries

_USER = 1
_CURRENCIES = ("PLN", "EUR", "USD")
TODAY = date(2026, 11, 21)

_ACCOUNTS_BUDGET = 25
_FORECAST_BUDGET = 85


def seed_world(
    conn: sqlite3.Connection, accounts: int, rules: int, today: date = TODAY
) -> list[int]:
    """Deterministic world; returns the account ids."""
    for ccy in ("EUR", "USD"):
        fx_repo.upsert_rate(
            conn,
            NewFxRate(
                date=today - timedelta(days=365), from_ccy=ccy, to_ccy="PLN", rate=Decimal("4.30")
            ),
        )
    income = categories_repo.create(
        conn, _USER, NewCategory(name="Pay", direction=Direction.INCOME)
    ).id
    expense_ids = [
        categories_repo.create(
            conn, _USER, NewCategory(name=f"Food{i}", direction=Direction.EXPENSE)
        ).id
        for i in range(3)
    ]
    for i, cat in enumerate(expense_ids):
        budgets_repo.set_default(conn, _USER, NewBudgetDefault(category_id=cat, amount=90_000 + i))
    budgets_repo.set_one_off(
        conn,
        _USER,
        NewBudgetOneOffOverride(
            category_id=expense_ids[0], year=today.year, month=today.month, amount=40_000
        ),
    )
    ids = [
        accounts_repo.create(
            conn,
            _USER,
            NewAccount(
                name=f"A{i}",
                currency=_CURRENCIES[i % len(_CURRENCIES)],
                opening_balance=1000 * i,
            ),
        ).id
        for i in range(accounts)
    ]
    for i, acc in enumerate(ids):
        for d in range(0, 120, 7):
            txn_repo.create(
                conn,
                _USER,
                NewTransaction(
                    operation_date=today - timedelta(days=d),
                    category_id=income if d % 14 == 0 else expense_ids[(i + d) % 3],
                    account_id=acc,
                    amount=100 + i + d,
                    description="",
                ),
            )
        planned_repo.create(
            conn,
            _USER,
            NewPlannedTransaction(
                operation_date=today + timedelta(days=5 + i),
                category_id=expense_ids[i % 3],
                account_id=acc,
                amount=700 + i,
            ),
        )
    for r in range(rules):
        recurring_repo.create_rule(
            conn,
            _USER,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=today - timedelta(days=60 + r),
                category_id=expense_ids[r % 3] if r % 2 else income,
                account_id=ids[r % len(ids)],
                default_amount=500 + r,
                default_description=f"rule {r}",
            ),
        )
    return ids


def _seed(settings: Settings, accounts: int, rules: int) -> None:
    conn = get_connection(settings)
    try:
        seed_world(conn, accounts, rules)
        conn.commit()
    finally:
        conn.close()


@pytest.mark.parametrize("size", [(3, 3), (12, 12)], ids=["small", "large"])
@pytest.mark.parametrize(
    ("route", "budget"),
    [
        ("/accounts", _ACCOUNTS_BUDGET),
        ("/forecast", _FORECAST_BUDGET),
        ("/plan?tab=forecast", _FORECAST_BUDGET),
    ],
)
def test_route_query_budget(
    route: str,
    budget: int,
    *,
    size: tuple[int, int],
    settings: Settings,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(settings, *size)
    assert_max_queries = make_assert_max_queries(client, monkeypatch)
    assert_max_queries(route, budget)


# ---------------------------------------------------------------------------
# Exact values: the batch paths equal the per-account canonical paths.
# ---------------------------------------------------------------------------


def test_batch_balances_equal_per_account_derive_balance(conn: sqlite3.Connection) -> None:
    ids = seed_world(conn, 6, 2)
    accs = accounts_repo.list_all(conn, _USER)
    for as_of in (None, TODAY - timedelta(days=30), TODAY - timedelta(days=500)):
        got = balance_svc.derive_balances(conn, _USER, accs, as_of_date=as_of)
        assert got == {i: balance_svc.derive_balance(conn, _USER, i, as_of_date=as_of) for i in ids}


def test_batch_series_equals_day_by_day_derive_balance(conn: sqlite3.Connection) -> None:
    ids = seed_world(conn, 4, 1)
    accs = accounts_repo.list_all(conn, _USER)
    days = 40
    got = balance_svc.balance_series_many(conn, _USER, accs, days=days, today=TODAY)
    for acc_id in ids:
        expected = [
            (d, balance_svc.derive_balance(conn, _USER, acc_id, as_of_date=d))
            for d in (TODAY - timedelta(days=days - 1 - k) for k in range(days))
        ]
        assert got[acc_id] == expected
        assert balance_svc.balance_series(conn, _USER, acc_id, days=days, today=TODAY) == expected


def test_batch_series_counts_transit_both_legs(conn: sqlite3.Connection) -> None:
    transit = categories_repo.create(
        conn, _USER, NewCategory(name="Move", direction=Direction.TRANSIT)
    ).id
    a = accounts_repo.create(
        conn, _USER, NewAccount(name="A", currency="PLN", opening_balance=500)
    ).id
    b = accounts_repo.create(
        conn, _USER, NewAccount(name="B", currency="PLN", opening_balance=0)
    ).id
    txn_repo.create(
        conn,
        _USER,
        NewTransaction(
            operation_date=TODAY - timedelta(days=1),
            category_id=transit,
            account_id=a,
            dest_account_id=b,
            amount=200,
            description="",
        ),
    )
    accs = accounts_repo.list_all(conn, _USER)
    series = balance_svc.balance_series_many(conn, _USER, accs, days=3, today=TODAY)
    assert [v for _, v in series[a]] == [500, 300, 300]
    assert [v for _, v in series[b]] == [0, 200, 200]


def test_batch_stats_equal_per_account_stats(conn: sqlite3.Connection) -> None:
    ids = seed_world(conn, 5, 1)
    accs = accounts_repo.list_all(conn, _USER)
    got = balance_svc.account_stats_many(conn, _USER, accs)
    for i in ids:
        assert got[i] == balance_svc.account_stats(conn, _USER, i)


def test_budget_resolver_equals_resolve_budget(conn: sqlite3.Connection) -> None:
    seed_world(conn, 2, 1)
    resolve = budget_batch.budget_resolver(conn, _USER, display_timezone=DEFAULT_DISPLAY_TIMEZONE)
    for cat in categories_repo.list_all(conn, _USER):
        for year, month in ((2026, 11), (2026, 12), (2027, 1)):
            assert resolve(cat.id, year, month) == budget_svc.resolve_budget(
                conn, _USER, cat.id, year, month
            )


def test_forecast_numbers_unchanged_by_batching(conn: sqlite3.Connection) -> None:
    """Values recorded from the pre-batching code (with FX-converted spent) on this world."""
    seed_world(conn, 6, 5)
    conn.commit()
    settings = get_settings()
    proj = forecast_svc.monthly_projection(conn, _USER, settings, TODAY, horizon=12)
    assert [(p.label, p.value_major) for p in proj] == [
        ("Nov 2026", -1640.04),
        ("Dec 2026", -4291.81),
        ("Jan 2027", -6943.58),
        ("Feb 2027", -9595.35),
        ("Mar 2027", -12247.12),
        ("Apr 2027", -14898.89),
        ("May 2027", -17550.66),
        ("Jun 2027", -20202.43),
        ("Jul 2027", -22854.2),
        ("Aug 2027", -25505.97),
        ("Sep 2027", -28157.74),
        ("Oct 2027", -30809.51),
    ]
    series = forecast_svc.forecast(
        conn,
        _USER,
        fx_svc.converter_for(conn, settings, TODAY),
        TODAY,
        400,
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    totals = [d.totals_base_minor for d in series.days]
    assert (totals[0], totals[30], totals[-1]) == (53390, -344413, -3611310)
