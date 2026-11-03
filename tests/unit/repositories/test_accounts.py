from __future__ import annotations

import json
import sqlite3

import pytest

from budget_planner.domain.accounts import NewAccount, PatchAccount
from budget_planner.repositories import accounts, audit

USER_ID = 1


def test_create_round_trip(conn: sqlite3.Connection) -> None:
    acc = accounts.create(conn, USER_ID, NewAccount(name="ING", currency="PLN"))
    fetched = accounts.find_by_id(conn, USER_ID, acc.id)
    assert fetched == acc
    assert accounts.find_by_name(conn, USER_ID, "ING") == acc
    entries = audit.list_entries(conn, "account", acc.id)
    assert len(entries) == 1
    assert entries[0].operation.value == "create"


def test_update_patch(conn: sqlite3.Connection) -> None:
    acc = accounts.create(conn, USER_ID, NewAccount(name="X", currency="PLN"))
    updated = accounts.update(conn, USER_ID, acc.id, PatchAccount(name="Y", type="bank"))
    assert updated.name == "Y"
    assert updated.type == "bank"
    assert updated.updated_at >= acc.updated_at
    entries = audit.list_entries(conn, "account", acc.id)
    assert [e.operation.value for e in entries] == ["create", "update"]


def test_update_noop_still_audits(conn: sqlite3.Connection) -> None:
    acc = accounts.create(conn, USER_ID, NewAccount(name="N", currency="PLN"))
    accounts.update(conn, USER_ID, acc.id, PatchAccount())
    entries = audit.list_entries(conn, "account", acc.id)
    assert [e.operation.value for e in entries] == ["create", "update"]


def test_update_missing_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(LookupError):
        accounts.update(conn, USER_ID, 999, PatchAccount(name="X"))


def test_soft_delete_round_trip(conn: sqlite3.Connection) -> None:
    acc = accounts.create(conn, USER_ID, NewAccount(name="D", currency="PLN"))
    accounts.soft_delete(conn, USER_ID, acc.id)
    assert accounts.find_by_id(conn, USER_ID, acc.id) is None
    assert accounts.find_by_id(conn, USER_ID, acc.id, include_deleted=True) is not None
    assert accounts.find_by_name(conn, USER_ID, "D") is None
    assert accounts.find_by_name(conn, USER_ID, "D", include_deleted=True) is not None
    assert accounts.list_all(conn, USER_ID) == []
    assert accounts.list_all(conn, USER_ID, include_deleted=True) != []

    restored = accounts.undelete(conn, USER_ID, acc.id)
    assert restored.deleted_at is None
    assert accounts.find_by_id(conn, USER_ID, acc.id) == restored

    entries = audit.list_entries(conn, "account", acc.id)
    assert [e.operation.value for e in entries] == [
        "create",
        "delete",
        "undelete",
    ]


def test_soft_delete_on_missing_is_noop(conn: sqlite3.Connection) -> None:
    accounts.soft_delete(conn, USER_ID, 999)
    # Should not have audited anything.
    assert audit.list_entries(conn, "account", 999) == []


def test_undelete_missing_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(LookupError):
        accounts.undelete(conn, USER_ID, 999)


def test_soft_delete_frees_name(conn: sqlite3.Connection) -> None:
    first = accounts.create(conn, USER_ID, NewAccount(name="ING", currency="PLN"))
    accounts.soft_delete(conn, USER_ID, first.id)
    second = accounts.create(conn, USER_ID, NewAccount(name="ING", currency="PLN"))
    assert second.id != first.id


def test_create_asset_account_defaults(conn: sqlite3.Connection) -> None:
    acc = accounts.create(conn, USER_ID, NewAccount(name="A", currency="PLN"))
    assert acc.is_liability is False
    assert acc.credit_limit_minor is None


def test_create_liability_account_with_limit(conn: sqlite3.Connection) -> None:
    acc = accounts.create(
        conn,
        USER_ID,
        NewAccount(
            name="Visa",
            currency="PLN",
            type="credit_card",
            is_liability=True,
            credit_limit_minor=1_000_000,
        ),
    )
    assert acc.is_liability is True
    assert acc.credit_limit_minor == 1_000_000
    fetched = accounts.find_by_id(conn, USER_ID, acc.id)
    assert fetched is not None
    assert fetched.is_liability is True
    assert fetched.credit_limit_minor == 1_000_000


