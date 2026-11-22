"""Transaction repository — pure CRUD + rich filter support.

## User-scoping discipline (T-D16 / ADR-0061 §5)

Every function takes ``user_id`` as the first positional arg after ``conn``;
every SELECT / UPDATE / DELETE carries ``user_id = :user_id``; the
``tests/architecture/test_user_id_filter.py`` static test backstops the rule.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from budget_planner.domain.transactions import (
    NewTransaction,
    PatchTransaction,
    Transaction,
    TransactionFilter,
)
from budget_planner.repositories._shared import (
    FilterPart,
    OwnedTable,
    find_owned,
    in_parts,
    insert_owned,
    join_filter_parts,
    list_recently_deleted_owned,
    parse_dt,
    parse_dt_required,
    require_owned,
    soft_delete_owned,
    undelete_owned,
    update_owned,
)

_COLUMNS = (
    "id, user_id, operation_date, category_id, account_id, dest_account_id, "
    "amount, description, promoted_from_planned_id, "
    "promoted_from_recurring_rule_id, promoted_from_recurring_date, "
    "created_at, updated_at, deleted_at"
)


def _row_to_txn(row: sqlite3.Row) -> Transaction:
    return Transaction(
        id=row["id"],
        user_id=row["user_id"],
        operation_date=date.fromisoformat(row["operation_date"]),
        category_id=row["category_id"],
        account_id=row["account_id"],
        dest_account_id=row["dest_account_id"],
        amount=row["amount"],
        description=row["description"],
        promoted_from_planned_id=row["promoted_from_planned_id"],
        promoted_from_recurring_rule_id=row["promoted_from_recurring_rule_id"],
        promoted_from_recurring_date=(
            date.fromisoformat(row["promoted_from_recurring_date"])
            if row["promoted_from_recurring_date"] is not None
            else None
        ),
        created_at=parse_dt_required(row["created_at"]),
        updated_at=parse_dt_required(row["updated_at"]),
        deleted_at=parse_dt(row["deleted_at"]),
    )


_TRANSACTIONS: OwnedTable[Transaction] = OwnedTable(
    table="transactions",
    entity_type="transaction",
    columns=_COLUMNS,
    hydrate=_row_to_txn,
    order_by="operation_date DESC, id DESC",
)


def find_by_id(
    conn: sqlite3.Connection,
    user_id: int,
    txn_id: int,
    *,
    include_deleted: bool = False,
) -> Transaction | None:
    return find_owned(conn, _TRANSACTIONS, user_id, {"id": txn_id}, include_deleted=include_deleted)


# ADR-0136: the one predicate that hides soft-deleted accounts from derived reads.
_LIVE_ACCOUNT = (
    "t.account_id IN (SELECT a.id FROM accounts a "
    "WHERE a.user_id = t.user_id AND a.deleted_at IS NULL)"
)


def _txn_filter_clauses(
    filters: TransactionFilter,
    include_deleted: bool,
) -> tuple[list[str], list[object]]:
    return join_filter_parts(
        [
            *_txn_date_parts(filters),
            *in_parts("t.account_id", filters.account_ids),
            *in_parts("t.category_id", filters.category_ids),
            *in_parts("c.direction", (d.value for d in filters.directions or ())),
            *_txn_amount_text_parts(filters),
            *_txn_scope_parts(filters, include_deleted),
        ]
    )


def _txn_date_parts(filters: TransactionFilter) -> list[FilterPart]:
    parts: list[FilterPart] = []
    if filters.date_from is not None:
        parts.append(("t.operation_date >= ?", [filters.date_from.isoformat()]))
    if filters.date_to is not None:
        parts.append(("t.operation_date <= ?", [filters.date_to.isoformat()]))
    if filters.up_to_date is not None:
        parts.append(("t.operation_date <= ?", [filters.up_to_date.isoformat()]))
    return parts


def _txn_amount_text_parts(filters: TransactionFilter) -> list[FilterPart]:
    parts: list[FilterPart] = []
    if filters.amount_min is not None:
        parts.append(("t.amount >= ?", [filters.amount_min]))
    if filters.amount_max is not None:
        parts.append(("t.amount <= ?", [filters.amount_max]))
    if filters.description_contains is not None:
        parts.append(("t.description LIKE ?", [f"%{filters.description_contains}%"]))
    return parts


def _txn_scope_parts(filters: TransactionFilter, include_deleted: bool) -> list[FilterPart]:
    parts: list[FilterPart] = []
    if filters.account_or_dest is not None:
        parts.append(
            (
                "(t.account_id = ? OR t.dest_account_id = ?)",
                [filters.account_or_dest, filters.account_or_dest],
            )
        )
    if filters.live_accounts_only:
        parts.append((_LIVE_ACCOUNT, []))
    if not include_deleted:
        parts.append(("t.deleted_at IS NULL", []))
    return parts


def list_filtered(
    conn: sqlite3.Connection,
    user_id: int,
    filters: TransactionFilter,
    *,
    include_deleted: bool = False,
) -> list[Transaction]:
    cols = ", ".join(f"t.{c}" for c in _COLUMNS.split(", "))
    sql = (
        f"SELECT {cols} FROM transactions t "
        "JOIN categories c ON c.id = t.category_id AND c.user_id = t.user_id"
    )
    clauses, params = _txn_filter_clauses(filters, include_deleted)
    clauses.insert(0, "t.user_id = ?")
    params.insert(0, user_id)
    sql += " WHERE " + " AND ".join(clauses)
    direction = "DESC" if filters.order_desc else "ASC"
    sql += f" ORDER BY t.operation_date {direction}, t.id {direction}"
    if filters.limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([filters.limit, filters.offset])
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_txn(r) for r in rows]


def count_filtered(
    conn: sqlite3.Connection,
    user_id: int,
    filters: TransactionFilter | None = None,
    *,
    include_deleted: bool = False,
) -> int:
    """``COUNT(*)`` of the user's rows matching ``filters`` (limit/offset ignored)."""
    clauses, params = _txn_filter_clauses(filters or TransactionFilter(), include_deleted)
    clauses.insert(0, "t.user_id = ?")
    params.insert(0, user_id)
    sql = (
        "SELECT COUNT(*) FROM transactions t "
        "JOIN categories c ON c.id = t.category_id AND c.user_id = t.user_id "
        "WHERE " + " AND ".join(clauses)
    )
    return int(conn.execute(sql, params).fetchone()[0])


