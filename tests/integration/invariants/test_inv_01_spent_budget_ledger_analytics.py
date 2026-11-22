# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""INV-1: budget spent(C, M) == ledger total == analytics(C, M), all in base currency (Q-008, Q-010)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from budget_planner.clock import DEFAULT_DISPLAY_TIMEZONE
from budget_planner.config import get_settings
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.enums import Direction
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.transactions import NewTransaction, TransactionFilter
from budget_planner.repositories import (
    accounts as accounts_repo,
    fx as fx_repo,
    transactions as txn_repo,
)
from budget_planner.services import analytics, budget, fx as fx_svc, ledger_totals

U = 1
Y, M = 2026, 10
START, END = date(Y, M, 1), date(Y, M, 31)
GROCERIES = 7


def figures(conn: sqlite3.Connection) -> dict[str, int]:
    summ = budget.month_summary(
        conn,
        U,
        Y,
        M,
        today=END,
        period_window=(START, END),
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    line = next(x for x in summ.lines if x.category_id == GROCERIES)
    converter = fx_svc.converter_for(conn, get_settings(), END)
    bundle = analytics.bundle(conn, U, converter, today=END, period="month")
    spend = next(
        (r.amount_minor for r in bundle.spend_by_category if r.category_id == GROCERIES), 0
    )
    rows = txn_repo.list_filtered(
        conn,
        U,
        TransactionFilter(
            date_from=START,
            date_to=END,
            category_ids=(GROCERIES,),
            directions=(Direction.EXPENSE,),
        ),
    )
    ccy = {a.id: a.currency for a in accounts_repo.list_all(conn, U, include_deleted=True)}
    items = [(t.operation_date, t.amount, Direction.EXPENSE, ccy[t.account_id]) for t in rows]
    ledger = -sum(
        ledger_totals.day_nets(items, lambda a, d, c: converter.to_base(a, c, d)).values()
    )
    return {"budget.spent": line.spent_minor, "analytics.spend": spend, "ledger.total": ledger}


def test_pln_only_demo_agrees(seeded: sqlite3.Connection) -> None:
    assert len(set(figures(seeded).values())) == 1


def test_foreign_currency_expense_agrees_across_budget_ledger_analytics(
    seeded: sqlite3.Connection,
) -> None:
    eur = accounts_repo.create(
        seeded, U, NewAccount(name="EUR Wallet", currency="EUR", opening_balance=0)
    ).id
    fx_repo.upsert_rate(
        seeded,
        NewFxRate(date=date(2026, 10, 15), from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.30")),
    )
    txn_repo.create(
        seeded,
        U,
        NewTransaction(
            operation_date=date(2026, 10, 15),
            category_id=GROCERIES,
            account_id=eur,
            amount=10_000,
            description="audit EUR",
        ),
    )
    assert len(set(figures(seeded).values())) == 1, figures(seeded)
