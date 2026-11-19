"""T-Q06: EXPLAIN QUERY PLAN for user-scoped hot filters. Scratch DB only.

Run: uv run python docs/plans/quality-audit/repro/C/explain_plans.py /tmp/audit-C.sqlite
"""

from __future__ import annotations

import sqlite3
import sys

path = sys.argv[1]
if not path.startswith("/tmp/") or "budget.sqlite" in path:
    sys.exit("refusing: scratch DB under /tmp only")
db = sqlite3.connect(path)
QUERIES = {
    "txn list (user, live, newest)": "SELECT * FROM transactions WHERE user_id=1 AND deleted_at IS NULL ORDER BY operation_date DESC, id DESC LIMIT 50",
    "txn by account OR dest": "SELECT * FROM transactions WHERE user_id=1 AND deleted_at IS NULL AND (account_id=1 OR dest_account_id=1)",
    "txn date range": "SELECT * FROM transactions WHERE user_id=1 AND deleted_at IS NULL AND operation_date BETWEEN '2026-11-01' AND '2026-11-30'",
    "txn by category": "SELECT * FROM transactions WHERE user_id=1 AND deleted_at IS NULL AND category_id=7",
    "txn recently deleted": "SELECT * FROM transactions WHERE user_id=1 AND deleted_at IS NOT NULL AND deleted_at > datetime('now','-90 days') ORDER BY deleted_at DESC",
    "planned pending": "SELECT * FROM planned_transactions WHERE user_id=1 AND deleted_at IS NULL AND promoted_to_txn_id IS NULL",
    "audit_log by user": "SELECT * FROM audit_log WHERE user_id=1 ORDER BY id DESC LIMIT 50",
    "audit_log by entity": "SELECT * FROM audit_log WHERE entity_type='transaction' AND entity_id=5",
    "audit_log retention scrub": "UPDATE audit_log SET ip=NULL WHERE datetime(changed_at) < datetime('2026-01-01T00:00:00.000Z')",
    "recurring rules": "SELECT * FROM recurring_rules WHERE user_id=1 AND deleted_at IS NULL",
    "overrides by rule": "SELECT * FROM recurring_rule_overrides WHERE rule_id=3",
    "categories": "SELECT * FROM categories WHERE user_id=1 ORDER BY name",
    "accounts": "SELECT * FROM accounts WHERE user_id=1 AND deleted_at IS NULL",
    "fx latest on/before": "SELECT * FROM fx_rates WHERE from_ccy='EUR' AND to_ccy='PLN' AND date<='2026-11-19' ORDER BY date DESC LIMIT 1",
    "budget_defaults": "SELECT * FROM budget_defaults WHERE category_id=3 AND user_id=1 AND deleted_at IS NULL",
    "sessions lookup": "SELECT * FROM sessions WHERE id='x' AND revoked_at IS NULL",
}
for name, sql in QUERIES.items():
    plan = [r[3] for r in db.execute("EXPLAIN QUERY PLAN " + sql)]
    print(f"{name:32} {' | '.join(plan)}")
print("\nindexes:")
for (tbl,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
    idx = [r[1] for r in db.execute(f"PRAGMA index_list({tbl})")]  # noqa: S608
    print(f"  {tbl}: {', '.join(idx) or '(none)'}")
