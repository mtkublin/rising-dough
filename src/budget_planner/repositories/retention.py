"""Retention purge SQL (T-D60, ADR-0078 §7).

Audit rows are never deleted (ADR-0019): only the personal-data columns
``ip`` / ``user_agent`` are nulled. Ended ``sessions`` rows are deleted.
Cutoffs are compared on the first 19 characters (``YYYY-MM-DDTHH:MM:SS``)
so mixed millisecond / microsecond stored precision cannot skew a boundary.
"""

from __future__ import annotations

import sqlite3

from budget_planner.repositories._shared import transaction

_TS_PREFIX = 19


def _prefix(cutoff_iso: str) -> str:
    return cutoff_iso[:_TS_PREFIX]


def scrub_audit_request_context(conn: sqlite3.Connection, cutoff_iso: str) -> int:
    """NULL ``ip`` / ``user_agent`` on audit rows with ``changed_at`` before the cutoff."""
    with transaction(conn):
        cur = conn.execute(
            "UPDATE audit_log SET ip = NULL, user_agent = NULL "
            "WHERE substr(changed_at, 1, ?) < ? "
            "AND (ip IS NOT NULL OR user_agent IS NOT NULL)",
            (_TS_PREFIX, _prefix(cutoff_iso)),
        )
    return cur.rowcount


def delete_ended_sessions(conn: sqlite3.Connection, cutoff_iso: str) -> int:
    """Delete sessions revoked or expired before the cutoff (live sessions untouched)."""
    cut = _prefix(cutoff_iso)
    with transaction(conn):
        cur = conn.execute(
            "DELETE FROM sessions WHERE substr(expires_at, 1, ?) < ? "
            "OR (revoked_at IS NOT NULL AND substr(revoked_at, 1, ?) < ?)",
            (_TS_PREFIX, cut, _TS_PREFIX, cut),
        )
    return cur.rowcount


__all__ = ["delete_ended_sessions", "scrub_audit_request_context"]
