"""Planned transaction repository.

## User-scoping discipline (T-D16 / ADR-0061 §5)

Every function takes ``user_id`` as the first positional arg after ``conn``;
every SELECT / UPDATE / DELETE carries ``user_id = :user_id``; the
``tests/architecture/test_user_id_filter.py`` static test backstops the rule.
"""

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
from budget_planner.repositories._shared import (
    OwnedTable,
    find_owned,
    insert_owned,
    list_recently_deleted_owned,
    mutate,
    parse_dt,
    parse_dt_required,
    require_owned,
    soft_delete_owned,
    undelete_owned,
    update_owned,
)

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


_PLANNED: OwnedTable[PlannedTransaction] = OwnedTable(
    table="planned_transactions",
    entity_type="planned_transaction",
    columns=_COLUMNS,
    hydrate=_row_to_planned,
    order_by="operation_date ASC, id ASC",
)


def find_by_id(
    conn: sqlite3.Connection,
    user_id: int,
    planned_id: int,
    *,
    include_deleted: bool = False,
) -> PlannedTransaction | None:
    return find_owned(conn, _PLANNED, user_id, {"id": planned_id}, include_deleted=include_deleted)


def _planned_filter_clauses(
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
    user_id: int,
    filters: PlannedFilter,
    *,
    include_deleted: bool = False,
) -> list[PlannedTransaction]:
    cols = ", ".join(f"p.{c}" for c in _COLUMNS.split(", "))
    sql = (
        f"SELECT {cols} FROM planned_transactions p "
        "JOIN categories c ON c.id = p.category_id AND c.user_id = p.user_id"
    )
    clauses, params = _planned_filter_clauses(filters, include_deleted)
    clauses.insert(0, "p.user_id = ?")
    params.insert(0, user_id)
    sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY p.operation_date ASC, p.id ASC"
    if filters.limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([filters.limit, filters.offset])
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_planned(r) for r in rows]


def create(
    conn: sqlite3.Connection, user_id: int, data: NewPlannedTransaction
) -> PlannedTransaction:
    require_owned(
        conn,
        user_id,
        account_ids=(data.account_id, data.dest_account_id),
        category_ids=(data.category_id,),
    )
    return insert_owned(
        conn,
        _PLANNED,
        user_id,
        {
            "operation_date": data.operation_date.isoformat(),
            "category_id": data.category_id,
            "account_id": data.account_id,
            "dest_account_id": data.dest_account_id,
            "amount": data.amount,
            "description": data.description,
            "recurring_rule_id": data.recurring_rule_id,
            "occurrence_date": data.occurrence_date.isoformat() if data.occurrence_date else None,
        },
    )


def _normalise_planned_patch(changes: dict[str, Any]) -> dict[str, Any]:
    norm: dict[str, Any] = {}
    for key, value in changes.items():
        if key in {"operation_date", "occurrence_date"} and value is not None:
            norm[key] = value.isoformat()
        else:
            norm[key] = value
    return norm


def update(
    conn: sqlite3.Connection,
    user_id: int,
    planned_id: int,
    data: PatchPlannedTransaction,
) -> PlannedTransaction:
    return update_owned(
        conn,
        _PLANNED,
        user_id,
        planned_id,
        _normalise_planned_patch(data.as_dict()),
        account_ids=(data.account_id, data.dest_account_id),
        category_ids=(data.category_id,),
    )


def soft_delete(conn: sqlite3.Connection, user_id: int, planned_id: int) -> None:
    soft_delete_owned(conn, _PLANNED, user_id, planned_id)


def list_recently_deleted(
    conn: sqlite3.Connection, user_id: int, *, days: int = 90, limit: int = 500
) -> list[PlannedTransaction]:
    """T-R70 — soft-deleted planned items within the last `days` days."""
    return list_recently_deleted_owned(conn, _PLANNED, user_id, days=days, limit=limit)


def undelete(conn: sqlite3.Connection, user_id: int, planned_id: int) -> PlannedTransaction:
    return undelete_owned(conn, _PLANNED, user_id, planned_id)


def stamp_promotion(
    conn: sqlite3.Connection, user_id: int, planned_id: int, txn_id: int
) -> PlannedTransaction:
    return update_owned(conn, _PLANNED, user_id, planned_id, {"promoted_to_txn_id": txn_id})


def clear_promotion(
    conn: sqlite3.Connection,
    user_id: int,
    planned_id: int,
    *,
    txn_ids: frozenset[int],
) -> bool:
    """Un-stamp a promoted planned row, audited, compare-and-set (T-Q228, Q-024).

    Clears ``promoted_to_txn_id`` only while it still equals one of ``txn_ids``
    (the transactions of the batch being undone). Returns ``False`` and writes
    nothing when the row is missing, not stamped, or stamped with another id.
    """
    prev = find_by_id(conn, user_id, planned_id, include_deleted=True)
    if prev is None or prev.promoted_to_txn_id not in txn_ids:
        return False

    def _clear_action(c: sqlite3.Connection) -> tuple[int, PlannedTransaction]:
        c.execute(
            "UPDATE planned_transactions SET promoted_to_txn_id = NULL, "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ? AND user_id = ? AND promoted_to_txn_id = ?",
            (planned_id, user_id, prev.promoted_to_txn_id),
        )
        updated = find_by_id(c, user_id, planned_id, include_deleted=True)
        if updated is None:
            raise LookupError(f"planned_transaction {planned_id} not found")
        return planned_id, updated

    mutate(
        conn,
        entity_type="planned_transaction",
        operation="update",
        prev=prev,
        action=_clear_action,
        user_id=user_id,
    )
    return True


__all__ = [
    "clear_promotion",
    "create",
    "find_by_id",
    "list_filtered",
    "list_recently_deleted",
    "soft_delete",
    "stamp_promotion",
    "undelete",
    "update",
]
