"""The account service refuses a change of kind (asset/liability) on update (T-UR60)."""

from __future__ import annotations

import sqlite3

import pytest

from budget_planner.domain.accounts import NewAccount, PatchAccount
from budget_planner.domain.errors import ValidationError
from budget_planner.repositories import accounts as accounts_repo
from budget_planner.services import accounts as accounts_svc

USER_ID = 1


def _audit_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])


@pytest.mark.parametrize("liability", [False, True])
def test_update_refuses_a_kind_change(conn: sqlite3.Connection, *, liability: bool) -> None:
    acc = accounts_repo.create(
        conn,
        USER_ID,
        NewAccount(
            name="A",
            currency="PLN",
            is_liability=liability,
            credit_limit_minor=100_000 if liability else None,
        ),
    )
    before = _audit_count(conn)
    with pytest.raises(ValidationError) as err:
        accounts_svc.update(
            conn, USER_ID, acc.id, PatchAccount(name="B", is_liability=not liability)
        )
    assert err.value.fields == {"is_liability": "can't be changed after the account is created"}
    stored = accounts_svc.find_by_id(conn, USER_ID, acc.id)
    assert stored is not None
    assert (stored.name, stored.is_liability) == ("A", liability)
    assert _audit_count(conn) == before


def test_update_with_the_same_or_no_kind_saves(conn: sqlite3.Connection) -> None:
    acc = accounts_repo.create(conn, USER_ID, NewAccount(name="A", currency="PLN"))
    same = accounts_svc.update(conn, USER_ID, acc.id, PatchAccount(name="B", is_liability=False))
    none = accounts_svc.update(conn, USER_ID, acc.id, PatchAccount(name="C"))
    assert (same.name, none.name, none.is_liability) == ("B", "C", False)
