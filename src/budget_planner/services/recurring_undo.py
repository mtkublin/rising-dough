"""Undo of a batch recurring promote-due (ADR-0019 amendment 2026-11-21, T-Q228, Q-024).

Undo is an audited action: it never erases or rewrites the trail, it appends its
own ``update`` / ``delete`` audit rows. It targets the specific audit row each
rule advance wrote, never "the latest audit row of the entity".
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from budget_planner.domain.audit import AuditEntry
from budget_planner.domain.enums import AuditOperation
from budget_planner.repositories import (
    audit as audit_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from budget_planner.repositories._shared import transaction as db_transaction
from budget_planner.services import audit as audit_svc
from budget_planner.services.recurring import restore_progress, unpromote_override


@dataclass(frozen=True, slots=True)
class BatchUndoResult:
    """Outcome of :func:`undo_batch`."""

    deleted_txn_ids: tuple[int, ...]
    restored_rule_ids: tuple[int, ...]
    skipped_rule_ids: tuple[int, ...]


def _belongs_to_batch(
    conn: sqlite3.Connection, user_id: int, txn_id: int, entry: AuditEntry
) -> bool:
    """Whether ``txn_id`` is the promotion that the rule-advance row ``entry`` wrote.

    The transaction carries the rule and the due date it was promoted for; the
    advance row's ``prev_json.next_due`` is that same due date. A pair that does
    not agree (another rule's row, an older or newer batch, a hand-picked id) is
    not part of one batch (T-Q288).
    """
    txn = transactions_repo.find_by_id(conn, user_id, txn_id, include_deleted=True)
    if txn is None or entry.prev_json is None:
        return False
    prev_due = json.loads(entry.prev_json).get("next_due")
    return (
        txn.promoted_from_recurring_rule_id == entry.entity_id
        and txn.promoted_from_recurring_date is not None
        and txn.promoted_from_recurring_date.isoformat() == prev_due
    )


def _restore_rule(conn: sqlite3.Connection, user_id: int, txn_id: int, audit_id: int) -> int | None:
    """Restore the rule behind ``audit_id`` (written by ``txn_id``'s promotion); audited.

    Returns the rule id when restored, ``-rule_id`` when the rule changed since
    (left as is), ``None`` when the audit row is not an advance of the user's rule.
    """
    entry = audit_repo.find_entry(conn, user_id, audit_id)
    if (
        entry is None
        or entry.entity_type != "recurring_rule"
        or entry.operation is not AuditOperation.UPDATE
        or entry.prev_json is None
        or not _belongs_to_batch(conn, user_id, txn_id, entry)
    ):
        return None
    rule_id = entry.entity_id
    current = recurring_repo.find_rule(conn, user_id, rule_id, include_deleted=True)
    newest = audit_repo.latest_entry_id(conn, user_id, "recurring_rule", rule_id)
    if current is None or newest != audit_id:
        return -rule_id
    restore_progress(conn, user_id, rule_id, json.loads(entry.prev_json))
    audit_svc.write_audit(
        conn,
        entity_type="recurring_rule",
        entity_id=rule_id,
        operation="update",
        prev=current,
        new=recurring_repo.find_rule(conn, user_id, rule_id, include_deleted=True),
        user_id=user_id,
    )
    unpromote_override(conn, user_id, rule_id, txn_id)
    return rule_id


def undo_batch(
    conn: sqlite3.Connection,
    user_id: int,
    steps: Sequence[tuple[int, int]],
) -> BatchUndoResult:
    """Reverse a batch recurring promote in one transaction.

    ``steps`` pairs each promoted transaction id with the id of the audit row
    its rule advance wrote. Per step the rule is restored from that row's
    ``prev_json`` only while that row is still the newest audit row of the rule
    (the rule is unchanged since the batch), the restore writes its own audit
    row, and the transaction is soft-deleted. A rule edited meanwhile is left as
    is, its transaction is kept, and it is reported in ``skipped_rule_ids``.
    Only audit rows written by the batch being undone are accepted: the row must
    be an advance of the rule the transaction was promoted from, for that
    transaction's due date. Any other row (another user, entity, operation, rule
    or batch) is ignored and nothing changes (T-Q288). The override the promotion
    consumed has its ``promoted_to_txn_id`` stamp cleared, audited.
    """
    deleted: list[int] = []
    restored: list[int] = []
    skipped: list[int] = []
    with db_transaction(conn):
        for txn_id, audit_id in steps:
            rule_id = _restore_rule(conn, user_id, txn_id, audit_id)
            if rule_id is None:
                continue
            if rule_id < 0:
                skipped.append(-rule_id)
                continue
            restored.append(rule_id)
            if transactions_repo.find_by_id(conn, user_id, txn_id) is not None:
                transactions_repo.soft_delete(conn, user_id, txn_id)
                deleted.append(txn_id)
    return BatchUndoResult(
        deleted_txn_ids=tuple(deleted),
        restored_rule_ids=tuple(restored),
        skipped_rule_ids=tuple(skipped),
    )


__all__ = ["BatchUndoResult", "undo_batch"]