def test_patch_set_credit_limit(conn: sqlite3.Connection) -> None:
    acc = accounts.create(
        conn,
        USER_ID,
        NewAccount(name="V", currency="PLN", is_liability=True, credit_limit_minor=500_000),
    )
    updated = accounts.update(conn, USER_ID, acc.id, PatchAccount(credit_limit_minor=2_000_000))
    assert updated.credit_limit_minor == 2_000_000
    entries = audit.list_entries(conn, "account", acc.id)
    new_json = json.loads(entries[-1].new_json or "{}")
    assert new_json["credit_limit_minor"] == 2_000_000


def test_patch_clear_credit_limit(conn: sqlite3.Connection) -> None:
    acc = accounts.create(
        conn,
        USER_ID,
        NewAccount(name="V", currency="PLN", is_liability=True, credit_limit_minor=500_000),
    )
    updated = accounts.update(
        conn,
        USER_ID,
        acc.id,
        PatchAccount(is_liability=False, clear_credit_limit=True),
    )
    assert updated.is_liability is False
    assert updated.credit_limit_minor is None
    entries = audit.list_entries(conn, "account", acc.id)
    new_json = json.loads(entries[-1].new_json or "{}")
    assert new_json["credit_limit_minor"] is None
    assert new_json["is_liability"] is False


def test_patch_flip_asset_to_liability_without_limit_allowed(conn: sqlite3.Connection) -> None:
    acc = accounts.create(conn, USER_ID, NewAccount(name="A", currency="PLN"))
    updated = accounts.update(conn, USER_ID, acc.id, PatchAccount(is_liability=True))
    assert updated.is_liability is True
    assert updated.credit_limit_minor is None


def test_hydrate_is_liability_zero_as_false(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT OR IGNORE INTO users(id, name) VALUES (1, 'default')")
    # Migration 0012 (ADR-0061) dropped the `DEFAULT 1` sentinel; raw SQL
    # paths must declare `user_id` explicitly.
    conn.execute(
        "INSERT INTO accounts(user_id, name, currency, is_liability, credit_limit_minor) "
        "VALUES (1, 'F', 'PLN', 0, NULL)"
    )
    conn.execute(
        "INSERT INTO accounts(user_id, name, currency, is_liability, credit_limit_minor) "
        "VALUES (1, 'T', 'PLN', 1, 500000)"
    )
    f = accounts.find_by_name(conn, USER_ID, "F")
    t = accounts.find_by_name(conn, USER_ID, "T")
    assert f is not None and f.is_liability is False
    assert t is not None and t.is_liability is True
    assert t.credit_limit_minor == 500_000


def test_list_all_includes_new_fields(conn: sqlite3.Connection) -> None:
    accounts.create(conn, USER_ID, NewAccount(name="Bank", currency="PLN"))
    accounts.create(
        conn,
        USER_ID,
        NewAccount(name="Visa", currency="PLN", is_liability=True, credit_limit_minor=100_000),
    )
    rows = accounts.list_all(conn, USER_ID)
    by_name = {a.name: a for a in rows}
    assert by_name["Bank"].is_liability is False
    assert by_name["Bank"].credit_limit_minor is None
    assert by_name["Visa"].is_liability is True
    assert by_name["Visa"].credit_limit_minor == 100_000


def test_audit_log_captures_both_new_fields_on_create_and_update(
    conn: sqlite3.Connection,
) -> None:
    acc = accounts.create(
        conn,
        USER_ID,
        NewAccount(name="V", currency="PLN", is_liability=True, credit_limit_minor=1_000_000),
    )
    accounts.update(conn, USER_ID, acc.id, PatchAccount(credit_limit_minor=2_000_000))
    entries = audit.list_entries(conn, "account", acc.id)
    create_new = json.loads(entries[0].new_json or "{}")
    update_new = json.loads(entries[1].new_json or "{}")
    assert create_new["is_liability"] is True
    assert create_new["credit_limit_minor"] == 1_000_000
    assert update_new["credit_limit_minor"] == 2_000_000
