"""Repro: router-resident logic produces wrong numbers / 500s (T-Q05).

1. ``GET /plan?tab=budget&year=0&month=5``: ``plan()`` shifts ``today`` into the
   requested month with ``date.replace(year=year, ...)`` without bounding
   ``year``, so an out-of-range year raises ``ValueError`` (HTTP 500).
2. ``GET /ledger?view=recurring``: ``_recurring_summary`` adds every rule's
   ``effective_amount_minor`` in the *account's own currency* with no FX
   conversion. A 100.00 EUR and a 100.00 PLN monthly expense show as 200.00.

Run: ``PYTHONPATH=src:. python docs/plans/quality-audit/repro/B/b_router_logic.py``
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import USER_ID, scratch, signed_in_client  # noqa: E402

from budget_planner.db.connection import get_connection  # noqa: E402
from budget_planner.domain.accounts import NewAccount  # noqa: E402
from budget_planner.domain.categories import NewCategory  # noqa: E402
from budget_planner.domain.enums import Cadence, Direction  # noqa: E402
from budget_planner.domain.recurring import NewRecurringRule  # noqa: E402
from budget_planner.repositories import (  # noqa: E402
    accounts as accounts_repo,
    categories as categories_repo,
    recurring as recurring_repo,
)


def main() -> None:
    settings, path = scratch("audit-B")
    print(f"scratch db: {path}")
    client = signed_in_client(settings)
    conn = get_connection(settings)

    r = client.get("/plan?tab=budget&year=0&month=5")
    print("(1) GET /plan?tab=budget&year=0&month=5 -> HTTP", r.status_code)

    # (2) Start from an empty rule set so the strip only reflects the two rules below.
    conn.execute("UPDATE recurring_rules SET active = 0")
    pln = accounts_repo.create(
        conn, USER_ID, NewAccount(name="B-pln", currency="PLN", opening_balance=0)
    )
    eur = accounts_repo.create(
        conn, USER_ID, NewAccount(name="B-eur", currency="EUR", opening_balance=0)
    )
    cat = categories_repo.create(
        conn, USER_ID, NewCategory(name="B-rent", direction=Direction.EXPENSE)
    )
    for acc in (pln, eur):
        recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=dt.date.today(),  # noqa: DTZ011
                category_id=cat.id,
                account_id=acc.id,
                default_amount=10_000,
                default_description=f"b-{acc.currency}",
            ),
        )
    html = client.get("/ledger?view=recurring").text
    match = re.search(r"Monthly out</span>\s*<strong[^>]*>\s*([\d,]+)\s*<span[^>]*>(\w+)<", html)
    print("(2) rules: 100.00 PLN + 100.00 EUR monthly expense")
    print("(2) 'Monthly out' strip shows:", match.groups() if match else "not found")
    print("(2) REPRODUCED (EUR added to PLN unconverted):", bool(match) and match.group(1) == "200")
    conn.close()


if __name__ == "__main__":
    main()
