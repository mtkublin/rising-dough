"""Audit-free repository helpers (ADR-0022 amendment 2026-11-21, T-Q228, Q-049).

These UPDATEs deliberately skip ``audit_log``: the orchestrating service in
``services/recurring.py`` writes one paired audit row for the whole step. They
are importable only from ``services/recurring.py``
(``tests/architecture/test_unaudited_imports.py``). Every statement is scoped by
``user_id``.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from budget_planner import clock


def set_next_due(
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    *,
    next_due: date,
    last_promoted_date: date | None,
) -> None:
    """Thin helper for the T-118 promotion service.

    Audit-free: the orchestrating service writes the paired audit entry.
    """
    conn.execute(
        "UPDATE recurring_rules SET next_due = ?, last_promoted_date = ?, "
        "updated_at = ? "
        "WHERE id = ? AND user_id = ?",
        (
            next_due.isoformat(),
            last_promoted_date.isoformat() if last_promoted_date is not None else None,
            clock.utc_now_iso(),
            rule_id,
            user_id,
        ),
    )


def set_inactive(conn: sqlite3.Connection, user_id: int, rule_id: int) -> None:
    """Thin helper for the T-118 promotion service — mark a rule inactive."""
    conn.execute(
        "UPDATE recurring_rules SET active = 0, updated_at = ? WHERE id = ? AND user_id = ?",
        (clock.utc_now_iso(), rule_id, user_id),
    )


def mark_override_promoted(
    conn: sqlite3.Connection,
    user_id: int,
    override_id: int,
    *,
    txn_id: int,
) -> None:
    """Stamp ``promoted_to_txn_id = txn_id`` on an override (ADR-0046 step 6e).

    FK-scoped: the UPDATE joins through ``recurring_rules.user_id`` so a
    leaked override id for a different user is a no-op.
    """
    conn.execute(
        "UPDATE recurring_rule_overrides AS o "
        "SET promoted_to_txn_id = ? "
        "WHERE o.id = ? "
        "AND EXISTS (SELECT 1 FROM recurring_rules r "
        "            WHERE r.id = o.rule_id AND r.user_id = ?)",
        (txn_id, override_id, user_id),
    )


def clear_override_promoted(
    conn: sqlite3.Connection,
    user_id: int,
    override_id: int,
    *,
    txn_id: int,
) -> int:
    """Compare-and-set ``promoted_to_txn_id`` back to NULL (T-Q288, undo of a promotion).

    Clears the stamp only while it still equals ``txn_id`` and the override's rule
    belongs to ``user_id``. Returns the number of rows changed (0 or 1).
    """
    cur = conn.execute(
        "UPDATE recurring_rule_overrides AS o "
        "SET promoted_to_txn_id = NULL "
        "WHERE o.id = ? AND o.promoted_to_txn_id = ? "
        "AND EXISTS (SELECT 1 FROM recurring_rules r "
        "            WHERE r.id = o.rule_id AND r.user_id = ?)",
        (override_id, txn_id, user_id),
    )
    return cur.rowcount


def restore_rule_progress(
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    *,
    next_due: date,
    last_promoted_date: date | None,
    active: bool,
) -> None:
    """Restore a rule's promotion progress (undo of a batch promote)."""
    conn.execute(
        "UPDATE recurring_rules SET next_due = ?, last_promoted_date = ?, active = ?, "
        "updated_at = ? "
        "WHERE id = ? AND user_id = ?",
        (
            next_due.isoformat(),
            last_promoted_date.isoformat() if last_promoted_date is not None else None,
            1 if active else 0,
            clock.utc_now_iso(),
            rule_id,
            user_id,
        ),
    )


__all__ = [
    "clear_override_promoted",
    "mark_override_promoted",
    "restore_rule_progress",
    "set_inactive",
    "set_next_due",
]
