"""First-run setup marker repository (T-UR32, ADR-0134 section 9).

``setup_token_consumed`` is a single-row, system-level table (``id = 1``); it
is not user-owned data, so its statements carry no ``user_id`` filter
(the *created* admin is recorded in the audit row only). The
consume write is audited as ``setup_token`` and must run inside the same
transaction that creates the first admin.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from budget_planner import clock
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories._shared import write_audit

ENTITY_TYPE = "setup_token"
_MARKER_ID = 1
_EMPTY_REQUEST_CTX: RequestCtx = RequestCtx.empty()


def is_consumed(conn: sqlite3.Connection) -> bool:
    """``True`` iff the setup token has been consumed."""
    row = conn.execute("SELECT 1 FROM setup_token_consumed WHERE id = ?", (_MARKER_ID,)).fetchone()
    return row is not None


def has_credentialed_user(conn: sqlite3.Connection) -> bool:
    """``True`` iff any live user has an email.

    The pre-v3 legacy owner row (no email, cannot sign in) does not count.
    """
    row = conn.execute(
        "SELECT 1 FROM users WHERE email IS NOT NULL AND deleted_at IS NULL LIMIT 1"
    ).fetchone()
    return row is not None


def mark_consumed(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> datetime:
    """Insert the consumed marker for ``user_id`` and audit it; returns the stamp.

    Raises ``sqlite3.IntegrityError`` when already consumed (primary key).
    """
    stamp = clock.utc_now()
    iso = clock.iso_utc(stamp)
    conn.execute(
        "INSERT INTO setup_token_consumed (id, consumed_at) VALUES (?, ?)",
        (_MARKER_ID, iso),
    )
    write_audit(
        conn,
        entity_type=ENTITY_TYPE,
        entity_id=_MARKER_ID,
        operation="create",
        prev=None,
        new={"consumed_at": iso, "user_id": user_id},
        request_ctx=request_ctx,
    )
    return stamp
