"""Planned transaction repository."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from budget_planner.domain.planned import (
    NewPlannedTransaction,
    PatchPlannedTransaction,
    PlannedFilter,
    PlannedTransaction,
)
from budget_planner.repositories._shared import mutate, parse_dt, parse_dt_required

_COLUMNS = (
    "id, user_id, operation_date, category_id, account_id, dest_account_id, "
    "amount, description, recurring_rule_id, occurrence_date, promoted_to_txn_id, "
    "created_at, updated_at, deleted_at"
)


def _row_to_planned(row: sqlite3.Row) -> PlannedTransaction:
    return PlannedTransaction(
        id=row["id"],
        user_id=row["user_id"],
        operation_date=date.fromisoformat(row["operation_date"]),
        category_id=row["category_id"],
        account_id=row["account_id"],
        dest_account_id=row["dest_account_id"],
        amount=row["amount"],
        description=row["description"],
        recurring_rule_id=row["recurring_rule_id"],
        occurrence_date=(
            date.fromisoformat(row["occurrence_date"])
            if row["occurrence_date"] is not None
            else None
        ),
        promoted_to_txn_id=row["promoted_to_txn_id"],
        created_at=parse_dt_required(row["created_at"]),
        updated_at=parse_dt_required(row["updated_at"]),
        deleted_at=parse_dt(row["deleted_at"]),
    )


def find_by_id(
    conn: sqlite3.Connection,
    planned_id: int,
    *,
    include_deleted: bool = False,
) -> PlannedTransaction | None:
    sql = f"SELECT {_COLUMNS} FROM planned_transactions WHERE id = ?"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    row = conn.execute(sql, (planned_id,)).fetchone()
    return _row_to_planned(row) if row is not None else None


def _append_filter_clauses(
    filters: PlannedFilter,
    include_deleted: bool,
) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if filters.date_from is not None:
        clauses.append("p.operation_date >= ?")
        params.append(filters.date_from.isoformat())
    if filters.date_to is not None:
        clauses.append("p.operation_date <= ?")
        params.append(filters.date_to.isoformat())
    if filters.account_ids:
        placeholders = ",".join("?" for _ in filters.account_ids)
        clauses.append(f"p.account_id IN ({placeholders})")
        params.extend(filters.account_ids)
    if filters.category_ids:
        placeholders = ",".join("?" for _ in filters.category_ids)
        clauses.append(f"p.category_id IN ({placeholders})")
        params.extend(filters.category_ids)
    if filters.directions:
        placeholders = ",".join("?" for _ in filters.directions)
        clauses.append(f"c.direction IN ({placeholders})")
        params.extend(d.value for d in filters.directions)
    if filters.recurring_rule_id is not None:
        clauses.append("p.recurring_rule_id = ?")
        params.append(filters.recurring_rule_id)
    if filters.promoted is not None:
        clauses.append(
            "p.promoted_to_txn_id IS NOT NULL"
            if filters.promoted
            else "p.promoted_to_txn_id IS NULL"
        )
    if not include_deleted:
        clauses.append("p.deleted_at IS NULL")
    return clauses, params


def list_filtered(
    conn: sqlite3.Connection,
    filters: PlannedFilter,
    *,
    include_deleted: bool = False,
) -> list[PlannedTransaction]:
    cols = ", ".join(f"p.{c}" for c in _COLUMNS.split(", "))
    sql = f"SELECT {cols} FROM planned_transactions p JOIN categories c ON c.id = p.category_id"
    clauses, params = _append_filter_clauses(filters, include_deleted)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY p.operation_date ASC, p.id ASC"
    if filters.limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([filters.limit, filters.offset])
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_planned(r) for r in rows]


def create(conn: sqlite3.Connection, data: NewPlannedTransaction) -> PlannedTransaction:
    def _action(c: sqlite3.Connection) -> tuple[int, PlannedTransaction]:
        cursor = c.execute(
            "INSERT INTO planned_transactions("
            "user_id, operation_date, category_id, account_id, dest_account_id, "
            "amount, description, recurring_rule_id, occurrence_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data.user_id,
                data.operation_date.isoformat(),
                data.category_id,
                data.account_id,
                data.dest_account_id,
                data.amount,
                data.description,
                data.recurring_rule_id,
                data.occurrence_date.isoformat() if data.occurrence_date else None,
            ),
        )
        new_id = int(cursor.lastrowid or 0)
        created = find_by_id(c, new_id)
        assert created is not None
        return new_id, created

    return mutate(
        conn,
        entity_type="planned_transaction",
        operation="create",
        prev=None,
        action=_action,
    )


def _normalise_patch(changes: dict[str, Any]) -> dict[str, Any]:
    norm: dict[str, Any] = {}
    for key, value in changes.items():
        if key in {"operation_date", "occurrence_date"} and value is not None:
            norm[key] = value.isoformat()
        else:
            norm[key] = value
    return norm


def update(
    conn: sqlite3.Connection,
    planned_id: int,
    data: PatchPlannedTransaction,
) -> PlannedTransaction:
    prev = find_by_id(conn, planned_id, include_deleted=True)
    if prev is None:
        raise LookupError(f"planned_transaction {planned_id} not found")
    changes = _normalise_patch(data.as_dict())

    def _action(c: sqlite3.Connection) -> tuple[int, PlannedTransaction]:
        if changes:
            sets = [f"{field} = ?" for field in changes]
            sets.append("updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))")
            c.execute(
                f"UPDATE planned_transactions SET {', '.join(sets)} WHERE id = ?",
                (*changes.values(), planned_id),
            )
        updated = find_by_id(c, planned_id, include_deleted=True)
        assert updated is not None
        return planned_id, updated

    return mutate(
        conn,
        entity_type="planned_transaction",
        operation="update",
        prev=prev,
        action=_action,
    )


def soft_delete(conn: sqlite3.Connection, planned_id: int) -> None:
    prev = find_by_id(conn, planned_id)
    if prev is None:
        return

    def _action(c: sqlite3.Connection) -> tuple[int, None]:
        c.execute(
            "UPDATE planned_transactions "
            "SET deleted_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')), "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ? AND deleted_at IS NULL",
            (planned_id,),
        )
        return planned_id, None

    mutate(
        conn,
        entity_type="planned_transaction",
        operation="delete",
        prev=prev,
        action=_action,
    )


def list_recently_deleted(
    conn: sqlite3.Connection, *, days: int = 90, limit: int = 500
) -> list[PlannedTransaction]:
    """T-R70 — soft-deleted planned items within the last `days` days."""
    sql = (
        f"SELECT {_COLUMNS} FROM planned_transactions "
        "WHERE deleted_at IS NOT NULL "
        "AND deleted_at > datetime('now', ?) "
        "ORDER BY deleted_at DESC "
        "LIMIT ?"
    )
    rows = conn.execute(sql, (f"-{days} days", limit)).fetchall()
    return [_row_to_planned(r) for r in rows]


def undelete(conn: sqlite3.Connection, planned_id: int) -> PlannedTransaction:
    prev = find_by_id(conn, planned_id, include_deleted=True)
    if prev is None:
        raise LookupError(f"planned_transaction {planned_id} not found")

    def _action(c: sqlite3.Connection) -> tuple[int, PlannedTransaction]:
        c.execute(
            "UPDATE planned_transactions SET deleted_at = NULL, "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ?",
            (planned_id,),
        )
        restored = find_by_id(c, planned_id)
        assert restored is not None
        return planned_id, restored

    return mutate(
        conn,
        entity_type="planned_transaction",
        operation="undelete",
        prev=prev,
        action=_action,
    )


def stamp_promotion(conn: sqlite3.Connection, planned_id: int, txn_id: int) -> PlannedTransaction:
    prev = find_by_id(conn, planned_id, include_deleted=True)
    if prev is None:
        raise LookupError(f"planned_transaction {planned_id} not found")

    def _action(c: sqlite3.Connection) -> tuple[int, PlannedTransaction]:
        c.execute(
            "UPDATE planned_transactions SET promoted_to_txn_id = ?, "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ?",
            (txn_id, planned_id),
        )
        updated = find_by_id(c, planned_id, include_deleted=True)
        assert updated is not None
        return planned_id, updated

    return mutate(
        conn,
        entity_type="planned_transaction",
        operation="update",
        prev=prev,
        action=_action,
    )


__all__ = [
    "create",
    "find_by_id",
    "list_filtered",
    "list_recently_deleted",
    "soft_delete",
    "stamp_promotion",
    "undelete",
    "update",
]
