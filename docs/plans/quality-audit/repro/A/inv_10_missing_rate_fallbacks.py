"""INV-10: one missing FX rate (EUR->PLN, nothing cached, network down) must degrade the same way.

Each consumer's observed behaviour is printed; a consistent policy would give one outcome.
"""

from __future__ import annotations

from datetime import date

import harness

from budget_planner.domain.accounts import NewAccount
from budget_planner.repositories import accounts as accounts_repo
from budget_planner.services import budget, forecast
from budget_planner.web import today_data

U = harness.USER_ID
TODAY = date.today()
conn = harness.fresh_db()
eur = accounts_repo.create(conn, U, NewAccount(name="EUR", currency="EUR", opening_balance=100_000)).id

outcomes: dict[str, str] = {}
conv = budget.base_amount_converter(conn, U, today=TODAY)
outcomes["budget.base_amount_converter(100000 EUR-minor)"] = f"returns {conv(eur, 100_000)} (native amount, no error)"

_, _, fortune_base = today_data.collect_account_rows(conn, U, "PLN")
outcomes["today_data.collect_account_rows"] = f"rate=1 degrade; fortune_base={fortune_base}"

try:
    forecast.forecast(conn, U, harness.offline_http(), TODAY, 0, "PLN", include_budget_overlay=False)
    outcomes["forecast.forecast"] = "ok"
except Exception as exc:  # noqa: BLE001
    outcomes["forecast.forecast"] = f"RAISES {type(exc).__name__} (no caller catches it -> HTTP 500)"

for k, v in outcomes.items():
    print(f"{k}: {v}")
harness.check("one consistent degrade policy", len({v.split()[0] for v in outcomes.values()}) == 1)
