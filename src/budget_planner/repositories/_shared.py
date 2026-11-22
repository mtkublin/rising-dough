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
- The ``*_owned`` helpers (:class:`OwnedTable`) are the one implementation of
  user-scoped, soft-deleting, audited CRUD for the user-owned tables
  (ADR-0022 amendment 2026-11-22, T-Q260). Table and column names only ever
  come from literals in the repository modules and are validated here; values
  are always bound parameters.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from budget_planner import clock
from budget_planner.domain.request_ctx import RequestCtx

# Module-level singleton for the default empty request context —
# ``RequestCtx`` is frozen so sharing one instance is safe. Ruff B008
# forbids inlining the ``RequestCtx.empty()`` call in parameter defaults.
_EMPTY_REQUEST_CTX: RequestCtx = RequestCtx.empty()
_SAVEPOINT = "bp_nested"


def _dumps(value: Any) -> str | None:
    """Serialise a dataclass or dict to JSON TEXT for the audit log."""
    if value is None:
        return None
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    return json.dumps(value, default=str, sort_keys=True)


def attributed_ctx(request_ctx: RequestCtx, user_id: int | None) -> RequestCtx:
    """Return ``request_ctx`` with ``user_id`` set to the row owner (T-D145)."""
    return request_ctx if user_id is None else replace(request_ctx, user_id=user_id)


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


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Explicit transaction context manager.

    First entry runs ``BEGIN IMMEDIATE``/``COMMIT`` (ADR-0137): the write
    lock is taken up front and waits on ``busy_timeout``, so guard reads
    made inside the block cannot go stale and concurrent writers queue
    instead of failing with "database is locked" on lock upgrade.
    Nested entries use SQLite
    ``SAVEPOINT``/``RELEASE`` so services can compose multi-mutation flows
    (e.g. planned promotion) and keep the whole operation atomic.
    Requires ``isolation_level=None`` on the connection.
    """
    # Nesting is read from the connection itself (no module-level depth map):
    # an open transaction means this entry is nested. SQLite resolves a repeated
    # savepoint name to the innermost one, so a single name nests correctly.
    is_outermost = not conn.in_transaction
    if is_outermost:
        conn.execute("BEGIN IMMEDIATE")
    else:
        conn.execute(f"SAVEPOINT {_SAVEPOINT}")
    try:
        yield conn
    except Exception:
        if is_outermost:
            conn.execute("ROLLBACK")
        else:
            conn.execute(f"ROLLBACK TO {_SAVEPOINT}")
            conn.execute(f"RELEASE {_SAVEPOINT}")
        raise
    else:
        if is_outermost:
            conn.execute("COMMIT")
        else:
            conn.execute(f"RELEASE {_SAVEPOINT}")


def mutate[T](
    conn: sqlite3.Connection,
    *,
    entity_type: str,
    operation: str,
    prev: Any | None,
    action: Callable[[sqlite3.Connection], tuple[int, T]],
    user_id: int | None,
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

    ``user_id`` is mandatory (T-D145, ADR-0122): the owner of the mutated row.
    Domain repositories only ever mutate the caller's own rows, so it is
    recorded as both ``audit_log.user_id`` and ``actor_user_id``. Pass ``None``
    only for global, ownerless tables (``fx_rates``).
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
            request_ctx=attributed_ctx(request_ctx, user_id),
            actor_user_id=user_id,
        )
        return new_value


def require_owned(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    account_ids: Iterable[int | None] = (),
    category_ids: Iterable[int | None] = (),
    include_deleted: bool = True,
) -> None:
    """Raise :class:`LookupError` unless every referenced FK row belongs to ``user_id``.

    Guards writes against cross-user FK linking (T-D16 / ADR-0061 §5): a
    leaked ``account_id`` / ``category_id`` from another user must not be
    attachable to the caller's rows. ``None`` ids are skipped. Soft-deleted
    parents still count as owned by default (``include_deleted=True``);
    liveness is the service layer's concern (ADR-0019 note, T-Q268).
    """
    live = "" if include_deleted else " AND deleted_at IS NULL"
    for account_id in {a for a in account_ids if a is not None}:
        row = conn.execute(
            f"SELECT 1 FROM accounts WHERE id = ? AND user_id = ?{live}", (account_id, user_id)
        ).fetchone()
        if row is None:
            raise LookupError(f"account {account_id} not found")
    for category_id in {c for c in category_ids if c is not None}:
        row = conn.execute(
            f"SELECT 1 FROM categories WHERE id = ? AND user_id = ?{live}", (category_id, user_id)
        ).fetchone()
        if row is None:
            raise LookupError(f"category {category_id} not found")


FilterPart = tuple[str, list[object]]
"""One WHERE clause (``?`` placeholders) with its bound parameters."""


def in_parts(column: str, values: Iterable[object]) -> list[FilterPart]:
    """``column IN (?, ...)`` as a one-element part list; empty when ``values`` is empty."""
    bound = list(values)
    if not bound:
        return []
    return [(f"{column} IN ({','.join('?' for _ in bound)})", bound)]


def join_filter_parts(parts: Iterable[FilterPart]) -> tuple[list[str], list[object]]:
    """Split filter parts into the clause list and the flat parameter list."""
    pairs = list(parts)
    return [clause for clause, _ in pairs], [value for _, bound in pairs for value in bound]


def parse_dt(value: str | None) -> datetime | None:
    """Parse a UTC-ISO timestamp from the DB (``...Z`` suffix) to ``datetime``."""
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_dt_required(value: str) -> datetime:
    """Variant of :func:`parse_dt` for ``NOT NULL`` columns."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Generic user-owned CRUD (T-Q260, ADR-0022 amendment 2026-11-22).
