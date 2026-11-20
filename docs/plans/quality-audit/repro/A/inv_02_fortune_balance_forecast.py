"""INV-2: fortune / balance agree across implementations (base currency).

* derive_balance == opening + SQL signed sum (independent oracle)
* compute_fortune.net_base == today_data fortune_base == forecast day-0 total
Run A: demo (PLN only).  Run B: + EUR account holding 1000.00 EUR (rate 4.30 today).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import harness

from budget_planner.config import get_settings
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.fx import NewFxRate
from budget_planner.repositories import accounts as accounts_repo, fx as fx_repo
from budget_planner.services import balance, forecast, fortune
from budget_planner.web import today_data

U = harness.USER_ID
TODAY = date.today()

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


def run(conn, label: str) -> None:
    harness.banner(label)
    s = get_settings()
    ok = True
    for a in accounts_repo.list_all(conn, U):
        derived = balance.derive_balance(conn, U, a.id)
        oracle = conn.execute(ORACLE, (TODAY.isoformat(), a.id)).fetchone()[0]
        ok &= derived == oracle
    harness.check("derive_balance == SQL oracle for every account", ok)
    f = fortune.compute_fortune(conn, U, s)
    _, _, fortune_base = today_data.collect_account_rows(conn, U, s.base_currency)
    series = forecast.forecast(
        conn,
        U,
        harness.offline_http(),
        TODAY,
        0,
        s.base_currency,
        include_budget_overlay=False,
    )
    day0 = series.days[0].totals_base_minor
    print(
        {
            "fortune.net_base (Today 'Net worth · all accounts' + Accounts hero)": f.net_base,
            "today_data.fortune_base (converted, unused by template)": fortune_base,
            "forecast day-0 total": day0,
        }
    )
    harness.check("fortune.net_base == today_data.fortune_base", f.net_base == fortune_base)
    harness.check("today_data.fortune_base == forecast day-0", fortune_base == day0)


conn = harness.fresh_db()
run(conn, "Run A: demo (PLN only)")
eur = accounts_repo.create(
    conn, U, NewAccount(name="EUR Wallet", currency="EUR", opening_balance=100_000)
).id
fx_repo.upsert_rate(
    conn, NewFxRate(date=TODAY, from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.30"))
)
run(conn, "Run B: + EUR account 1000.00 EUR (= 4300.00 PLN)")
