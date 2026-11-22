"""Domain audit rows carry the owner and the actor (T-D145, ADR-0122).

Every domain write by a user must land in ``audit_log`` with ``user_id`` =
owner and ``actor_user_id`` = acting user (identical for self-service
writes), so ``audit_tail`` shows the user their own payloads.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from budget_planner.domain.accounts import NewAccount, PatchAccount
from budget_planner.domain.budgets import (
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringOverride, NewRecurringRule
from budget_planner.domain.snapshots import NewAccountSnapshot
from budget_planner.domain.transactions import NewTransaction, PatchTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    fx as fx_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    snapshots as snapshots_repo,
    transactions as txn_repo,
)
from budget_planner.services import audit_tail
from budget_planner.services.recurring import PromotionEdits, promote_recurring, skip_and_advance
from tests.formula_fx_support import formula_fx_of

OWNER = 2
OTHER = 1

pytestmark = pytest.mark.integration


@pytest.fixture
def owner_conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.execute("INSERT INTO users (id, name) VALUES (?, 'owner')", (OWNER,))
    return conn


def _domain_rows(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        db.execute(
            "SELECT entity_type, operation, user_id, actor_user_id "
            "FROM audit_log WHERE entity_type != 'fx_rate' "
            "AND entity_type NOT IN ('users', 'categories') ORDER BY id"
        )
    )


def _write_everything(db: sqlite3.Connection) -> None:
    cat = categories_repo.create(db, OWNER, NewCategory(name="Food", direction=Direction.EXPENSE))
    categories_repo.soft_delete(db, OWNER, cat.id)
    categories_repo.undelete(db, OWNER, cat.id)
    acc = accounts_repo.create(db, OWNER, NewAccount(name="Main", currency="PLN"))
    accounts_repo.update(db, OWNER, acc.id, PatchAccount(name="Main2"))
    snapshots_repo.create(db, OWNER, NewAccountSnapshot(account_id=acc.id, balance=5))
    txn = txn_repo.create(
        db,
        OWNER,
        NewTransaction(
            operation_date=date(2026, 1, 1), category_id=cat.id, account_id=acc.id, amount=100
        ),
    )
    txn_repo.update(db, OWNER, txn.id, PatchTransaction(description="x"))
    txn_repo.soft_delete(db, OWNER, txn.id)
    txn_repo.undelete(db, OWNER, txn.id)
    pl = planned_repo.create(
        db,
        OWNER,
        NewPlannedTransaction(
            operation_date=date(2026, 2, 1), category_id=cat.id, account_id=acc.id, amount=5
        ),
    )
    planned_repo.soft_delete(db, OWNER, pl.id)
    planned_repo.undelete(db, OWNER, pl.id)
    rule = recurring_repo.create_rule(
        db,
        OWNER,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 15),
            category_id=cat.id,
            account_id=acc.id,
            default_amount=10,
        ),
    )
    recurring_repo.upsert_override(
        db,
        OWNER,
        NewRecurringOverride(
            rule_id=rule.id, occurrence_date=rule.next_due, state=OverrideState.SKIPPED
        ),
    )
    recurring_repo.delete_override(db, OWNER, rule.id, rule.next_due)
    promote_recurring(db, OWNER, rule.id, PromotionEdits(), fx=formula_fx_of(db, OWNER))
    skip_and_advance(db, OWNER, rule.id)
    recurring_repo.soft_delete_rule(db, OWNER, rule.id)
    budgets_repo.set_default(db, OWNER, NewBudgetDefault(category_id=cat.id, amount=1))
    budgets_repo.clear_default(db, OWNER, cat.id)
    budgets_repo.set_recurring(
        db, OWNER, NewBudgetRecurringOverride(category_id=cat.id, month=3, amount=1)
    )
    budgets_repo.clear_recurring(db, OWNER, cat.id, 3)
    budgets_repo.set_one_off(
        db, OWNER, NewBudgetOneOffOverride(category_id=cat.id, year=2026, month=3, amount=1)
    )
    budgets_repo.clear_one_off(db, OWNER, cat.id, 2026, 3)


def test_every_domain_write_records_owner_and_actor(owner_conn: sqlite3.Connection) -> None:
    _write_everything(owner_conn)
    rows = _domain_rows(owner_conn)
    assert {r["entity_type"] for r in rows} >= {
        "account",
        "category",
        "transaction",
        "planned_transaction",
        "recurring_rule",
        "recurring_override",
        "snapshot",
        "budget_default",
        "budget_recurring_override",
        "budget_one_off_override",
    }
    bad = [
        (r["entity_type"], r["operation"], r["user_id"], r["actor_user_id"])
        for r in rows
        if (r["user_id"], r["actor_user_id"]) != (OWNER, OWNER)
    ]
    assert bad == []


def test_global_fx_rate_row_has_no_owner(conn: sqlite3.Connection) -> None:
    fx_repo.upsert_rate(
        conn, NewFxRate(date=date(2026, 1, 1), from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.3"))
    )
    row = conn.execute(
        "SELECT user_id, actor_user_id FROM audit_log WHERE entity_type = 'fx_rate'"
    ).fetchone()
    assert (row["user_id"], row["actor_user_id"]) == (None, None)


def test_audit_tail_shows_owner_their_own_payload(owner_conn: sqlite3.Connection) -> None:
    acc = accounts_repo.create(owner_conn, OWNER, NewAccount(name="Mine", currency="PLN"))
    mine = audit_tail.audit_tail(owner_conn, OWNER, 1)[0]
    assert mine["entity_id"] == acc.id
    assert mine["new"] != audit_tail.OTHER_USER
    assert isinstance(mine["new"], dict)
    assert mine["new"]["name"] == "Mine"
    assert audit_tail.audit_tail(owner_conn, OTHER, 1)[0]["new"] == audit_tail.OTHER_USER


def test_make_helpers_attribute_to_default_user(
    conn: sqlite3.Connection, make_account: Callable[..., int]
) -> None:
    make_account(name="A")
    row = conn.execute("SELECT user_id, actor_user_id FROM audit_log WHERE entity_type='account'")
    assert tuple(row.fetchone()) == (1, 1)


def test_backfill_migration_fills_owner_only_where_null(owner_conn: sqlite3.Connection) -> None:
    acc = accounts_repo.create(owner_conn, OWNER, NewAccount(name="Old", currency="PLN"))
    owner_conn.execute("UPDATE audit_log SET user_id = NULL, actor_user_id = NULL")
    fx_repo.upsert_rate(
        owner_conn,
        NewFxRate(date=date(2026, 1, 1), from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.3")),
    )
    sql = Path("migrations/0016_audit_backfill_owner.sql").read_text()
    owner_conn.executescript(sql)
    row = owner_conn.execute(
        "SELECT user_id, actor_user_id FROM audit_log WHERE entity_type='account' AND entity_id=?",
        (acc.id,),
    ).fetchone()
    assert (row["user_id"], row["actor_user_id"]) == (OWNER, None)
    fx = owner_conn.execute("SELECT user_id FROM audit_log WHERE entity_type='fx_rate'").fetchone()
    assert fx["user_id"] is None