def sum_legs_by_direction(
    conn: sqlite3.Connection,
    user_id: int,
    account_id: int,
    *,
    up_to_date: date | None = None,
) -> list[tuple[str, bool, bool, int]]:
    """``SUM(amount)`` of live rows touching ``account_id``, grouped.

    Returns ``(category direction, is_source, is_dest, total)`` rows; the caller
    applies the sign rule (ADR-0008) via the canonical balance owner.
    """
    clauses = ["t.user_id = ?", "t.deleted_at IS NULL"]
    params: list[object] = [account_id, account_id, user_id]
    if up_to_date is not None:
        clauses.append("t.operation_date <= ?")
        params.append(up_to_date.isoformat())
    params.extend([account_id, account_id])
    sql = (
        "SELECT c.direction, t.account_id = ? AS is_source, "
        "t.dest_account_id = ? AS is_dest, SUM(t.amount) "
        "FROM transactions t "
        "JOIN categories c ON c.id = t.category_id AND c.user_id = t.user_id "
        "WHERE " + " AND ".join(clauses) + " AND (t.account_id = ? OR t.dest_account_id = ?) "
        "GROUP BY c.direction, is_source, is_dest"
    )
    return [
        (str(r[0]), bool(r[1]), bool(r[2]), int(r[3])) for r in conn.execute(sql, params).fetchall()
    ]


def sum_legs_by_account(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    up_to_date: date | None = None,
) -> list[tuple[str, int, int | None, int]]:
    """One-query ``SUM(amount)`` of the user's live rows, grouped per account pair.

    Returns ``(category direction, account_id, dest_account_id, total)`` rows for
    every account at once (T-Q234); the balance owner applies the sign rule.
    """
    clauses = ["t.user_id = ?", "t.deleted_at IS NULL"]
    params: list[object] = [user_id]
    if up_to_date is not None:
        clauses.append("t.operation_date <= ?")
        params.append(up_to_date.isoformat())
    sql = (
        "SELECT c.direction, t.account_id, t.dest_account_id, SUM(t.amount) "
        "FROM transactions t "
        "JOIN categories c ON c.id = t.category_id AND c.user_id = t.user_id "
        "WHERE " + " AND ".join(clauses) + " "
        "GROUP BY c.direction, t.account_id, t.dest_account_id"
    )
    return [
        (str(r[0]), int(r[1]), None if r[2] is None else int(r[2]), int(r[3]))
        for r in conn.execute(sql, params).fetchall()
    ]


