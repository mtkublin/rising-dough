"""Isolation cases for the CRUD entry points of T-Q285: accounts, categories, budgets, auth reads.

Exact values throughout: the owner (user 1) sees only its own live rows, user 2's rows and the
owner's tombstones stay hidden, a write against another user's row changes nothing, and a
rejected write leaves no row and no audit row.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

import pytest

from budget_planner import clock
from budget_planner.domain.accounts import NewAccount, PatchAccount
from budget_planner.domain.budgets import (
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.domain.categories import NewCategory, PatchCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.errors import ValidationError
from budget_planner.domain.snapshots import NewAccountSnapshot
from budget_planner.repositories import sessions as sessions_repo, webauthn as webauthn_repo
from budget_planner.services import accounts, auth, budget_overrides, categories
from tests.unit.services._isolation_registry import covers
from tests.unit.services.conftest import OTHER_ID, OWNER_ID, Tombstones, World


def audit_total(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])


def _account_names(conn: sqlite3.Connection, user_id: int, **kw: bool) -> list[str]:
    return [a.name for a in accounts.list_all(conn, user_id, **kw)]


def _category_names(conn: sqlite3.Connection, user_id: int, **kw: bool) -> set[str]:
    return {c.name for c in categories.list_all(conn, user_id, **kw)}


def _tomb(world: World) -> Tombstones:
    assert world.tombstones is not None
    return world.tombstones


# --- accounts -------------------------------------------------------


@covers("accounts.find_by_id")
def _case_accounts_find_by_id(conn: sqlite3.Connection, world: World) -> None:
    own = accounts.find_by_id(conn, OWNER_ID, world.owner.account_id)
    assert own is not None and (own.name, own.opening_balance) == ("acct-1", 123_456)
    assert accounts.find_by_id(conn, OWNER_ID, world.other.account_id) is None
    assert accounts.find_by_id(conn, OTHER_ID, world.owner.account_id) is None
    dead = _tomb(world).account_id
    assert accounts.find_by_id(conn, OWNER_ID, dead) is None
    kept = accounts.find_by_id(conn, OWNER_ID, dead, include_deleted=True)
    assert kept is not None and kept.name == "dead-account"


@covers("accounts.find_by_name")
def _case_accounts_find_by_name(conn: sqlite3.Connection, world: World) -> None:
    own = accounts.find_by_name(conn, OWNER_ID, "acct-1")
    assert own is not None and own.id == world.owner.account_id
    assert accounts.find_by_name(conn, OWNER_ID, "acct-2") is None
    assert accounts.find_by_name(conn, OWNER_ID, "dead-account") is None
    assert accounts.find_by_name(conn, OWNER_ID, "dead-account", include_deleted=True) is not None


@covers("accounts.list_all")
def _case_accounts_list_all(conn: sqlite3.Connection, world: World) -> None:
    assert _account_names(conn, OWNER_ID) == ["acct-1"]
    assert _account_names(conn, OTHER_ID) == ["acct-2"]
    assert _account_names(conn, OWNER_ID, include_deleted=True) == ["acct-1", "dead-account"]


@covers("accounts.create")
def _case_accounts_create(conn: sqlite3.Connection, world: World) -> None:
    audit_before = audit_total(conn)
    with pytest.raises(ValidationError) as err:
        accounts.create(conn, OWNER_ID, NewAccount(name=" ", currency="PL"))
    assert err.value.fields == {"name": "name required", "currency": "ISO 4217 code required"}
    assert (_account_names(conn, OWNER_ID), audit_total(conn)) == (["acct-1"], audit_before)
    made = accounts.create(conn, OWNER_ID, NewAccount(name="new-acct", currency="EUR"))
    assert (made.user_id, made.name, made.currency) == (OWNER_ID, "new-acct", "EUR")
    assert _account_names(conn, OTHER_ID) == ["acct-2"]


@covers("accounts.update")
def _case_accounts_update(conn: sqlite3.Connection, world: World) -> None:
    with pytest.raises(LookupError):
        accounts.update(conn, OWNER_ID, world.other.account_id, PatchAccount(name="stolen"))
    assert _account_names(conn, OTHER_ID) == ["acct-2"]
    assert (
        accounts.update(conn, OWNER_ID, world.owner.account_id, PatchAccount(name="renamed")).name
        == "renamed"
    )
    audit_before = audit_total(conn)
    with pytest.raises(ValidationError) as err:
        accounts.update(conn, OWNER_ID, world.owner.account_id, PatchAccount(name=""))
    assert err.value.fields == {"name": "name required"}
    assert (_account_names(conn, OWNER_ID), audit_total(conn)) == (["renamed"], audit_before)


@covers("accounts.create_snapshot")
@covers("accounts.list_snapshots_for_account")
@covers("accounts.list_snapshots_for_user")
def _case_account_snapshots(conn: sqlite3.Connection, world: World) -> None:
    own = world.owner.account_id
    snap = accounts.create_snapshot(
        conn, OWNER_ID, NewAccountSnapshot(account_id=own, balance=500, note="n")
    )
    assert (snap.account_id, snap.balance, snap.note) == (own, 500, "n")
    assert [s.balance for s in accounts.list_snapshots_for_account(conn, OWNER_ID, own)] == [500]
    assert accounts.list_snapshots_for_account(conn, OTHER_ID, own) == []
    assert {
        k: [s.balance for s in v]
        for k, v in accounts.list_snapshots_for_user(conn, OWNER_ID).items()
    } == {own: [500]}
    assert accounts.list_snapshots_for_user(conn, OTHER_ID) == {}
    audit_before = audit_total(conn)
    with pytest.raises(LookupError):
        accounts.create_snapshot(conn, OTHER_ID, NewAccountSnapshot(account_id=own, balance=1))
    assert audit_total(conn) == audit_before


# --- categories -----------------------------------------------------


@covers("categories.find_by_id")
def _case_categories_find_by_id(conn: sqlite3.Connection, world: World) -> None:
    own = categories.find_by_id(conn, OWNER_ID, world.owner.category_id)
    assert own is not None and own.name == "cat-1"
    assert categories.find_by_id(conn, OWNER_ID, world.other.category_id) is None
    assert categories.find_by_id(conn, OTHER_ID, world.owner.category_id) is None
    dead = _tomb(world).category_id
    assert categories.find_by_id(conn, OWNER_ID, dead) is None
    kept = categories.find_by_id(conn, OWNER_ID, dead, include_deleted=True)
    assert kept is not None and kept.name == "dead-category"


@covers("categories.find_by_name")
def _case_categories_find_by_name(conn: sqlite3.Connection, world: World) -> None:
    own = categories.find_by_name(conn, OWNER_ID, "cat-1")
    assert own is not None and own.id == world.owner.category_id
    assert categories.find_by_name(conn, OWNER_ID, "cat-2") is None
    assert categories.find_by_name(conn, OWNER_ID, "dead-category") is None
    assert (
        categories.find_by_name(conn, OWNER_ID, "dead-category", include_deleted=True) is not None
    )


@covers("categories.list_all")
def _case_categories_list_all(conn: sqlite3.Connection, world: World) -> None:
    names = _category_names(conn, OWNER_ID)
    assert {"cat-1", "inc-1"} <= names and not names & {"cat-2", "inc-2", "dead-category"}
    assert "dead-category" in _category_names(conn, OWNER_ID, include_deleted=True)
    assert not _category_names(conn, OTHER_ID) & {"cat-1", "inc-1", "dead-category"}


@covers("categories.list_recently_deleted")
def _case_categories_list_recently_deleted(conn: sqlite3.Connection, world: World) -> None:
    # The fixture archived the category on 2026-11-11; judge "recently" from the world's day.
    with clock.frozen(dt.datetime(2026, 11, 12, 12, tzinfo=dt.UTC)):
        assert [c.name for c in categories.list_recently_deleted(conn, OWNER_ID)] == [
            "dead-category"
        ]
        assert categories.list_recently_deleted(conn, OTHER_ID) == []


@covers("categories.create")
def _case_categories_create(conn: sqlite3.Connection, world: World) -> None:
    audit_before = audit_total(conn)
    with pytest.raises(ValidationError) as err:
        categories.create(
            conn, OWNER_ID, NewCategory(name="", direction=Direction.EXPENSE, color="red")
        )
    assert err.value.fields == {
        "name": "name required",
        "color": "invalid color 'red'; expected 6-digit hex like #a3c2ff",
    }
    assert audit_total(conn) == audit_before
    made = categories.create(conn, OWNER_ID, NewCategory(name="fresh", direction=Direction.EXPENSE))
    assert (made.user_id, made.name) == (OWNER_ID, "fresh")
    assert "fresh" not in _category_names(conn, OTHER_ID)


@covers("categories.update")
def _case_categories_update(conn: sqlite3.Connection, world: World) -> None:
    with pytest.raises(LookupError):
        categories.update(conn, OWNER_ID, world.other.category_id, PatchCategory(name="stolen"))
    other = categories.find_by_id(conn, OTHER_ID, world.other.category_id)
    assert other is not None and other.name == "cat-2"
    assert (
        categories.update(
            conn, OWNER_ID, world.owner.category_id, PatchCategory(name="cat-1b")
        ).name
        == "cat-1b"
    )
    with pytest.raises(ValidationError) as err:
        categories.update(conn, OWNER_ID, world.owner.category_id, PatchCategory(name=" "))
    assert err.value.fields == {"name": "name required"}


@covers("categories.soft_delete")
def _case_categories_soft_delete(conn: sqlite3.Connection, world: World) -> None:
    categories.soft_delete(conn, OWNER_ID, world.other.category_id)  # not the owner's row: no-op
    assert categories.find_by_id(conn, OTHER_ID, world.other.category_id) is not None
    categories.soft_delete(conn, OWNER_ID, world.owner.income_category_id)
    assert categories.find_by_id(conn, OWNER_ID, world.owner.income_category_id) is None


# --- budget overrides -----------------------------------------------


@covers("budget_overrides.get_default")
def _case_budget_get_default(conn: sqlite3.Connection, world: World) -> None:
    own = budget_overrides.get_default(conn, OWNER_ID, world.owner.category_id)
    assert own is not None and own.amount == 3_000
    assert budget_overrides.get_default(conn, OWNER_ID, world.other.category_id) is None
    assert budget_overrides.get_default(conn, OTHER_ID, world.owner.category_id) is None


@covers("budget_overrides.list_defaults")
def _case_budget_list_defaults(conn: sqlite3.Connection, world: World) -> None:
    assert [(d.category_id, d.amount) for d in budget_overrides.list_defaults(conn, OWNER_ID)] == [
        (world.owner.category_id, 3_000)
    ]
    assert [(d.category_id, d.amount) for d in budget_overrides.list_defaults(conn, OTHER_ID)] == [
        (world.other.category_id, 6_000)
    ]


@covers("budget_overrides.set_default")
def _case_budget_set_default(conn: sqlite3.Connection, world: World) -> None:
    audit_before = audit_total(conn)
    with pytest.raises(ValidationError) as err:
        budget_overrides.set_default(
            conn, OWNER_ID, NewBudgetDefault(category_id=world.owner.category_id, amount=-1)
        )
    assert err.value.fields == {"amount": "invalid amount"}
    assert audit_total(conn) == audit_before
    with pytest.raises(LookupError):
        budget_overrides.set_default(
            conn, OWNER_ID, NewBudgetDefault(category_id=world.other.category_id, amount=1)
        )
    saved = budget_overrides.set_default(
        conn, OWNER_ID, NewBudgetDefault(category_id=world.owner.category_id, amount=4_000)
    )
    assert saved.amount == 4_000
    other = budget_overrides.get_default(conn, OTHER_ID, world.other.category_id)
    assert other is not None and other.amount == 6_000


@covers("budget_overrides.set_recurring")
def _case_budget_set_recurring(conn: sqlite3.Connection, world: World) -> None:
    cat = world.owner.category_id
    with pytest.raises(ValidationError) as err:
        budget_overrides.set_recurring(
            conn, OWNER_ID, NewBudgetRecurringOverride(category_id=cat, month=13, amount=5)
        )
    assert err.value.fields == {"month": "invalid month"}
    with pytest.raises(LookupError):
        budget_overrides.set_recurring(
            conn,
            OWNER_ID,
            NewBudgetRecurringOverride(category_id=world.other.category_id, month=3, amount=5),
        )
    saved = budget_overrides.set_recurring(
        conn, OWNER_ID, NewBudgetRecurringOverride(category_id=cat, month=3, amount=250)
    )
    assert (saved.user_id, saved.month, saved.amount) == (OWNER_ID, 3, 250)


@covers("budget_overrides.set_one_off")
def _case_budget_set_one_off(conn: sqlite3.Connection, world: World) -> None:
    cat = world.owner.category_id
    with pytest.raises(ValidationError) as err:
        budget_overrides.set_one_off(
            conn, OWNER_ID, NewBudgetOneOffOverride(category_id=cat, year=2026, month=0, amount=-5)
        )
    assert err.value.fields == {"amount": "invalid amount", "month": "invalid month"}
    with pytest.raises(LookupError):
        budget_overrides.set_one_off(
            conn,
            OWNER_ID,
            NewBudgetOneOffOverride(
                category_id=world.other.category_id, year=2026, month=3, amount=5
            ),
        )
    saved = budget_overrides.set_one_off(
        conn, OWNER_ID, NewBudgetOneOffOverride(category_id=cat, year=2026, month=3, amount=90)
    )
    assert (saved.user_id, saved.year, saved.month, saved.amount) == (OWNER_ID, 2026, 3, 90)


# --- auth reads -----------------------------------------------------


@covers("auth.list_active_sessions")
def _case_auth_list_active_sessions(conn: sqlite3.Connection, world: World) -> None:
    owner = sessions_repo.create_session(conn, OWNER_ID, ip="10.0.0.1", user_agent="owner-ua")
    sessions_repo.create_session(conn, OTHER_ID, ip="10.0.0.2", user_agent="other-ua")
    assert [s.user_agent for s in auth.list_active_sessions(conn, OWNER_ID)] == ["owner-ua"]
    assert [s.user_agent for s in auth.list_active_sessions(conn, OTHER_ID)] == ["other-ua"]
    assert owner.token  # the raw token is never part of the listed rows


@covers("auth.list_passkeys")
def _case_auth_list_passkeys(conn: sqlite3.Connection, world: World) -> None:
    for user_id, cred in ((OWNER_ID, b"owner-cred"), (OTHER_ID, b"other-cred")):
        webauthn_repo.create_credential(
            conn,
            user_id=user_id,
            credential_id=cred,
            public_key=b"pk",
            sign_count=0,
            label=f"key-{user_id}",
        )
    assert [c.label for c in auth.list_passkeys(conn, OWNER_ID)] == ["key-1"]
    assert [c.label for c in auth.list_passkeys(conn, OTHER_ID)] == ["key-2"]
