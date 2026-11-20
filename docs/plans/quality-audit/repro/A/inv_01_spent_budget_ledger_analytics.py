"""INV-1: budget spent(C,M) == ledger total == analytics(C,M), all in base currency.

Run A: demo data (all PLN)  -> expected to agree.
Run B: + one EUR account, one EUR expense (100.00 EUR, Groceries, 2026-10-15, rate 4.30)
       -> ADR-0006/0095 say every aggregate is in base currency (430.00 PLN).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import harness

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

U = harness.USER_ID
Y, M = 2026, 10
START, END = date(Y, M, 1), date(Y, M, 31)
GROCERIES = 7


def figures(conn) -> dict[str, int]:
    summ = budget.month_summary(conn, U, Y, M, today=END, period_window=(START, END))
    line = next(x for x in summ.lines if x.category_id == GROCERIES)
    bundle = analytics.bundle(conn, U, today=END, period="month")
    an = next((r.amount_minor for r in bundle.spend_by_category if r.category_id == GROCERIES), 0)
    base = get_settings().base_currency
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
    led = -sum(
        ledger_totals.day_nets(
            items, lambda a, d, c: fx_svc.convert_cached(conn, a, d, c, base)
        ).values()
    )
    return {"budget.spent": line.spent_minor, "analytics.spend": an, "ledger.total": led}


def report(label: str, f: dict[str, int]) -> None:
    harness.banner(label)
    print(f)
    harness.check("budget == ledger == analytics", len(set(f.values())) == 1)


conn = harness.fresh_db()
report("Run A: demo (PLN only)", figures(conn))

eur = accounts_repo.create(
    conn, U, NewAccount(name="EUR Wallet", currency="EUR", opening_balance=0)
).id
fx_repo.upsert_rate(
    conn,
    NewFxRate(date=date(2026, 10, 15), from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.30")),
)
txn_repo.create(
    conn,
    U,
    NewTransaction(
        operation_date=date(2026, 10, 15),
        category_id=GROCERIES,
        account_id=eur,
        amount=10_000,
        description="audit EUR",
    ),
)
report("Run B: + 100.00 EUR grocery (expect 43000 minor PLN extra)", figures(conn))
