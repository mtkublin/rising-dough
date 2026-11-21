"""T-Q228 (Q-024, Q-049): batch undo is an audited, batch-targeted action.

Ported from ``docs/plans/quality-audit/repro/B/b_undo_replay.out`` and
``repro/H2/h2_02_undo_chain.py``: undo used to replay "the latest audit row" of any
operation, restore partial state and write no audit entry (ADR-0019, ADR-0022).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule, PatchRecurringRule
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    preferences as preferences_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from budget_planner.repositories._unaudited import set_next_due
from budget_planner.services import recurring as recurring_svc, recurring_undo
from budget_planner.web.app import create_app
from tests.auth_support import login_cookie
from tests.integration.web.conftest import _CSRFAwareTestClient

pytestmark = pytest.mark.integration

USER = 1
OTHER = 2
DUE = date(2026, 10, 20)


@pytest.fixture
def user_two_client(_migrated: Settings) -> Iterator[TestClient]:
    name, value = login_cookie(_migrated, user_id=OTHER, email="second@example.test")
    with _CSRFAwareTestClient(create_app(settings=_migrated)) as c:
        c.cookies.set(name, value)
        yield c


def _seed(conn: sqlite3.Connection, user_id: int) -> tuple[int, int]:
    acc = accounts_repo.create(
        conn, user_id, NewAccount(name="Main", currency="PLN", opening_balance=0)
    )
    cat = categories_repo.create(
        conn, user_id, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    )
    return acc.id, cat.id


def _rule(conn: sqlite3.Connection, user_id: int) -> int:
    acc, cat = _seed(conn, user_id)
    rule = recurring_repo.create_rule(
        conn,
        user_id,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 10, 1),
            category_id=cat,
            account_id=acc,
            default_amount=1_000,
            default_description="",
        ),
    )
    set_next_due(conn, user_id, rule.id, next_due=DUE, last_promoted_date=None)
    return rule.id


def _planned(conn: sqlite3.Connection, user_id: int) -> int:
    acc, cat = _seed(conn, user_id)
    return planned_repo.create(
        conn,
        user_id,
        NewPlannedTransaction(
            operation_date=DUE, category_id=cat, account_id=acc, amount=5_000, description=""
        ),
    ).id


def _promote_recurring(conn: sqlite3.Connection, user_id: int) -> dict[str, list[int]]:
    """Run the recurring batch promote through the service (its HTTP route was removed)."""
    result = recurring_svc.batch_promote_due(conn, user_id, DUE)
    return {
        "promoted_txn_ids": list(result.promoted_txn_ids),
        "advance_audit_ids": list(result.advance_audit_ids),
    }


def _undo_recurring(
    conn: sqlite3.Connection,
    user_id: int,
    txn_ids: list[int],
    audit_ids: list[int],
) -> recurring_undo.BatchUndoResult:
    """Undo a recurring batch through the service (its HTTP route was removed)."""
    return recurring_undo.undo_batch(conn, user_id, list(zip(txn_ids, audit_ids, strict=True)))


def _payload(headers: Mapping[str, str]) -> dict[str, list[int]]:
    payload: dict[str, list[int]] = json.loads(headers["HX-Trigger"])["toast"]["undo_payload"]
    return payload


def _csv(ids: list[int]) -> str:
    return ",".join(str(i) for i in ids)


def _audit(conn: sqlite3.Connection, entity_type: str) -> list[sqlite3.Row]:
    return list(
        conn.execute("SELECT * FROM audit_log WHERE entity_type = ? ORDER BY id", (entity_type,))
    )


def test_recurring_undo_restores_full_state_and_writes_its_own_audit_row(
    _migrated: Settings,
) -> None:
    conn = get_connection(_migrated)
    rule_id = _rule(conn, USER)
    payload = _promote_recurring(conn, USER)
    advanced = recurring_repo.find_rule(conn, USER, rule_id)
    assert advanced is not None and advanced.next_due != DUE
    before = len(_audit(conn, "recurring_rule"))

    _undo_recurring(conn, USER, payload["promoted_txn_ids"], payload["advance_audit_ids"])

    restored = recurring_repo.find_rule(conn, USER, rule_id)
    assert restored is not None
    assert (restored.next_due, restored.last_promoted_date, restored.active) == (DUE, None, True)
    rows = _audit(conn, "recurring_rule")
    assert len(rows) == before + 1
    last = rows[-1]
    assert (last["operation"], last["user_id"], last["entity_id"]) == ("update", USER, rule_id)
    assert json.loads(last["prev_json"])["next_due"] == advanced.next_due.isoformat()
    assert json.loads(last["new_json"])["next_due"] == DUE.isoformat()
    txn = conn.execute(
        "SELECT deleted_at FROM transactions WHERE id = ?", (payload["promoted_txn_ids"][0],)
    ).fetchone()
    assert txn["deleted_at"] is not None
    assert _audit(conn, "transaction")[-1]["operation"] == "delete"
    conn.close()


def test_recurring_undo_refuses_a_rule_edited_since_the_batch(
    client: TestClient, _migrated: Settings
) -> None:
    conn = get_connection(_migrated)
    rule_id = _rule(conn, USER)
    payload = _promote_recurring(conn, USER)
    recurring_repo.update_rule(conn, USER, rule_id, PatchRecurringRule(default_amount=2_222))
    edited = recurring_repo.find_rule(conn, USER, rule_id)
    assert edited is not None
    audit_before = len(_audit(conn, "recurring_rule"))

    result = _undo_recurring(conn, USER, payload["promoted_txn_ids"], payload["advance_audit_ids"])

    assert result.skipped_rule_ids == (rule_id,)
    after = recurring_repo.find_rule(conn, USER, rule_id)
    assert after == edited
    assert len(_audit(conn, "recurring_rule")) == audit_before
    txn = conn.execute(
        "SELECT deleted_at FROM transactions WHERE id = ?", (payload["promoted_txn_ids"][0],)
    ).fetchone()
    assert txn["deleted_at"] is None
    conn.close()


def test_recurring_undo_ignores_an_audit_row_of_another_entity(
    client: TestClient, _migrated: Settings
) -> None:
    conn = get_connection(_migrated)
    rule_id = _rule(conn, USER)
    payload = _promote_recurring(conn, USER)
    advanced = recurring_repo.find_rule(conn, USER, rule_id)
    txn_audit_id = _audit(conn, "transaction")[-1]["id"]
    audit_before = len(_audit(conn, "recurring_rule"))

    _undo_recurring(conn, USER, payload["promoted_txn_ids"], [txn_audit_id])

    assert recurring_repo.find_rule(conn, USER, rule_id) == advanced
    assert len(_audit(conn, "recurring_rule")) == audit_before
    conn.close()


def test_recurring_undo_by_another_user_touches_nothing(
    client: TestClient, user_two_client: TestClient, _migrated: Settings
) -> None:
    conn = get_connection(_migrated)
    rule_id = _rule(conn, USER)
    payload = _promote_recurring(conn, USER)
    advanced = recurring_repo.find_rule(conn, USER, rule_id)
    audit_before = len(_audit(conn, "recurring_rule"))

    _undo_recurring(conn, OTHER, payload["promoted_txn_ids"], payload["advance_audit_ids"])

    assert recurring_repo.find_rule(conn, USER, rule_id) == advanced
    assert len(_audit(conn, "recurring_rule")) == audit_before
    txn = conn.execute(
        "SELECT deleted_at FROM transactions WHERE id = ?", (payload["promoted_txn_ids"][0],)
    ).fetchone()
    assert txn["deleted_at"] is None
    conn.close()


def test_planned_undo_unstamps_with_an_audit_row(client: TestClient, _migrated: Settings) -> None:
    conn = get_connection(_migrated)
    planned_id = _planned(conn, USER)
    payload = _payload(client.post("/planned/batch/promote-due").headers)
    txn_id = payload["promoted_txn_ids"][0]

    undo = client.post(
        "/planned/batch/undo",
        data={
            "promoted_txn_ids": _csv(payload["promoted_txn_ids"]),
            "promoted_planned_ids": _csv(payload["promoted_planned_ids"]),
        },
    )

    assert undo.status_code == 204
    row = planned_repo.find_by_id(conn, USER, planned_id)
    assert row is not None and row.promoted_to_txn_id is None
    last = _audit(conn, "planned_transaction")[-1]
    assert (last["operation"], last["user_id"], last["entity_id"]) == ("update", USER, planned_id)
    assert json.loads(last["prev_json"])["promoted_to_txn_id"] == txn_id
    assert json.loads(last["new_json"])["promoted_to_txn_id"] is None
    assert _audit(conn, "transaction")[-1]["operation"] == "delete"
    conn.close()


def test_planned_undo_leaves_a_row_stamped_by_another_promotion(
    client: TestClient, _migrated: Settings
) -> None:
    conn = get_connection(_migrated)
    planned_id = _planned(conn, USER)
    payload = _payload(client.post("/planned/batch/promote-due").headers)
    batch_txn = payload["promoted_txn_ids"][0]
    # The row is re-stamped with another transaction after the batch (the earlier
    # audit replay would have wiped it back to its pre-batch state).
    stamped = planned_repo.find_by_id(conn, USER, planned_id)
    assert stamped is not None
    other = transactions_repo.create(
        conn,
        USER,
        NewTransaction(
            operation_date=DUE,
            category_id=stamped.category_id,
            account_id=stamped.account_id,
            amount=1,
            description="other",
        ),
    )
    conn.execute(
        "UPDATE planned_transactions SET promoted_to_txn_id = ? WHERE id = ?",
        (other.id, planned_id),
    )
    audit_before = len(_audit(conn, "planned_transaction"))

    client.post(
        "/planned/batch/undo",
        data={
            "promoted_txn_ids": _csv([batch_txn]),
            "promoted_planned_ids": _csv([planned_id]),
        },
    )

    row = planned_repo.find_by_id(conn, USER, planned_id)
    assert row is not None and row.promoted_to_txn_id == other.id
    assert len(_audit(conn, "planned_transaction")) == audit_before
    conn.close()


def test_planned_undo_by_another_user_touches_nothing(
    client: TestClient, user_two_client: TestClient, _migrated: Settings
) -> None:
    conn = get_connection(_migrated)
    planned_id = _planned(conn, USER)
    payload = _payload(client.post("/planned/batch/promote-due").headers)
    audit_before = conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"]

    user_two_client.post(
        "/planned/batch/undo",
        data={
            "promoted_txn_ids": _csv(payload["promoted_txn_ids"]),
            "promoted_planned_ids": _csv(payload["promoted_planned_ids"]),
        },
    )

    row = planned_repo.find_by_id(conn, USER, planned_id)
    assert row is not None and row.promoted_to_txn_id == payload["promoted_txn_ids"][0]
    txn = conn.execute(
        "SELECT deleted_at FROM transactions WHERE id = ?", (payload["promoted_txn_ids"][0],)
    ).fetchone()
    assert txn["deleted_at"] is None
    assert conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"] == audit_before
    conn.close()


def test_preference_writes_are_audited(_migrated: Settings) -> None:
    conn = get_connection(_migrated)
    login_cookie(_migrated, user_id=OTHER, email="second@example.test")
    created = preferences_repo.upsert(conn, OTHER, "income_anchor_category_id", "7")
    preferences_repo.upsert(conn, OTHER, "income_anchor_category_id", "9")
    preferences_repo.delete(conn, OTHER, "income_anchor_category_id")

    rows = _audit(conn, "user_preference")
    assert [r["operation"] for r in rows] == ["create", "update", "delete"]
    assert {r["user_id"] for r in rows} == {OTHER}
    assert {r["entity_id"] for r in rows} == {created.id}
    assert json.loads(rows[1]["prev_json"])["value"] == "7"
    assert json.loads(rows[1]["new_json"])["value"] == "9"
    assert rows[2]["new_json"] is None
    conn.close()
