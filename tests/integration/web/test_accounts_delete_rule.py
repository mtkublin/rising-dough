"""Account delete rule dialogs: blocked variants and final confirm (T-UR23, F2.8, ADR-0134 §3)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from tests.ui_map import _html, accounts

USER_ID = 1


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def _account(db: sqlite3.Connection, name: str, **kw: object) -> int:
    return accounts_repo.create(db, USER_ID, NewAccount(name=name, currency="PLN", **kw)).id  # type: ignore[arg-type]  # test helper forwards NewAccount kwargs


def _expense_category(db: sqlite3.Connection) -> int:
    return categories_repo.create(
        db, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id


def _rule(db: sqlite3.Connection, acc: int, cat: int) -> None:
    recurring_repo.create_rule(
        db,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 11, 1),
            category_id=cat,
            account_id=acc,
            default_amount=500,
        ),
    )


def _txn(db: sqlite3.Connection, acc: int, cat: int) -> None:
    transactions_repo.create(
        db,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 11, 10), category_id=cat, account_id=acc, amount=100
        ),
    )


def _audit(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])


def test_blocked_by_recurring_only_links_to_the_rules(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db, "Rules")
    cat = _expense_category(db)
    _rule(db, acc, cat)
    _rule(db, acc, cat)
    r = client.get(f"/accounts/{acc}/edit?intent=delete")
    assert _html.exists(r.text, accounts.blocked_dialog("Rules"))
    assert not _html.exists(r.text, accounts.delete_confirm)
    assert (
        "It has no transactions, but 2 recurring rules still use it. Move or delete them first."
        in _html.text_of(r.text, accounts.blocked_dialog("Rules"))
    )
    link = _html.resolve_one(r.text, accounts.blocked_link)
    assert link["href"] == f"/ledger?account_id={acc}&view=recurring"
    assert link.get_text() == "view recurring rules"


def test_blocked_by_planned_links_to_the_planned_items(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db, "Plans")
    cat = _expense_category(db)
    planned_repo.create(
        db,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 12, 1), category_id=cat, account_id=acc, amount=700
        ),
    )
    _rule(db, acc, cat)
    r = client.get(f"/accounts/{acc}/edit?intent=delete")
    assert (
        "It has no transactions, but 1 planned item and 1 recurring rule still use it."
        " Move or delete them first." in _html.text_of(r.text, accounts.blocked_dialog("Plans"))
    )
    link = _html.resolve_one(r.text, accounts.blocked_link)
    assert link["href"] == f"/ledger?account_id={acc}&view=planned"
    assert link.get_text() == "view planned items"


def test_blocked_by_transactions_and_rules_lists_every_count(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db, "Busy")
    cat = _expense_category(db)
    _txn(db, acc, cat)
    _txn(db, acc, cat)
    _rule(db, acc, cat)
    r = client.get(f"/accounts/{acc}/edit?intent=delete")
    assert (
        "It still has 2 transactions and 1 recurring rule. Move or delete them first."
        in _html.text_of(r.text, accounts.blocked_dialog("Busy"))
    )
    assert _html.resolve_one(r.text, accounts.blocked_link).get_text() == "view 2 transactions"


def test_second_users_rows_do_not_block_and_foreign_account_is_404(
    client: TestClient, db: sqlite3.Connection
) -> None:
    db.execute("INSERT INTO users(id, name) VALUES (2, 'other')")
    acc = _account(db, "Mine")
    theirs = accounts_repo.create(db, 2, NewAccount(name="Theirs", currency="PLN")).id
    their_cat = categories_repo.create(
        db, 2, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id
    transactions_repo.create(
        db,
        2,
        NewTransaction(
            operation_date=date(2026, 11, 10), category_id=their_cat, account_id=theirs, amount=5
        ),
    )
    r = client.get(f"/accounts/{acc}/edit?intent=delete")
    assert _html.exists(r.text, accounts.delete_dialog("Mine"))
    assert client.get(f"/accounts/{theirs}/edit?intent=delete").status_code == 404
    assert client.post(f"/accounts/{theirs}/delete").status_code == 404
    assert accounts_repo.find_by_id(db, 2, theirs) is not None


def test_confirm_post_soft_deletes_and_writes_one_audit_row(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db, "Gone")
    before = _audit(db)
    r = client.post(f"/accounts/{acc}/delete")
    assert r.status_code == 200
    assert r.text == ""
    assert accounts_repo.find_by_id(db, USER_ID, acc) is None
    assert accounts_repo.find_by_id(db, USER_ID, acc, include_deleted=True) is not None
    assert _audit(db) == before + 1


def test_post_while_blocked_is_refused_and_writes_nothing(
    client: TestClient, db: sqlite3.Connection
) -> None:
    acc = _account(db, "Held")
    _rule(db, acc, _expense_category(db))
    before = _audit(db)
    r = client.post(f"/accounts/{acc}/delete")
    assert r.status_code == 409
    assert accounts_repo.find_by_id(db, USER_ID, acc) is not None
    assert _audit(db) == before
