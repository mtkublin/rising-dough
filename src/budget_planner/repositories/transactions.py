"""Transaction repository — pure CRUD + rich filter support."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from budget_planner.domain.transactions import (
    NewTransaction,
    PatchTransaction,
    Transaction,
    TransactionFilter,
)
from budget_planner.repositories._shared import mutate, parse_dt, parse_dt_required

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


def find_by_id(
    conn: sqlite3.Connection,
    txn_id: int,
    *,
    include_deleted: bool = False,
) -> Transaction | None:
    sql = f"SELECT {_COLUMNS} FROM transactions WHERE id = ?"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    row = conn.execute(sql, (txn_id,)).fetchone()
    return _row_to_txn(row) if row is not None else None


def _append_filter_clauses(
    filters: TransactionFilter,
    include_deleted: bool,
) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if filters.date_from is not None:
        clauses.append("t.operation_date >= ?")
        params.append(filters.date_from.isoformat())
    if filters.date_to is not None:
        clauses.append("t.operation_date <= ?")
        params.append(filters.date_to.isoformat())
    if filters.up_to_date is not None:
        clauses.append("t.operation_date <= ?")
        params.append(filters.up_to_date.isoformat())
    if filters.account_ids:
        placeholders = ",".join("?" for _ in filters.account_ids)
        clauses.append(f"t.account_id IN ({placeholders})")
        params.extend(filters.account_ids)
    if filters.category_ids:
        placeholders = ",".join("?" for _ in filters.category_ids)
        clauses.append(f"t.category_id IN ({placeholders})")
        params.extend(filters.category_ids)
    if filters.directions:
        placeholders = ",".join("?" for _ in filters.directions)
        clauses.append(f"c.direction IN ({placeholders})")
        params.extend(d.value for d in filters.directions)
    if filters.amount_min is not None:
        clauses.append("t.amount >= ?")
        params.append(filters.amount_min)
    if filters.amount_max is not None:
        clauses.append("t.amount <= ?")
        params.append(filters.amount_max)
    if filters.description_contains is not None:
        clauses.append("t.description LIKE ?")
        params.append(f"%{filters.description_contains}%")
    if filters.account_or_dest is not None:
        clauses.append("(t.account_id = ? OR t.dest_account_id = ?)")
        params.extend([filters.account_or_dest, filters.account_or_dest])
    if not include_deleted:
        clauses.append("t.deleted_at IS NULL")
    return clauses, params


def list_filtered(
    conn: sqlite3.Connection,
    filters: TransactionFilter,
    *,
    include_deleted: bool = False,
) -> list[Transaction]:
    cols = ", ".join(f"t.{c}" for c in _COLUMNS.split(", "))
    sql = f"SELECT {cols} FROM transactions t JOIN categories c ON c.id = t.category_id"
    clauses, params = _append_filter_clauses(filters, include_deleted)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    direction = "DESC" if filters.order_desc else "ASC"
    sql += f" ORDER BY t.operation_date {direction}, t.id {direction}"
    if filters.limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([filters.limit, filters.offset])
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_txn(r) for r in rows]


def _normalise_patch(changes: dict[str, Any]) -> dict[str, Any]:
    norm: dict[str, Any] = {}
    for key, value in changes.items():
        if key == "operation_date":
            norm[key] = value.isoformat()
        else:
            norm[key] = value
    return norm


def create(conn: sqlite3.Connection, data: NewTransaction) -> Transaction:
    def _action(c: sqlite3.Connection) -> tuple[int, Transaction]:
        cursor = c.execute(
            "INSERT INTO transactions("
            "user_id, operation_date, category_id, account_id, dest_account_id, "
            "amount, description, promoted_from_planned_id, "
            "promoted_from_recurring_rule_id, promoted_from_recurring_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data.user_id,
                data.operation_date.isoformat(),
                data.category_id,
                data.account_id,
                data.dest_account_id,
                data.amount,
                data.description,
                data.promoted_from_planned_id,
                data.promoted_from_recurring_rule_id,
                (
                    data.promoted_from_recurring_date.isoformat()
                    if data.promoted_from_recurring_date is not None
                    else None
                ),
            ),
        )
        new_id = int(cursor.lastrowid or 0)
        created = find_by_id(c, new_id)
        assert created is not None
        return new_id, created

    return mutate(
        conn,
        entity_type="transaction",
        operation="create",
        prev=None,
        action=_action,
    )


def update(
    conn: sqlite3.Connection,
    txn_id: int,
    data: PatchTransaction,
) -> Transaction:
    prev = find_by_id(conn, txn_id, include_deleted=True)
    if prev is None:
        raise LookupError(f"transaction {txn_id} not found")
    changes = _normalise_patch(data.as_dict())

    def _action(c: sqlite3.Connection) -> tuple[int, Transaction]:
        if changes:
            sets = [f"{field} = ?" for field in changes]
            sets.append("updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))")
            c.execute(
                f"UPDATE transactions SET {', '.join(sets)} WHERE id = ?",
                (*changes.values(), txn_id),
            )
        updated = find_by_id(c, txn_id, include_deleted=True)
        assert updated is not None
        return txn_id, updated

    return mutate(
        conn,
        entity_type="transaction",
        operation="update",
        prev=prev,
        action=_action,
    )


def soft_delete(conn: sqlite3.Connection, txn_id: int) -> None:
    prev = find_by_id(conn, txn_id)
    if prev is None:
        return

    def _action(c: sqlite3.Connection) -> tuple[int, None]:
        c.execute(
            "UPDATE transactions SET deleted_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')), "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ? AND deleted_at IS NULL",
            (txn_id,),
        )
        return txn_id, None

    mutate(
        conn,
        entity_type="transaction",
        operation="delete",
        prev=prev,
        action=_action,
    )


def list_recently_deleted(
    conn: sqlite3.Connection, *, days: int = 90, limit: int = 500
) -> list[Transaction]:
    """T-R70 — soft-deleted transactions within the last `days` days (ADR-0019)."""
    sql = (
        f"SELECT {_COLUMNS} FROM transactions "
        "WHERE deleted_at IS NOT NULL "
        "AND deleted_at > datetime('now', ?) "
        "ORDER BY deleted_at DESC "
        "LIMIT ?"
    )
    rows = conn.execute(sql, (f"-{days} days", limit)).fetchall()
    return [_row_to_txn(r) for r in rows]


def undelete(conn: sqlite3.Connection, txn_id: int) -> Transaction:
    prev = find_by_id(conn, txn_id, include_deleted=True)
    if prev is None:
        raise LookupError(f"transaction {txn_id} not found")

    def _action(c: sqlite3.Connection) -> tuple[int, Transaction]:
        c.execute(
            "UPDATE transactions SET deleted_at = NULL, "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ?",
            (txn_id,),
        )
        restored = find_by_id(c, txn_id)
        assert restored is not None
        return txn_id, restored

    return mutate(
        conn,
        entity_type="transaction",
        operation="undelete",
        prev=prev,
        action=_action,
    )


__all__ = [
    "create",
    "find_by_id",
    "list_filtered",
    "list_recently_deleted",
    "soft_delete",
    "undelete",
    "update",
]
