"""Repro: batch-undo routes replay ``audit_log`` and bypass the audit layer (T-Q05).

Scenarios on a scratch DB (``/tmp/audit-B.sqlite``, copied from demo data):

1. Rule edited after a batch promote, then ``POST /recurring/batch/undo``: the
   router replays "the latest audit row" (the edit's), so the txn is undone but
   ``next_due`` is not restored.
2. Undo of the *final* promotion of an ending rule: ``set_inactive`` is not
   reverted, so the rule stays inactive although the txn was undone.
3. ``POST /planned/batch/undo``: the raw ``UPDATE planned_transactions`` in the
   router writes no ``audit_log`` row.

Run: ``PYTHONPATH=src:. python docs/plans/quality-audit/repro/B/b_undo_replay.py``
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import USER_ID, audit_rows, scratch, signed_in_client  # noqa: E402

from budget_planner.db.connection import get_connection  # noqa: E402
from budget_planner.domain.accounts import NewAccount  # noqa: E402
from budget_planner.domain.categories import NewCategory  # noqa: E402
from budget_planner.domain.enums import Cadence, Direction  # noqa: E402
from budget_planner.domain.planned import NewPlannedTransaction  # noqa: E402
from budget_planner.domain.recurring import NewRecurringRule, PatchRecurringRule  # noqa: E402
from budget_planner.repositories import (  # noqa: E402
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
)


def _undo_payload(resp_headers: dict[str, str]) -> dict[str, str]:
    toast = json.loads(resp_headers["hx-trigger"])["toast"]["undo_payload"]
    return {k: ",".join(str(i) for i in v) for k, v in toast.items()}


def main() -> None:
    settings, path = scratch("audit-B")
    print(f"scratch db: {path}")
    client = signed_in_client(settings)
    conn = get_connection(settings)
    today = dt.date.today()  # noqa: DTZ011
    acc = accounts_repo.create(
        conn, USER_ID, NewAccount(name="B-repro", currency="PLN", opening_balance=0)
    )
    cat = categories_repo.create(
        conn, USER_ID, NewCategory(name="B-repro-exp", direction=Direction.EXPENSE)
    )

    # Scenario 1: double undo -------------------------------------------------
    start = today - dt.timedelta(days=40)
    rule = recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=start,
            category_id=cat.id,
            account_id=acc.id,
            default_amount=1000,
            default_description="b-repro",
        ),
    )
    recurring_repo.set_next_due(
        conn, USER_ID, rule.id, next_due=today - dt.timedelta(days=9), last_promoted_date=None
    )
    before = recurring_repo.find_rule(conn, USER_ID, rule.id)
    assert before is not None
    r = client.post("/recurring/batch/promote-due")
    print("promote-due status", r.status_code, r.text[:200])
    payload = _undo_payload(dict(r.headers))
    after_promote =recurring_repo.find_rule(conn, USER_ID, rule.id)
    assert after_promote is not None
    # The user edits the rule after the batch (any edit writes a newer audit row).
    recurring_repo.update_rule(
        conn, USER_ID, rule.id, PatchRecurringRule(default_description="edited after batch")
    )
    client.post("/recurring/batch/undo", data=payload)
    after_undo = recurring_repo.find_rule(conn, USER_ID, rule.id)
    assert after_undo is not None
    txn_ids = payload["promoted_txn_ids"].split(",")
    live = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE id IN (%s) AND deleted_at IS NULL"
        % ",".join("?" * len(txn_ids)),
        txn_ids,
    ).fetchone()[0]
    print("S1 next_due  before promote :", before.next_due)
    print("S1 next_due  after promote  :", after_promote.next_due)
    print("S1 next_due  after undo     :", after_undo.next_due, "| live promoted txns:", live)
    print("S1 REPRODUCED (txn undone, rule stays advanced):", after_undo.next_due != before.next_due)

    # Scenario 2: final promotion of an ending rule ---------------------------
    end = today
    rule2 = recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=today - dt.timedelta(days=5),
            end_date=end,
            category_id=cat.id,
            account_id=acc.id,
            default_amount=2000,
            default_description="b-repro-final",
        ),
    )
    r = client.post("/recurring/batch/promote-due")
    payload2 = _undo_payload(dict(r.headers))
    after_promote2 = recurring_repo.find_rule(conn, USER_ID, rule2.id, include_deleted=True)
    assert after_promote2 is not None
    client.post("/recurring/batch/undo", data=payload2)
    after_undo = recurring_repo.find_rule(conn, USER_ID, rule2.id, include_deleted=True)
    assert after_undo is not None
    print("S2 active after promote:", after_promote2.active, "| after undo:", after_undo.active)
    print("S2 REPRODUCED (rule stays inactive after undo):", not after_undo.active)

    # Scenario 3: planned undo writes no audit row ----------------------------
    planned = planned_repo.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=today - dt.timedelta(days=1),
            category_id=cat.id,
            account_id=acc.id,
            amount=500,
            description="b-repro-planned",
        ),
    )
    r = client.post("/planned/batch/promote-due")
    payload3 = _undo_payload(dict(r.headers))
    n_before = len(audit_rows(conn, "planned_transaction", planned.id))
    client.post("/planned/batch/undo", data=payload3)
    n_after = len(audit_rows(conn, "planned_transaction", planned.id))
    row = planned_repo.find_by_id(conn, USER_ID, planned.id)
    assert row is not None
    print("S3 promoted_to_txn_id after undo:", row.promoted_to_txn_id)
    print("S3 audit rows before/after undo:", n_before, n_after)
    print("S3 REPRODUCED (audit bypass):", n_after == n_before and row.promoted_to_txn_id is None)
    conn.close()


if __name__ == "__main__":
    main()
