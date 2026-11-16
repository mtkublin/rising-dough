"""Account repository — pure CRUD functions over the `accounts` table.

## User-scoping discipline (T-D16 / ADR-0061 §5)

Every function takes ``user_id`` as the first positional arg after ``conn``;
every SELECT / UPDATE / DELETE carries ``user_id = :user_id``; the
``tests/architecture/test_user_id_filter.py`` static test backstops the rule.
"""

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
    user_id: int,
    account_id: int,
    *,
    include_deleted: bool = False,
) -> Account | None:
    sql = f"SELECT {_COLUMNS} FROM accounts WHERE id = ? AND user_id = ?"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    row = conn.execute(sql, (account_id, user_id)).fetchone()
    return _row_to_account(row) if row is not None else None


def find_by_name(
    conn: sqlite3.Connection,
    user_id: int,
    name: str,
    *,
    include_deleted: bool = False,
) -> Account | None:
    sql = f"SELECT {_COLUMNS} FROM accounts WHERE name = ? AND user_id = ?"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    row = conn.execute(sql, (name, user_id)).fetchone()
    return _row_to_account(row) if row is not None else None


def list_all(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    include_deleted: bool = False,
) -> list[Account]:
    sql = f"SELECT {_COLUMNS} FROM accounts WHERE user_id = ?"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    sql += " ORDER BY name ASC"
    return [_row_to_account(r) for r in conn.execute(sql, (user_id,)).fetchall()]


def create(conn: sqlite3.Connection, user_id: int, data: NewAccount) -> Account:
    def _action(c: sqlite3.Connection) -> tuple[int, Account]:
        cursor = c.execute(
            "INSERT INTO accounts("
            "user_id, name, type, currency, opening_balance, "
            "is_liability, credit_limit_minor) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                data.name,
                data.type,
                data.currency,
                data.opening_balance,
                1 if data.is_liability else 0,
                data.credit_limit_minor,
            ),
        )
        new_id = int(cursor.lastrowid or 0)
        created = find_by_id(c, user_id, new_id)
        assert created is not None
        return new_id, created

    return mutate(conn, entity_type="account", operation="create", prev=None, action=_action)


def update(
    conn: sqlite3.Connection,
    user_id: int,
    account_id: int,
    data: PatchAccount,
) -> Account:
    prev = find_by_id(conn, user_id, account_id, include_deleted=True)
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
                f"UPDATE accounts SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
                (*changes.values(), account_id, user_id),
            )
        updated = find_by_id(c, user_id, account_id, include_deleted=True)
        assert updated is not None
        return account_id, updated

    return mutate(conn, entity_type="account", operation="update", prev=prev, action=_action)


def soft_delete(conn: sqlite3.Connection, user_id: int, account_id: int) -> None:
    prev = find_by_id(conn, user_id, account_id)
    if prev is None:
        return

    def _action(c: sqlite3.Connection) -> tuple[int, None]:
        c.execute(
            "UPDATE accounts "
            "SET deleted_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')), "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (account_id, user_id),
        )
        return account_id, None

    mutate(conn, entity_type="account", operation="delete", prev=prev, action=_action)


def undelete(conn: sqlite3.Connection, user_id: int, account_id: int) -> Account:
    prev = find_by_id(conn, user_id, account_id, include_deleted=True)
    if prev is None:
        raise LookupError(f"account {account_id} not found")

    def _action(c: sqlite3.Connection) -> tuple[int, Account]:
        c.execute(
            "UPDATE accounts SET deleted_at = NULL, "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ? AND user_id = ?",
            (account_id, user_id),
        )
        restored = find_by_id(c, user_id, account_id)
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
