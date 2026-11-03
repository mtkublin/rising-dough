"""Shared helpers for every repository.

Policy (see ADR-0022):

- Every mutation goes through :func:`mutate`, which runs the action inside
  an explicit ``BEGIN`` / ``COMMIT`` and writes a matching ``audit_log``
  entry in the same transaction. On failure the whole thing rolls back.
- ``_dumps`` serialises frozen dataclasses and plain mappings for the
  ``prev_json`` / ``new_json`` columns.
- ``_utc_now_iso`` matches the ISO format used by the SQL
  ``strftime('%Y-%m-%dT%H:%M:%fZ', 'now')`` default so timestamps stored
  by Python and by SQLite are visually comparable.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any

from budget_planner.domain.request_ctx import RequestCtx

# Module-level singleton for the default empty request context —
# ``RequestCtx`` is frozen so sharing one instance is safe. Ruff B008
# forbids inlining the ``RequestCtx.empty()`` call in parameter defaults.
_EMPTY_REQUEST_CTX: RequestCtx = RequestCtx.empty()


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with millisecond precision."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _dumps(value: Any) -> str | None:
    """Serialise a dataclass or dict to JSON TEXT for the audit log."""
    if value is None:
        return None
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    return json.dumps(value, default=str, sort_keys=True)


def write_audit(
    conn: sqlite3.Connection,
    *,
    entity_type: str,
    entity_id: int,
    operation: str,
    prev: Any | None,
    new: Any | None,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
    actor_user_id: int | None = None,
) -> None:
    """Insert a single row into ``audit_log``.

    Called from inside :func:`mutate`; must share the same transaction.

    ``request_ctx`` carries the forensic metadata written to the four
    columns added by migration 0013 (``ip``, ``user_id``, ``session_id``,
    ``user_agent``). The default :meth:`RequestCtx.empty` matches
    pre-T-D14 behaviour — every new column lands as NULL — so existing
    call sites keep working without being retrofitted. See
    ``src/budget_planner/domain/request_ctx.py``.

    ``actor_user_id`` fills the column added by migration 0012: the admin
    issuing a privileged mutation against another user's row (T-D17,
    ADR-0073 §5). ``None`` (the default) leaves it NULL.
    """
    conn.execute(
        "INSERT INTO audit_log("
        "entity_type, entity_id, operation, prev_json, new_json, "
        "ip, user_id, session_id, user_agent, actor_user_id"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entity_type,
            entity_id,
            operation,
            _dumps(prev),
            _dumps(new),
            request_ctx.ip,
            request_ctx.user_id,
            request_ctx.session_id,
            request_ctx.user_agent,
            actor_user_id,
        ),
    )


_TX_DEPTH: dict[int, int] = {}


def _depth(conn: sqlite3.Connection) -> int:
    return _TX_DEPTH.get(id(conn), 0)


def _set_depth(conn: sqlite3.Connection, value: int) -> None:
    key = id(conn)
    if value == 0:
        _TX_DEPTH.pop(key, None)
    else:
        _TX_DEPTH[key] = value


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Explicit transaction context manager.

    First entry runs ``BEGIN``/``COMMIT``; nested entries use SQLite
    ``SAVEPOINT``/``RELEASE`` so services can compose multi-mutation flows
    (e.g. planned promotion) and keep the whole operation atomic.
    Requires ``isolation_level=None`` on the connection.
    """
    depth = _depth(conn)
    if depth == 0:
        conn.execute("BEGIN")
    else:
        conn.execute(f"SAVEPOINT sp_{depth}")
    _set_depth(conn, depth + 1)
    try:
        yield conn
    except Exception:
        if depth == 0:
            conn.execute("ROLLBACK")
        else:
            conn.execute(f"ROLLBACK TO sp_{depth}")
            conn.execute(f"RELEASE sp_{depth}")
        _set_depth(conn, depth)
        raise
    else:
        if depth == 0:
            conn.execute("COMMIT")
        else:
            conn.execute(f"RELEASE sp_{depth}")
        _set_depth(conn, depth)


def mutate[T](
    conn: sqlite3.Connection,
    *,
    entity_type: str,
    operation: str,
    prev: Any | None,
    action: Callable[[sqlite3.Connection], tuple[int, T]],
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> T:
    """Run ``action`` inside a transaction and emit a paired audit row.

    ``action(conn)`` returns ``(entity_id, new_value)`` where
    ``entity_id`` is the row id after the mutation and ``new_value`` is the
    hydrated DTO (or ``None`` for a delete).

    ``request_ctx`` is forwarded unchanged to :func:`write_audit` so the
    audit row carries the inbound request's forensic metadata (T-D14).
    Defaults to :meth:`RequestCtx.empty` — callers that have not yet
    threaded a real context behave exactly as before.
    """
    with transaction(conn):
        new_id, new_value = action(conn)
        write_audit(
            conn,
            entity_type=entity_type,
            entity_id=new_id,
            operation=operation,
            prev=prev,
            new=new_value,
            request_ctx=request_ctx,
        )
        return new_value


def require_owned(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    account_ids: Iterable[int | None] = (),
    category_ids: Iterable[int | None] = (),
) -> None:
    """Raise :class:`LookupError` unless every referenced FK row belongs to ``user_id``.

    Guards writes against cross-user FK linking (T-D16 / ADR-0061 §5): a
    leaked ``account_id`` / ``category_id`` from another user must not be
    attachable to the caller's rows. ``None`` ids are skipped. Soft-deleted
    parents still count as owned — liveness is the service layer's concern.
    """
    for account_id in {a for a in account_ids if a is not None}:
        row = conn.execute(
            "SELECT 1 FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id)
        ).fetchone()
        if row is None:
            raise LookupError(f"account {account_id} not found")
    for category_id in {c for c in category_ids if c is not None}:
        row = conn.execute(
            "SELECT 1 FROM categories WHERE id = ? AND user_id = ?", (category_id, user_id)
        ).fetchone()
        if row is None:
            raise LookupError(f"category {category_id} not found")


def parse_dt(value: str | None) -> datetime | None:
    """Parse a UTC-ISO timestamp from the DB (``...Z`` suffix) to ``datetime``."""
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_dt_required(value: str) -> datetime:
    """Variant of :func:`parse_dt` for ``NOT NULL`` columns."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