# ---------------------------------------------------------------------------
_NOW_SQL = "(strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
_IDENT = re.compile(r"[a-z][a-z0-9_]*")
_COLUMN_LIST = re.compile(r"[a-z][a-z0-9_]*(, [a-z][a-z0-9_]*)*")
_ORDER_BY = re.compile(r"[a-z][a-z0-9_]*( (ASC|DESC))?(, [a-z][a-z0-9_]*( (ASC|DESC))?)*")
_OWNED_TABLES = frozenset(
    {
        "accounts",
        "categories",
        "planned_transactions",
        "transactions",
        "recurring_rules",
        "budget_defaults",
        "budget_recurring_overrides",
        "budget_one_off_overrides",
    }
)


@dataclass(frozen=True, slots=True)
class OwnedTable[R]:
    """Static description of one soft-deleting, user-owned table.

    ``table`` must be one of the allowlisted literals; ``columns`` and
    ``order_by`` must be plain identifier lists. Violations raise
    :class:`ValueError` at construction, so a repository module that builds
    its spec at import time fails loudly instead of interpolating anything
    unexpected into SQL.
    """

    table: str
    entity_type: str
    columns: str
    hydrate: Callable[[sqlite3.Row], R]
    order_by: str = "id ASC"

    def __post_init__(self) -> None:
        if self.table not in _OWNED_TABLES:
            raise ValueError(f"table {self.table!r} is not an allowlisted owned table")
        if not _COLUMN_LIST.fullmatch(self.columns):
            raise ValueError(f"invalid column list {self.columns!r}")
        if not _ORDER_BY.fullmatch(self.order_by):
            raise ValueError(f"invalid order_by {self.order_by!r}")


def _identifiers(names: Iterable[str]) -> list[str]:
    checked = list(names)
    for name in checked:
        if not _IDENT.fullmatch(name):
            raise ValueError(f"invalid column name {name!r}")
    return checked


def _live_clause(include_deleted: bool) -> str:
    return "" if include_deleted else " AND deleted_at IS NULL"


def find_owned[R](
    conn: sqlite3.Connection,
    spec: OwnedTable[R],
    user_id: int,
    where: Mapping[str, object],
    *,
    include_deleted: bool = False,
) -> R | None:
    """Return the caller's row matching every ``where`` column, or ``None``."""
    predicate = " AND ".join(f"{key} = ?" for key in _identifiers(where))
    sql = (
        f"SELECT {spec.columns} FROM {spec.table} "
        f"WHERE {predicate} AND user_id = ?{_live_clause(include_deleted)}"
    )
    row = conn.execute(sql, (*where.values(), user_id)).fetchone()
    return spec.hydrate(row) if row is not None else None


def list_owned[R](
    conn: sqlite3.Connection,
    spec: OwnedTable[R],
    user_id: int,
    *,
    where: Mapping[str, object] | None = None,
    include_deleted: bool = False,
) -> list[R]:
    """List the caller's rows (optionally filtered by equality) in ``spec.order_by``."""
    extra = {} if where is None else dict(where)
    predicates = ["user_id = ?"]
    for key in _identifiers(extra):
        predicates.append(f"{key} = ?")
    sql = (
        f"SELECT {spec.columns} FROM {spec.table} WHERE {' AND '.join(predicates)}"
        f"{_live_clause(include_deleted)} ORDER BY {spec.order_by}"
    )
    rows = conn.execute(sql, (user_id, *extra.values())).fetchall()
    return [spec.hydrate(r) for r in rows]


def list_recently_deleted_owned[R](
    conn: sqlite3.Connection,
    spec: OwnedTable[R],
    user_id: int,
    *,
    days: int = 90,
    limit: int = 500,
) -> list[R]:
    """Soft-deleted rows of the caller within the last ``days`` days, newest first (T-R70)."""
    sql = (
        f"SELECT {spec.columns} FROM {spec.table} "
        "WHERE user_id = ? AND deleted_at IS NOT NULL AND deleted_at > ? "
        "ORDER BY deleted_at DESC LIMIT ?"
    )
    cutoff = clock.iso_utc(clock.utc_now() - timedelta(days=days))  # same text format as deleted_at
    rows = conn.execute(sql, (user_id, cutoff, limit)).fetchall()
    return [spec.hydrate(r) for r in rows]


