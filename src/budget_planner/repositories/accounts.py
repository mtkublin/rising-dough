"""Account repository — pure CRUD functions over the `accounts` table.

## User-scoping discipline (T-D16 / ADR-0061 §5)

Every function takes ``user_id`` as the first positional arg after ``conn``;
every SELECT / UPDATE / DELETE carries ``user_id = :user_id``; the
``tests/architecture/test_user_id_filter.py`` static test backstops the rule.
"""

from __future__ import annotations

import sqlite3

from budget_planner.domain.accounts import Account, NewAccount, PatchAccount
from budget_planner.repositories._shared import (
    OwnedTable,
    find_owned,
    insert_owned,
    list_owned,
    parse_dt,
    parse_dt_required,
    soft_delete_owned,
    undelete_owned,
    update_owned,
)

_COLUMNS = (
    "id, user_id, name, type, currency, opening_balance, "
    "is_liability, credit_limit_minor, created_at, updated_at, deleted_at"
)


def _row_to_account(row: sqlite3.Row) -> Account:
    return Account(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        type=row["type"],
        currency=row["currency"],
        opening_balance=row["opening_balance"],
        is_liability=bool(row["is_liability"]),
        credit_limit_minor=row["credit_limit_minor"],
        created_at=parse_dt_required(row["created_at"]),
        updated_at=parse_dt_required(row["updated_at"]),
        deleted_at=parse_dt(row["deleted_at"]),
    )


_ACCOUNTS: OwnedTable[Account] = OwnedTable(
    table="accounts",
    entity_type="account",
    columns=_COLUMNS,
    hydrate=_row_to_account,
    order_by="name ASC",
)


def find_by_id(
    conn: sqlite3.Connection,
    user_id: int,
    account_id: int,
    *,
    include_deleted: bool = False,
) -> Account | None:
    return find_owned(conn, _ACCOUNTS, user_id, {"id": account_id}, include_deleted=include_deleted)


def find_by_name(
    conn: sqlite3.Connection,
    user_id: int,
    name: str,
    *,
    include_deleted: bool = False,
) -> Account | None:
    return find_owned(conn, _ACCOUNTS, user_id, {"name": name}, include_deleted=include_deleted)


def list_all(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    include_deleted: bool = False,
) -> list[Account]:
    return list_owned(conn, _ACCOUNTS, user_id, include_deleted=include_deleted)


def create(conn: sqlite3.Connection, user_id: int, data: NewAccount) -> Account:
    return insert_owned(
        conn,
        _ACCOUNTS,
        user_id,
        {
            "name": data.name,
            "type": data.type,
            "currency": data.currency,
            "opening_balance": data.opening_balance,
            "is_liability": 1 if data.is_liability else 0,
            "credit_limit_minor": data.credit_limit_minor,
        },
    )


def update(
    conn: sqlite3.Connection,
    user_id: int,
    account_id: int,
    data: PatchAccount,
) -> Account:
    changes = data.as_dict()
    if "is_liability" in changes:
        changes["is_liability"] = 1 if changes["is_liability"] else 0
    return update_owned(conn, _ACCOUNTS, user_id, account_id, changes)


def soft_delete(conn: sqlite3.Connection, user_id: int, account_id: int) -> None:
    soft_delete_owned(conn, _ACCOUNTS, user_id, account_id)


def undelete(conn: sqlite3.Connection, user_id: int, account_id: int) -> Account:
    return undelete_owned(conn, _ACCOUNTS, user_id, account_id)


__all__ = [
    "create",
    "find_by_id",
    "find_by_name",
    "list_all",
    "soft_delete",
    "undelete",
    "update",
]
