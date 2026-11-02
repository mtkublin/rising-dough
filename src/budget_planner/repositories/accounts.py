"""Account repository — pure CRUD functions over the `accounts` table."""

from __future__ import annotations

import sqlite3

from budget_planner.domain.accounts import Account, NewAccount, PatchAccount
from budget_planner.repositories._shared import mutate, parse_dt, parse_dt_required

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


def find_by_id(
    conn: sqlite3.Connection,
    account_id: int,
    *,
    include_deleted: bool = False,
) -> Account | None:
    sql = f"SELECT {_COLUMNS} FROM accounts WHERE id = ?"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    row = conn.execute(sql, (account_id,)).fetchone()
    return _row_to_account(row) if row is not None else None


def find_by_name(
    conn: sqlite3.Connection,
    name: str,
    *,
    include_deleted: bool = False,
) -> Account | None:
    sql = f"SELECT {_COLUMNS} FROM accounts WHERE name = ?"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    row = conn.execute(sql, (name,)).fetchone()
    return _row_to_account(row) if row is not None else None


def list_all(
    conn: sqlite3.Connection,
    *,
    include_deleted: bool = False,
) -> list[Account]:
    sql = f"SELECT {_COLUMNS} FROM accounts"
    if not include_deleted:
        sql += " WHERE deleted_at IS NULL"
    sql += " ORDER BY name ASC"
    return [_row_to_account(r) for r in conn.execute(sql).fetchall()]


def create(conn: sqlite3.Connection, data: NewAccount) -> Account:
    def _action(c: sqlite3.Connection) -> tuple[int, Account]:
        cursor = c.execute(
            "INSERT INTO accounts("
            "user_id, name, type, currency, opening_balance, "
            "is_liability, credit_limit_minor) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                data.user_id,
                data.name,
                data.type,
                data.currency,
                data.opening_balance,
                1 if data.is_liability else 0,
                data.credit_limit_minor,
            ),
        )
        new_id = int(cursor.lastrowid or 0)
        created = find_by_id(c, new_id)
        assert created is not None
        return new_id, created

    return mutate(conn, entity_type="account", operation="create", prev=None, action=_action)


def update(
    conn: sqlite3.Connection,
    account_id: int,
    data: PatchAccount,
) -> Account:
    prev = find_by_id(conn, account_id, include_deleted=True)
    if prev is None:
        raise LookupError(f"account {account_id} not found")

    changes = data.as_dict()
    if "is_liability" in changes:
        changes["is_liability"] = 1 if changes["is_liability"] else 0

    def _action(c: sqlite3.Connection) -> tuple[int, Account]:
        if changes:
            sets = [f"{field} = ?" for field in changes]
            sets.append("updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))")
            c.execute(
                f"UPDATE accounts SET {', '.join(sets)} WHERE id = ?",
                (*changes.values(), account_id),
            )
        updated = find_by_id(c, account_id, include_deleted=True)
        assert updated is not None
        return account_id, updated

    return mutate(conn, entity_type="account", operation="update", prev=prev, action=_action)


def soft_delete(conn: sqlite3.Connection, account_id: int) -> None:
    prev = find_by_id(conn, account_id)
    if prev is None:
        return

    def _action(c: sqlite3.Connection) -> tuple[int, None]:
        c.execute(
            "UPDATE accounts "
            "SET deleted_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')), "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ? AND deleted_at IS NULL",
            (account_id,),
        )
        return account_id, None

    mutate(conn, entity_type="account", operation="delete", prev=prev, action=_action)


def undelete(conn: sqlite3.Connection, account_id: int) -> Account:
    prev = find_by_id(conn, account_id, include_deleted=True)
    if prev is None:
        raise LookupError(f"account {account_id} not found")

    def _action(c: sqlite3.Connection) -> tuple[int, Account]:
        c.execute(
            "UPDATE accounts SET deleted_at = NULL, "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ?",
            (account_id,),
        )
        restored = find_by_id(c, account_id)
        assert restored is not None
        return account_id, restored

    return mutate(conn, entity_type="account", operation="undelete", prev=prev, action=_action)


__all__ = [
    "create",
    "find_by_id",
    "find_by_name",
    "list_all",
    "soft_delete",
    "undelete",
    "update",
]
