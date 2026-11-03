"""Fixed-window counters for auth rate limiting (T-D09, ADR-0072).

Backs ``auth_rate_limit`` (migration 0014). The table is not user-owned:
keys are opaque strings built by :mod:`budget_planner.services.rate_limit`
(e.g. ``login:60s:ip=…|email=…``), so these functions take ``(conn, key, …)``
rather than ``(conn, user_id, …)`` — exempted in the T-D16 architecture test.

Counter rows are bookkeeping, not user data: they are not audited and not
soft-deleted. Stale buckets are hard-deleted by :func:`prune`.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def hit(conn: sqlite3.Connection, key: str, bucket_start: datetime) -> int:
    """Increment the ``(key, bucket_start)`` counter and return the new count.

    One atomic UPSERT statement, so concurrent requests never lose a hit.
    """
    row = conn.execute(
        "INSERT INTO auth_rate_limit (key, bucket_start, count) VALUES (?, ?, 1) "
        "ON CONFLICT (key, bucket_start) DO UPDATE SET count = count + 1 "
        "RETURNING count",
        (key, _iso(bucket_start)),
    ).fetchone()
    return int(row[0])


def get_count(conn: sqlite3.Connection, key: str, bucket_start: datetime) -> int:
    """Return the current count for ``(key, bucket_start)``; 0 when absent."""
    row = conn.execute(
        "SELECT count FROM auth_rate_limit WHERE key = ? AND bucket_start = ?",
        (key, _iso(bucket_start)),
    ).fetchone()
    return 0 if row is None else int(row[0])


def prune(conn: sqlite3.Connection, before: datetime) -> int:
    """Delete every bucket that started before ``before``; return rows removed."""
    cur = conn.execute("DELETE FROM auth_rate_limit WHERE bucket_start < ?", (_iso(before),))
    return cur.rowcount
