"""INV-3: budget and forecast agree on spent / committed for the same category+window.

3a spent:  budget (converted, ADR-0095 s6-8) vs forecast._spent_so_far (raw sum)
3b committed with a linked planned row (ADR-0087 dedup): budget vs forecast overlay helper
3c overdue unpromoted planned item: budget committed (ADR-0105) vs forecast event stream
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import harness

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
from budget_planner.services import budget, forecast

U = harness.USER_ID
TODAY = date(2026, 11, 19)
M_START, M_END = date(2026, 11, 1), date(2026, 11, 30)

conn = harness.fresh_db()

# ---- 3a -------------------------------------------------------------------
harness.banner("3a spent: EUR expense 100.00 EUR on 2026-11-10 (Groceries), rate 4.30")
eur = accounts_repo.create(conn, U, NewAccount(name="EUR Wallet", currency="EUR")).id
fx_repo.upsert_rate(
    conn,
    NewFxRate(date=date(2026, 11, 10), from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.30")),
)
txn_repo.create(
    conn,
    U,
    NewTransaction(
        operation_date=date(2026, 11, 10), category_id=7, account_id=eur, amount=10_000
    ),
)
txns = txn_repo.list_filtered(
    conn,
    U,
    TransactionFilter(
        date_from=M_START,
        date_to=TODAY,
        category_ids=(7,),
        directions=(Direction.EXPENSE,),
    ),
)
b_spent = budget._sum_by_category(txns, budget.base_txn_converter(conn, U)).get(7, 0)
f_spent = forecast._spent_so_far(conn, U, 7, M_START, TODAY)
print({"budget spent (base)": b_spent, "forecast._spent_so_far": f_spent})
harness.check("budget spent == forecast spent", b_spent == f_spent)

# ---- 3b -------------------------------------------------------------------
harness.banner("3b committed: rule 22 (cat 6, 2026-11-24, 1530) + linked planned row for same occurrence")
win_start = TODAY + timedelta(days=1)


def pair() -> tuple[int, int]:
    b = budget._committed_by_category(
        conn, U, start=win_start, end=M_END + timedelta(days=1), today=TODAY
    ).get(6, 0)
    f = forecast._committed_future_for_category(conn, U, 6, win_start, M_END, today=TODAY)
    return b, f


b0, f0 = pair()
print({"before link: budget": b0, "forecast": f0})
planned_repo.create(
    conn,
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
b1, f1 = pair()
print({"after link: budget": b1, "forecast": f1})
harness.check("budget committed == forecast committed (after link)", b1 == f1)

# ---- 3c -------------------------------------------------------------------
harness.banner("3c overdue: unpromoted planned expense dated 2026-11-05 (< today), cat 7, 5000")
planned_repo.create(
    conn,
    U,
    NewPlannedTransaction(
        operation_date=date(2026, 11, 5), category_id=7, account_id=1, amount=5000
    ),
)
b_all = budget._committed_by_category(
    conn, U, start=None, end=M_END + timedelta(days=1), today=TODAY
).get(7, 0)
events = forecast._collect_events(
    conn,
    U,
    TODAY,
    M_END,
    {c.id: c.direction for c in __import__("budget_planner.repositories.categories", fromlist=["x"]).list_all(conn, U, include_deleted=True)},
)
f_ev = sum(-e.amount_minor for evs in events.values() for e in evs if e.on_date <= M_END)
overdue_in_events = any(e.on_date == date(2026, 11, 5) for evs in events.values() for e in evs)
print({"budget committed(cat7, unbounded start)": b_all, "overdue 11-05 event in forecast stream": overdue_in_events})
harness.check("forecast event stream contains the overdue item budget counts", overdue_in_events)
