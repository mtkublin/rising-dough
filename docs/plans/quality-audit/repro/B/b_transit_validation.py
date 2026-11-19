"""Repro: transit-without-destination invariant is enforced only by some routers (T-Q05).

``POST /transactions`` accepts a ``transit`` category with an empty destination
(the recurring router rejects the same input with "transit requires
destination account"), and ``POST /transactions/{id}`` re-categorises a row to
``transit`` without any destination check. The invalid row persists; every
balance computation for that account then raises, so account/today pages 500.

Run: ``PYTHONPATH=src:. python docs/plans/quality-audit/repro/B/b_transit_validation.py``
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import USER_ID, scratch, signed_in_client  # noqa: E402

from budget_planner.db.connection import get_connection  # noqa: E402
from budget_planner.domain.accounts import NewAccount  # noqa: E402
from budget_planner.domain.categories import NewCategory  # noqa: E402
from budget_planner.domain.enums import Direction  # noqa: E402
from budget_planner.repositories import (  # noqa: E402
    accounts as accounts_repo,
    categories as categories_repo,
)
from budget_planner.services import balance as balance_svc  # noqa: E402


def _balance_state(conn: sqlite3.Connection, account_id: int) -> str:
    try:
        return str(balance_svc.derive_balance(conn, USER_ID, account_id))
    except ValueError as exc:
        return f"ValueError: {exc}"


def main() -> None:
    settings, path = scratch("audit-B")
    print(f"scratch db: {path}")
    client = signed_in_client(settings)
    conn = get_connection(settings)
    today = dt.date.today().isoformat()  # noqa: DTZ011
    acc_a = accounts_repo.create(
        conn, USER_ID, NewAccount(name="B-transit-a", currency="PLN", opening_balance=0)
    )
    transit = categories_repo.create(
        conn, USER_ID, NewCategory(name="B-transit", direction=Direction.TRANSIT)
    )
    expense = categories_repo.create(
        conn, USER_ID, NewCategory(name="B-expense", direction=Direction.EXPENSE)
    )

    # (a) create: transit category, empty destination.
    r = client.post(
        "/transactions",
        data={
            "operation_date": today,
            "category_id": str(transit.id),
            "account_id": str(acc_a.id),
            "amount": "10.00",
            "description": "transit without dest",
            "dest_account_id": "",
        },
    )
    print("(a) POST /transactions transit, no dest -> HTTP", r.status_code)
    print("(a) derive_balance:", _balance_state(conn, acc_a.id))

    # (b) update: expense row re-categorised to transit.
    acc_b = accounts_repo.create(
        conn, USER_ID, NewAccount(name="B-transit-b", currency="PLN", opening_balance=0)
    )
    r = client.post(
        "/transactions",
        data={
            "operation_date": today,
            "category_id": str(expense.id),
            "account_id": str(acc_b.id),
            "amount": "5.00",
            "description": "plain expense",
        },
    )
    txn_id = conn.execute(
        "SELECT id FROM transactions WHERE account_id = ?", (acc_b.id,)
    ).fetchone()["id"]
    print("(b) create expense -> HTTP", r.status_code, "| balance:", _balance_state(conn, acc_b.id))
    r = client.post(
        f"/transactions/{txn_id}",
        data={
            "operation_date": today,
            "category_id": str(transit.id),
            "account_id": str(acc_b.id),
            "amount": "5.00",
            "description": "now transit",
            "dest_account_id": "",
        },
    )
    print("(b) POST /transactions/{id} -> transit, no dest -> HTTP", r.status_code)
    print("(b) derive_balance:", _balance_state(conn, acc_b.id))
    print("GET /accounts status afterwards:", client.get("/accounts").status_code)
    conn.close()


if __name__ == "__main__":
    main()
