"""Retention purge SQL (T-D60, ADR-0078 §7).

Audit rows are never deleted (ADR-0019): only the personal-data columns
``ip`` / ``user_agent`` are nulled. Ended ``sessions`` rows are deleted.

All app writers store ISO-8601 UTC with a ``T`` separator and ``Z`` suffix
(``strftime('%Y-%m-%dT%H:%M:%fZ')`` defaults, ``sessions._iso``), but the
comparison is normalised anyway: ``datetime(col)`` parses ``T``/space
separators, ``Z`` / ``+HH:MM`` offsets and fractional seconds and yields UTC
``YYYY-MM-DD HH:MM:SS``, compared against ``datetime(?)`` of the cutoff.
Unparseable values yield NULL and are therefore never purged.
"""

from __future__ import annotations

import sqlite3

from budget_planner.repositories._shared import transaction


def scrub_audit_request_context(conn: sqlite3.Connection, cutoff_iso: str) -> int:
    """NULL ``ip`` / ``user_agent`` on audit rows with ``changed_at`` before the cutoff."""
    with transaction(conn):
        cur = conn.execute(
            "UPDATE audit_log SET ip = NULL, user_agent = NULL "
            "WHERE datetime(changed_at) < datetime(?) "
            "AND (ip IS NOT NULL OR user_agent IS NOT NULL)",
            (cutoff_iso,),
        )
    return cur.rowcount


def delete_ended_sessions(conn: sqlite3.Connection, cutoff_iso: str) -> int:
    """Delete sessions revoked or expired before the cutoff (live sessions untouched)."""
    with transaction(conn):
        cur = conn.execute(
            "DELETE FROM sessions WHERE datetime(expires_at) < datetime(?) "
            "OR (revoked_at IS NOT NULL AND datetime(revoked_at) < datetime(?))",
            (cutoff_iso, cutoff_iso),
        )
    return cur.rowcount


__all__ = ["delete_ended_sessions", "scrub_audit_request_context"]
