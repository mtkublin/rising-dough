"""Budget tier repositories (defaults + recurring + one-off; ADR-0014).

## User-scoping discipline (T-D16 / ADR-0061 §5)

Every function takes ``user_id`` as the first positional arg after ``conn``;
every SELECT / UPDATE / DELETE carries ``user_id = :user_id``; the
``tests/architecture/test_user_id_filter.py`` static test backstops the rule.
"""

from __future__ import annotations

import sqlite3

from budget_planner.domain.budgets import (
    BudgetDefault,
    BudgetOneOffOverride,
    BudgetRecurringOverride,
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.repositories._shared import (
    OwnedTable,
    find_owned,
    insert_owned,
    list_owned,
    parse_dt,
    parse_dt_required,
    require_owned,
    soft_delete_found,
    update_owned,
)

_DEFAULT_COLS = "id, user_id, category_id, amount, created_at, updated_at, deleted_at"
_RECURRING_COLS = "id, user_id, category_id, month, amount, created_at, updated_at, deleted_at"
_ONE_OFF_COLS = "id, user_id, category_id, year, month, amount, created_at, updated_at, deleted_at"


def _row_to_default(row: sqlite3.Row) -> BudgetDefault:
    return BudgetDefault(
        id=row["id"],
        user_id=row["user_id"],
        category_id=row["category_id"],
        amount=row["amount"],
        created_at=parse_dt_required(row["created_at"]),
        updated_at=parse_dt_required(row["updated_at"]),
        deleted_at=parse_dt(row["deleted_at"]),
    )


def _row_to_recurring(row: sqlite3.Row) -> BudgetRecurringOverride:
    return BudgetRecurringOverride(
        id=row["id"],
        user_id=row["user_id"],
        category_id=row["category_id"],
        month=row["month"],
        amount=row["amount"],
        created_at=parse_dt_required(row["created_at"]),
        updated_at=parse_dt_required(row["updated_at"]),
        deleted_at=parse_dt(row["deleted_at"]),
    )


def _row_to_one_off(row: sqlite3.Row) -> BudgetOneOffOverride:
    return BudgetOneOffOverride(
        id=row["id"],
        user_id=row["user_id"],
        category_id=row["category_id"],
        year=row["year"],
        month=row["month"],
        amount=row["amount"],
        created_at=parse_dt_required(row["created_at"]),
        updated_at=parse_dt_required(row["updated_at"]),
        deleted_at=parse_dt(row["deleted_at"]),
    )


_DEFAULTS: OwnedTable[BudgetDefault] = OwnedTable(
    table="budget_defaults",
    entity_type="budget_default",
    columns=_DEFAULT_COLS,
    hydrate=_row_to_default,
    order_by="category_id ASC",
)
_RECURRING: OwnedTable[BudgetRecurringOverride] = OwnedTable(
    table="budget_recurring_overrides",
    entity_type="budget_recurring_override",
    columns=_RECURRING_COLS,
    hydrate=_row_to_recurring,
    order_by="category_id ASC, month ASC",
)
_ONE_OFF: OwnedTable[BudgetOneOffOverride] = OwnedTable(
    table="budget_one_off_overrides",
    entity_type="budget_one_off_override",
    columns=_ONE_OFF_COLS,
    hydrate=_row_to_one_off,
    order_by="year ASC, month ASC, category_id ASC",
)


# ---------------------------------------------------------------------------
# defaults
# ---------------------------------------------------------------------------
def get_default(
    conn: sqlite3.Connection,
    user_id: int,
    category_id: int,
    *,
    include_deleted: bool = False,
) -> BudgetDefault | None:
    return find_owned(
        conn, _DEFAULTS, user_id, {"category_id": category_id}, include_deleted=include_deleted
    )


def list_defaults(
    conn: sqlite3.Connection, user_id: int, *, include_deleted: bool = False
) -> list[BudgetDefault]:
    return list_owned(conn, _DEFAULTS, user_id, include_deleted=include_deleted)


def set_default(conn: sqlite3.Connection, user_id: int, data: NewBudgetDefault) -> BudgetDefault:
    require_owned(conn, user_id, category_ids=(data.category_id,))
    existing = get_default(conn, user_id, data.category_id)
    if existing is None:
        return insert_owned(
            conn,
            _DEFAULTS,
            user_id,
            {"category_id": data.category_id, "amount": data.amount},
        )
    return update_owned(conn, _DEFAULTS, user_id, existing.id, {"amount": data.amount})


def clear_default(conn: sqlite3.Connection, user_id: int, category_id: int) -> None:
    prev = get_default(conn, user_id, category_id)
    if prev is not None:
        soft_delete_found(conn, _DEFAULTS, user_id, prev.id, prev)


# ---------------------------------------------------------------------------
# recurring overrides
# ---------------------------------------------------------------------------
def get_recurring(
    conn: sqlite3.Connection,
    user_id: int,
    category_id: int,
    month: int,
    *,
    include_deleted: bool = False,
) -> BudgetRecurringOverride | None:
    return find_owned(
        conn,
        _RECURRING,
        user_id,
        {"category_id": category_id, "month": month},
        include_deleted=include_deleted,
    )


def list_recurring(
    conn: sqlite3.Connection, user_id: int, *, include_deleted: bool = False
) -> list[BudgetRecurringOverride]:
    return list_owned(conn, _RECURRING, user_id, include_deleted=include_deleted)


def set_recurring(
    conn: sqlite3.Connection, user_id: int, data: NewBudgetRecurringOverride
) -> BudgetRecurringOverride:
    require_owned(conn, user_id, category_ids=(data.category_id,))
    existing = get_recurring(conn, user_id, data.category_id, data.month)
    if existing is None:
        return insert_owned(
            conn,
            _RECURRING,
            user_id,
            {"category_id": data.category_id, "month": data.month, "amount": data.amount},
        )
    return update_owned(conn, _RECURRING, user_id, existing.id, {"amount": data.amount})


def clear_recurring(conn: sqlite3.Connection, user_id: int, category_id: int, month: int) -> None:
    prev = get_recurring(conn, user_id, category_id, month)
    if prev is not None:
        soft_delete_found(conn, _RECURRING, user_id, prev.id, prev)


# ---------------------------------------------------------------------------
# one-off overrides
# ---------------------------------------------------------------------------
def get_one_off(
    conn: sqlite3.Connection,
    user_id: int,
    category_id: int,
    year: int,
    month: int,
    *,
    include_deleted: bool = False,
) -> BudgetOneOffOverride | None:
    return find_owned(
        conn,
        _ONE_OFF,
        user_id,
        {"category_id": category_id, "year": year, "month": month},
        include_deleted=include_deleted,
    )


def list_one_off(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    year: int | None = None,
    include_deleted: bool = False,
) -> list[BudgetOneOffOverride]:
    return list_owned(
        conn,
        _ONE_OFF,
        user_id,
        where=None if year is None else {"year": year},
        include_deleted=include_deleted,
    )


def set_one_off(
    conn: sqlite3.Connection, user_id: int, data: NewBudgetOneOffOverride
) -> BudgetOneOffOverride:
    require_owned(conn, user_id, category_ids=(data.category_id,))
    existing = get_one_off(conn, user_id, data.category_id, data.year, data.month)
    if existing is None:
        return insert_owned(
            conn,
            _ONE_OFF,
            user_id,
            {
                "category_id": data.category_id,
                "year": data.year,
                "month": data.month,
                "amount": data.amount,
            },
        )
    return update_owned(conn, _ONE_OFF, user_id, existing.id, {"amount": data.amount})


def clear_one_off(
    conn: sqlite3.Connection,
    user_id: int,
    category_id: int,
    year: int,
    month: int,
) -> None:
    prev = get_one_off(conn, user_id, category_id, year, month)
    if prev is not None:
        soft_delete_found(conn, _ONE_OFF, user_id, prev.id, prev)


__all__ = [
    "clear_default",
    "clear_one_off",
    "clear_recurring",
    "get_default",
    "get_one_off",
    "get_recurring",
    "list_defaults",
    "list_one_off",
    "list_recurring",
    "set_default",
    "set_one_off",
    "set_recurring",
]
