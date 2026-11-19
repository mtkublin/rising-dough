"""Repro: reconcile accepts a ``transit`` category and breaks its post-condition (T-Q05).

``services.reconciliation.reconcile`` coerces the amount sign only for
``adjustment``/income/expense semantics; the router offers every non-system
category, including user categories with ``direction=transit``. A transit row
with no destination moves money out of the source leg only, so the derived
balance ends up different from the balance the user asked for.

Run: ``PYTHONPATH=src:. python docs/plans/quality-audit/repro/B/b_reconcile_transit.py``
"""

from __future__ import annotations

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


def main() -> None:
    settings, path = scratch("audit-B")
    print(f"scratch db: {path}")
    client = signed_in_client(settings)
    conn = get_connection(settings)
    acc = accounts_repo.create(
        conn, USER_ID, NewAccount(name="B-reconcile", currency="PLN", opening_balance=10_000)
    )
    cat = categories_repo.create(
        conn, USER_ID, NewCategory(name="B-transit", direction=Direction.TRANSIT)
    )
    target = "150.00"  # 15_000 minor; derived is 10_000
    r = client.post(
        f"/accounts/{acc.id}/reconcile",
        data={"actual_balance": target, "category_id": str(cat.id), "save_snapshot": ""},
    )
    row = conn.execute(
        "SELECT amount, dest_account_id FROM transactions WHERE account_id = ? AND category_id = ?",
        (acc.id, cat.id),
    ).fetchone()
    print("HTTP status:", r.status_code)
    print("stored txn (amount, dest_account_id):", tuple(row) if row else None)
    try:
        print("derive_balance:", balance_svc.derive_balance(conn, USER_ID, acc.id))
        poisoned = False
    except ValueError as exc:
        print("derive_balance raises ValueError:", exc)
        poisoned = True
    page = client.get("/accounts")
    print("GET /accounts status afterwards:", page.status_code)
    print("REPRODUCED (invalid txn persisted, balance pages fail):", poisoned)
    conn.close()


if __name__ == "__main__":
    main()