def sum_legs_by_day(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    since: date,
    until: date,
) -> list[tuple[date, str, int, int | None, int]]:
    """Like :func:`sum_legs_by_account` for ``since <= operation_date <= until``, per day."""
    sql = (
        "SELECT t.operation_date, c.direction, t.account_id, t.dest_account_id, SUM(t.amount) "
        "FROM transactions t "
        "JOIN categories c ON c.id = t.category_id AND c.user_id = t.user_id "
        "WHERE t.user_id = ? AND t.deleted_at IS NULL "
        "AND t.operation_date >= ? AND t.operation_date <= ? "
        "GROUP BY t.operation_date, c.direction, t.account_id, t.dest_account_id"
    )
    rows = conn.execute(sql, (user_id, since.isoformat(), until.isoformat())).fetchall()
    return [
        (
            date.fromisoformat(str(r[0])),
            str(r[1]),
            int(r[2]),
            None if r[3] is None else int(r[3]),
            int(r[4]),
        )
        for r in rows
    ]


def _normalise_txn_patch(changes: dict[str, object]) -> dict[str, object]:
    norm: dict[str, object] = {}
    for key, value in changes.items():
        if key == "operation_date" and isinstance(value, date):
            norm[key] = value.isoformat()
        else:
            norm[key] = value
    return norm


def create(conn: sqlite3.Connection, user_id: int, data: NewTransaction) -> Transaction:
    require_owned(
        conn,
        user_id,
        account_ids=(data.account_id, data.dest_account_id),
        category_ids=(data.category_id,),
    )
    return insert_owned(
        conn,
        _TRANSACTIONS,
        user_id,
        {
            "operation_date": data.operation_date.isoformat(),
            "category_id": data.category_id,
            "account_id": data.account_id,
            "dest_account_id": data.dest_account_id,
            "amount": data.amount,
            "description": data.description,
            "promoted_from_planned_id": data.promoted_from_planned_id,
            "promoted_from_recurring_rule_id": data.promoted_from_recurring_rule_id,
            "promoted_from_recurring_date": (
                data.promoted_from_recurring_date.isoformat()
                if data.promoted_from_recurring_date is not None
                else None
            ),
        },
    )


def update(
    conn: sqlite3.Connection,
    user_id: int,
    txn_id: int,
    data: PatchTransaction,
) -> Transaction:
    return update_owned(
        conn,
        _TRANSACTIONS,
        user_id,
        txn_id,
        _normalise_txn_patch(data.as_dict()),
        account_ids=(data.account_id, data.dest_account_id),
        category_ids=(data.category_id,),
    )


def soft_delete(conn: sqlite3.Connection, user_id: int, txn_id: int) -> None:
    soft_delete_owned(conn, _TRANSACTIONS, user_id, txn_id)


def list_recently_deleted(
    conn: sqlite3.Connection, user_id: int, *, days: int = 90, limit: int = 500
) -> list[Transaction]:
    """T-R70 — soft-deleted transactions within the last `days` days (ADR-0019)."""
    return list_recently_deleted_owned(conn, _TRANSACTIONS, user_id, days=days, limit=limit)


def undelete(conn: sqlite3.Connection, user_id: int, txn_id: int) -> Transaction:
    return undelete_owned(conn, _TRANSACTIONS, user_id, txn_id)


__all__ = [
    "count_filtered",
    "create",
    "find_by_id",
    "list_filtered",
    "list_recently_deleted",
    "soft_delete",
    "sum_legs_by_account",
    "sum_legs_by_day",
    "sum_legs_by_direction",
    "undelete",
    "update",
]


def latest_operation_date_by_account(
    conn: sqlite3.Connection, user_id: int, category_id: int
) -> dict[int, date]:
    """Return ``{account_id: max(operation_date)}`` for live transactions in one category."""
    rows = conn.execute(
        """
        SELECT account_id, MAX(operation_date) AS d
        FROM transactions
        WHERE user_id = ? AND category_id = ? AND deleted_at IS NULL
        GROUP BY account_id
        """,
        (user_id, category_id),
    ).fetchall()
    return {row["account_id"]: date.fromisoformat(row["d"]) for row in rows if row["d"] is not None}
