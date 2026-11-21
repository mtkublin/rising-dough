# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""INV-3: budget and forecast agree on spent / committed for the same category and window (Q-008, Q-002, Q-030)."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from decimal import Decimal

from budget_planner.config import get_settings
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.enums import Direction
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.transactions import NewTransaction, TransactionFilter
from budget_planner.repositories import (
    accounts as accounts_repo,
    fx as fx_repo,
    planned as planned_repo,
    transactions as txn_repo,
)
from budget_planner.services import budget, forecast, fx as fx_svc

U = 1
TODAY = date(2026, 11, 19)
M_START, M_END = date(2026, 11, 1), date(2026, 11, 30)


def test_3a_spent_in_base_currency_agrees(seeded: sqlite3.Connection) -> None:
    eur = accounts_repo.create(seeded, U, NewAccount(name="EUR Wallet", currency="EUR")).id
    fx_repo.upsert_rate(
        seeded,
        NewFxRate(date=date(2026, 11, 10), from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.30")),
    )
    txn_repo.create(
        seeded,
        U,
        NewTransaction(
            operation_date=date(2026, 11, 10), category_id=7, account_id=eur, amount=10_000
        ),
    )
    txns = txn_repo.list_filtered(
        seeded,
        U,
        TransactionFilter(
            date_from=M_START, date_to=TODAY, category_ids=(7,), directions=(Direction.EXPENSE,)
        ),
    )
    b_spent = budget._sum_by_category(txns, budget.txn_base_amounts(seeded, U, today=TODAY)).get(
        7, 0
    )
    converter = fx_svc.converter_for(seeded, get_settings(), TODAY)
    f_spent = forecast._spent_so_far(
        seeded, U, 7, M_START, TODAY, base_of=fx_svc.txn_base_of(converter, {eur: "EUR"})
    )
    assert b_spent == f_spent, (b_spent, f_spent)


def _committed_pair(conn: sqlite3.Connection) -> tuple[int, int]:
    win_start = TODAY + timedelta(days=1)
    b = budget.committed_by_category(
        conn, U, start=win_start, end=M_END + timedelta(days=1), today=TODAY
    ).get(6, 0)
    f = forecast._committed_future_for_category(conn, U, 6, win_start, M_END, today=TODAY)
    return b, f


def test_3b_committed_agrees_before_a_planned_row_is_linked(seeded: sqlite3.Connection) -> None:
    b, f = _committed_pair(seeded)
    assert b == f


def test_3b_committed_agrees_after_a_planned_row_is_linked(seeded: sqlite3.Connection) -> None:
    planned_repo.create(
        seeded,
        U,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 24),
            category_id=6,
            account_id=5,
            amount=1530,
            description="linked",
            recurring_rule_id=22,
            occurrence_date=date(2026, 11, 24),
        ),
    )
    b, f = _committed_pair(seeded)
    assert b == f, (b, f)


def test_3c_overdue_planned_item_is_in_the_forecast_event_stream(
    seeded: sqlite3.Connection,
) -> None:
    planned_repo.create(
        seeded,
        U,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 5), category_id=7, account_id=1, amount=5000
        ),
    )
    budget_counts = budget.committed_by_category(
        seeded, U, start=None, end=M_END + timedelta(days=1), today=TODAY
    ).get(7, 0)
    events = forecast._collect_events(seeded, U, TODAY, M_END)
    placed = [e for evs in events.values() for e in evs if e.amount_minor == -5000]
    assert budget_counts == 5000
    # OQ-6 default (ADR-0105 amendment 2026-11-21): overdue is placed on today + 1.
    assert [(e.on_date, e.account_id) for e in placed] == [(TODAY + timedelta(days=1), 1)]
