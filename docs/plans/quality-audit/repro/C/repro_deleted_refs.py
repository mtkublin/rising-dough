"""T-Q06 repro: soft-deleted account/category still referenced by live rules; fortune drop.

Scratch DB only. Run:
    cp /tmp/audit-C.sqlite /tmp/audit-C-del.sqlite
    BUDGET_DATABASE_URL=sqlite:////tmp/audit-C-del.sqlite PYTHONPATH=. \
      uv run python docs/plans/quality-audit/repro/C/repro_deleted_refs.py
"""

from __future__ import annotations

import datetime as dt
import os
import sys

URL = os.environ.get("BUDGET_DATABASE_URL", "")
if not URL.startswith("sqlite:////tmp/") or "budget.sqlite" in URL:
    sys.exit("refusing: BUDGET_DATABASE_URL must point at a /tmp scratch DB")

from budget_planner.config import Settings  # noqa: E402
from budget_planner.db.connection import get_connection  # noqa: E402
from budget_planner.repositories import accounts as accounts_repo  # noqa: E402
from budget_planner.repositories import recurring as recurring_repo  # noqa: E402
from budget_planner.services import balance, upcoming  # noqa: E402
from budget_planner.services import recurring as recurring_svc  # noqa: E402
from budget_planner.web import today_data  # noqa: E402

conn = get_connection(Settings())
RID = conn.execute(
    "SELECT r.id FROM recurring_rules r JOIN categories c ON c.id = r.category_id "
    "WHERE r.active = 1 AND r.deleted_at IS NULL AND c.direction = 'expense' ORDER BY r.id LIMIT 1"
).fetchone()[0]
rule = recurring_repo.find_rule(conn, 1, RID)
assert rule is not None
acct = accounts_repo.find_by_id(conn, 1, rule.account_id)
assert acct is not None
print(f"rule #{RID} -> account #{acct.id} '{acct.name}', next_due={rule.next_due}")

_, _, fortune_before = today_data.collect_account_rows(conn, 1, "PLN")
bal = balance.derive_balance(conn, 1, acct.id)
accounts_repo.soft_delete(conn, 1, acct.id)  # no balance / dependency check in the route either
_, _, fortune_after = today_data.collect_account_rows(conn, 1, "PLN")
print(f"\n== D1: soft-delete account with balance {bal} (minor) ==")
print(f"fortune before={fortune_before} after={fortune_after} diff={fortune_after - fortune_before}")

print("\n== D2: live recurring rule on the deleted account is still scheduled and promotable ==")
rows = upcoming.list_upcoming(conn, 1, today=dt.date(2026, 11, 1), window_days=60)
print("upcoming rows referencing deleted account:", sum(1 for r in rows if getattr(r, "account_id", None) == acct.id))
txn = recurring_svc.promote_recurring(conn, 1, RID, recurring_svc.PromotionEdits())
print(f"promote_recurring(rule) created txn #{txn.id} on deleted account #{txn.account_id}")
live_ids = {a.id for a in accounts_repo.list_all(conn, 1)}
print("account visible in list_all():", txn.account_id in live_ids, "-> the new transaction is on an invisible account")