def insert_owned[R](
    conn: sqlite3.Connection,
    spec: OwnedTable[R],
    user_id: int,
    values: Mapping[str, object],
) -> R:
    """Insert one row owned by ``user_id`` and write the ``create`` audit row."""
    columns = ["user_id", *_identifiers(values)]
    marks = ", ".join("?" for _ in columns)

    def _insert_row(c: sqlite3.Connection) -> tuple[int, R]:
        cursor = c.execute(
            f"INSERT INTO {spec.table}({', '.join(columns)}) VALUES ({marks})",
            (user_id, *values.values()),
        )
        new_id = int(cursor.lastrowid or 0)
        created = find_owned(c, spec, user_id, {"id": new_id})
        if created is None:
            raise LookupError(f"{spec.entity_type} {new_id} vanished mid-mutation")
        return new_id, created

    return mutate(
        conn,
        entity_type=spec.entity_type,
        operation="create",
        prev=None,
        action=_insert_row,
        user_id=user_id,
    )


def update_owned[R](
    conn: sqlite3.Connection,
    spec: OwnedTable[R],
    user_id: int,
    row_id: int,
    changes: Mapping[str, object],
    *,
    account_ids: Iterable[int | None] = (),
    category_ids: Iterable[int | None] = (),
) -> R:
    """Patch the caller's row (soft-deleted rows included) and write the ``update`` audit row.

    Raises :class:`LookupError` when the row is not the caller's. FK targets in
    ``account_ids`` / ``category_ids`` are checked with :func:`require_owned`
    after the row lookup. An empty ``changes`` still audits (``updated_at``
    is not bumped).
    """
    prev = find_owned(conn, spec, user_id, {"id": row_id}, include_deleted=True)
    if prev is None:
        raise LookupError(f"{spec.entity_type} {row_id} not found")
    require_owned(conn, user_id, account_ids=account_ids, category_ids=category_ids)
    sets = [f"{field} = ?" for field in _identifiers(changes)]

    def _update_row(c: sqlite3.Connection) -> tuple[int, R]:
        if sets:
            c.execute(
                f"UPDATE {spec.table} SET {', '.join([*sets, f'updated_at = {_NOW_SQL}'])} "
                "WHERE id = ? AND user_id = ?",
                (*changes.values(), row_id, user_id),
            )
        updated = find_owned(c, spec, user_id, {"id": row_id}, include_deleted=True)
        if updated is None:
            raise LookupError(f"{spec.entity_type} {row_id} vanished mid-mutation")
        return row_id, updated

    return mutate(
        conn,
        entity_type=spec.entity_type,
        operation="update",
        prev=prev,
        action=_update_row,
        user_id=user_id,
    )


def soft_delete_found[R](
    conn: sqlite3.Connection,
    spec: OwnedTable[R],
    user_id: int,
    row_id: int,
    prev: R,
) -> None:
    """Soft-delete the live row ``row_id`` whose current state is ``prev`` and audit it."""

    def _soft_delete_row(c: sqlite3.Connection) -> tuple[int, None]:
        c.execute(
            f"UPDATE {spec.table} SET deleted_at = {_NOW_SQL}, updated_at = {_NOW_SQL} "
            "WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (row_id, user_id),
        )
        return row_id, None

    mutate(
        conn,
        entity_type=spec.entity_type,
        operation="delete",
        prev=prev,
        action=_soft_delete_row,
        user_id=user_id,
    )


def soft_delete_owned[R](
    conn: sqlite3.Connection, spec: OwnedTable[R], user_id: int, row_id: int
) -> None:
    """Soft-delete the caller's live row; a silent no-op when missing or already deleted."""
    prev = find_owned(conn, spec, user_id, {"id": row_id})
    if prev is None:
        return
    soft_delete_found(conn, spec, user_id, row_id, prev)


def undelete_owned[R](
    conn: sqlite3.Connection, spec: OwnedTable[R], user_id: int, row_id: int
) -> R:
    """Restore a soft-deleted row of the caller and write the ``undelete`` audit row."""
    prev = find_owned(conn, spec, user_id, {"id": row_id}, include_deleted=True)
    if prev is None:
        raise LookupError(f"{spec.entity_type} {row_id} not found")

    def _undelete_row(c: sqlite3.Connection) -> tuple[int, R]:
        c.execute(
            f"UPDATE {spec.table} SET deleted_at = NULL, updated_at = {_NOW_SQL} "
            "WHERE id = ? AND user_id = ?",
            (row_id, user_id),
        )
        restored = find_owned(c, spec, user_id, {"id": row_id})
        if restored is None:
            raise LookupError(f"{spec.entity_type} {row_id} vanished mid-mutation")
        return row_id, restored

    return mutate(
        conn,
        entity_type=spec.entity_type,
        operation="undelete",
        prev=prev,
        action=_undelete_row,
        user_id=user_id,
    )
