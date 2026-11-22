"""Isolation cases for the transaction, planned and recurring CRUD entry points (T-Q285).

Same world and conventions as ``_isolation_crud_cases.py``: exact values, another user's rows
and the owner's tombstones stay hidden, a foreign write raises and changes nothing, and a
rejected write leaves no row and no audit row.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

import pytest

from budget_planner.domain.enums import Cadence, OverrideState
from budget_planner.domain.planned import (
    NewPlannedTransaction,
    PatchPlannedTransaction,
    PlannedFilter,
)
from budget_planner.domain.recurring import (
    NewRecurringOverride,
    NewRecurringRule,
    PatchRecurringRule,
)
from budget_planner.domain.transactions import (
    NewTransaction,
    PatchTransaction,
    TransactionFilter,
)
from budget_planner.services import planned, recurring_rules, transactions
from budget_planner.services.transactions import ValidationError
from tests.unit.services._isolation_crud_cases import audit_total
from tests.unit.services._isolation_registry import covers
from tests.unit.services.conftest import (
    EXPENSE_RULE_DUE,
    OTHER_ID,
    OWNER_ID,
    WORLD_DAY,
    Tombstones,
    World,
)


def _tomb(world: World) -> Tombstones:
    assert world.tombstones is not None
    return world.tombstones


def _new_txn(world: World, **over: object) -> NewTransaction:
    fields: dict[str, object] = {
        "operation_date": WORLD_DAY,
        "category_id": world.owner.category_id,
        "account_id": world.owner.account_id,
        "amount": 250,
        "description": "coffee",
    }
    return NewTransaction(**{**fields, **over})  # type: ignore[arg-type]  # test-only kwargs merge


def _new_planned(world: World, **over: object) -> NewPlannedTransaction:
    fields: dict[str, object] = {
        "operation_date": WORLD_DAY,
        "category_id": world.owner.category_id,
        "account_id": world.owner.account_id,
        "amount": 250,
        "description": "plan",
    }
    return NewPlannedTransaction(**{**fields, **over})  # type: ignore[arg-type]  # test-only kwargs merge


# --- transactions ---------------------------------------------------


@covers("transactions.find_by_id")
def _case_txn_find_by_id(conn: sqlite3.Connection, world: World) -> None:
    own = transactions.find_by_id(conn, OWNER_ID, world.owner.transaction_id)
    assert own is not None and own.amount == 1_000
    assert transactions.find_by_id(conn, OWNER_ID, world.other.transaction_id) is None
    assert transactions.find_by_id(conn, OTHER_ID, world.owner.transaction_id) is None
    dead = _tomb(world).transaction_id
    assert transactions.find_by_id(conn, OWNER_ID, dead) is None
    kept = transactions.find_by_id(conn, OWNER_ID, dead, include_deleted=True)
    assert kept is not None and kept.amount == 4_242


@covers("transactions.list_filtered")
@covers("transactions.count_filtered")
def _case_txn_list_and_count(conn: sqlite3.Connection, world: World) -> None:
    f = TransactionFilter()
    assert [t.id for t in transactions.list_filtered(conn, OWNER_ID, f)] == [
        world.owner.transaction_id
    ]
    assert [t.id for t in transactions.list_filtered(conn, OTHER_ID, f)] == [
        world.other.transaction_id
    ]
    assert transactions.count_filtered(conn, OWNER_ID, f) == 1
    assert transactions.count_filtered(conn, OTHER_ID) == 1
    assert transactions.count_filtered(conn, OWNER_ID, f, include_deleted=True) == 2


@covers("transactions.list_recently_deleted")
def _case_txn_recently_deleted(conn: sqlite3.Connection, world: World) -> None:
    assert [t.id for t in transactions.list_recently_deleted(conn, OWNER_ID)] == [
        _tomb(world).transaction_id
    ]
    assert transactions.list_recently_deleted(conn, OTHER_ID) == []


def _validate(conn: sqlite3.Connection, world: World, category_id: int, amount: int) -> None:
    transactions.validate_entry(
        conn,
        OWNER_ID,
        category_id=category_id,
        account_id=world.owner.account_id,
        dest_account_id=None,
        amount=amount,
        description="",
    )


@covers("transactions.validate_entry")
def _case_txn_validate_entry(conn: sqlite3.Connection, world: World) -> None:
    with pytest.raises(ValidationError, match=r"^amount must be positive$"):
        _validate(conn, world, world.owner.category_id, 0)
    # A category the caller does not own is left to the repository's ownership check.
    _validate(conn, world, world.other.category_id, 0)
    _validate(conn, world, world.owner.category_id, 1)


@covers("transactions.validate_patched_entry")
def _case_txn_validate_patched(conn: sqlite3.Connection, world: World) -> None:
    mine = transactions.find_by_id(conn, OWNER_ID, world.owner.transaction_id)
    assert mine is not None
    transactions.validate_patched_entry(conn, OWNER_ID, None, PatchTransaction(amount=0))
    with pytest.raises(ValidationError, match=r"^amount must be positive$"):
        transactions.validate_patched_entry(conn, OWNER_ID, mine, PatchTransaction(amount=0))
    transactions.validate_patched_entry(conn, OWNER_ID, mine, PatchTransaction(description="ok"))


@covers("transactions.create")
def _case_txn_create(conn: sqlite3.Connection, world: World) -> None:
    audit_before = audit_total(conn)
    with pytest.raises(ValidationError, match=r"^amount must be positive$"):
        transactions.create(conn, OWNER_ID, _new_txn(world, amount=0))
    with pytest.raises(ValidationError, match=r"^description must be at most 500 characters$"):
        transactions.create(conn, OWNER_ID, _new_txn(world, description="x" * 501))
    with pytest.raises(LookupError):
        transactions.create(conn, OWNER_ID, _new_txn(world, account_id=world.other.account_id))
    assert audit_total(conn) == audit_before
    made = transactions.create(conn, OWNER_ID, _new_txn(world))
    assert (made.user_id, made.amount) == (OWNER_ID, 250)
    assert transactions.count_filtered(conn, OTHER_ID) == 1


@covers("transactions.update")
def _case_txn_update(conn: sqlite3.Connection, world: World) -> None:
    with pytest.raises(LookupError):
        transactions.update(conn, OWNER_ID, world.other.transaction_id, PatchTransaction(amount=5))
    other = transactions.find_by_id(conn, OTHER_ID, world.other.transaction_id)
    assert other is not None and other.amount == 2_000
    with pytest.raises(ValidationError, match=r"^amount must be positive$"):
        transactions.update(conn, OWNER_ID, world.owner.transaction_id, PatchTransaction(amount=0))
    assert (
        transactions.update(
            conn, OWNER_ID, world.owner.transaction_id, PatchTransaction(amount=7)
        ).amount
        == 7
    )


@covers("transactions.soft_delete")
@covers("transactions.undelete")
def _case_txn_soft_delete_undelete(conn: sqlite3.Connection, world: World) -> None:
    with pytest.raises(LookupError):
        transactions.undelete(conn, OTHER_ID, _tomb(world).transaction_id)
    assert transactions.find_by_id(conn, OWNER_ID, _tomb(world).transaction_id) is None
    transactions.soft_delete(
        conn, OTHER_ID, world.owner.transaction_id
    )  # not the caller's row: no-op
    assert transactions.find_by_id(conn, OWNER_ID, world.owner.transaction_id) is not None
    transactions.soft_delete(conn, OWNER_ID, world.owner.transaction_id)
    assert transactions.find_by_id(conn, OWNER_ID, world.owner.transaction_id) is None
    assert transactions.undelete(conn, OWNER_ID, world.owner.transaction_id).amount == 1_000


# --- planned --------------------------------------------------------


@covers("planned.find_by_id")
def _case_planned_find_by_id(conn: sqlite3.Connection, world: World) -> None:
    own = planned.find_by_id(conn, OWNER_ID, world.owner.planned_id)
    assert own is not None and own.amount == 500
    assert planned.find_by_id(conn, OWNER_ID, world.other.planned_id) is None
    assert planned.find_by_id(conn, OTHER_ID, world.owner.planned_id) is None
    dead = _tomb(world).planned_id
    assert planned.find_by_id(conn, OWNER_ID, dead) is None
    kept = planned.find_by_id(conn, OWNER_ID, dead, include_deleted=True)
    assert kept is not None and kept.amount == 8_000


@covers("planned.list_filtered")
def _case_planned_list_filtered(conn: sqlite3.Connection, world: World) -> None:
    assert [p.id for p in planned.list_filtered(conn, OWNER_ID, PlannedFilter())] == [
        world.owner.planned_id
    ]
    assert [p.id for p in planned.list_filtered(conn, OTHER_ID, PlannedFilter())] == [
        world.other.planned_id
    ]


@covers("planned.list_recently_deleted")
def _case_planned_recently_deleted(conn: sqlite3.Connection, world: World) -> None:
    assert [p.id for p in planned.list_recently_deleted(conn, OWNER_ID)] == [
        _tomb(world).planned_id
    ]
    assert planned.list_recently_deleted(conn, OTHER_ID) == []


@covers("planned.create")
def _case_planned_create(conn: sqlite3.Connection, world: World) -> None:
    audit_before = audit_total(conn)
    with pytest.raises(ValidationError, match=r"^amount must be positive$"):
        planned.create(conn, OWNER_ID, _new_planned(world, amount=0))
    with pytest.raises(LookupError):
        planned.create(conn, OWNER_ID, _new_planned(world, category_id=world.other.category_id))
    assert audit_total(conn) == audit_before
    made = planned.create(conn, OWNER_ID, _new_planned(world))
    assert (made.user_id, made.amount) == (OWNER_ID, 250)
    assert [p.id for p in planned.list_filtered(conn, OTHER_ID, PlannedFilter())] == [
        world.other.planned_id
    ]


@covers("planned.update")
def _case_planned_update(conn: sqlite3.Connection, world: World) -> None:
    with pytest.raises(LookupError):
        planned.update(conn, OWNER_ID, world.other.planned_id, PatchPlannedTransaction(amount=5))
    other = planned.find_by_id(conn, OTHER_ID, world.other.planned_id)
    assert other is not None and other.amount == 1_000
    with pytest.raises(ValidationError, match=r"^amount must be positive$"):
        planned.update(conn, OWNER_ID, world.owner.planned_id, PatchPlannedTransaction(amount=-3))
    assert (
        planned.update(
            conn, OWNER_ID, world.owner.planned_id, PatchPlannedTransaction(amount=9)
        ).amount
        == 9
    )


@covers("planned.soft_delete")
@covers("planned.undelete")
def _case_planned_soft_delete_undelete(conn: sqlite3.Connection, world: World) -> None:
    with pytest.raises(LookupError):
        planned.undelete(conn, OTHER_ID, _tomb(world).planned_id)
    planned.soft_delete(conn, OTHER_ID, world.owner.planned_id)  # not the caller's row: no-op
    assert planned.find_by_id(conn, OWNER_ID, world.owner.planned_id) is not None
    planned.soft_delete(conn, OWNER_ID, world.owner.planned_id)
    assert planned.find_by_id(conn, OWNER_ID, world.owner.planned_id) is None
    assert planned.undelete(conn, OWNER_ID, world.owner.planned_id).amount == 500


# --- recurring rules ------------------------------------------------


def _new_rule(world: World, **over: object) -> NewRecurringRule:
    fields: dict[str, object] = {
        "cadence": Cadence.MONTHLY,
        "start_date": EXPENSE_RULE_DUE,
        "category_id": world.owner.category_id,
        "account_id": world.owner.account_id,
        "default_amount": 300,
    }
    return NewRecurringRule(**{**fields, **over})  # type: ignore[arg-type]  # test-only kwargs merge


@covers("recurring_rules.find_rule")
def _case_rule_find(conn: sqlite3.Connection, world: World) -> None:
    own = recurring_rules.find_rule(conn, OWNER_ID, world.owner.rule_id)
    assert own is not None and own.default_amount == 700
    assert recurring_rules.find_rule(conn, OWNER_ID, world.other.rule_id) is None
    assert recurring_rules.find_rule(conn, OTHER_ID, world.owner.rule_id) is None
    dead = _tomb(world).deleted_rule_id
    assert recurring_rules.find_rule(conn, OWNER_ID, dead) is None
    kept = recurring_rules.find_rule(conn, OWNER_ID, dead, include_deleted=True)
    assert kept is not None and kept.default_amount == 7_000


@covers("recurring_rules.list_rules")
def _case_rule_list(conn: sqlite3.Connection, world: World) -> None:
    ids = {r.id for r in recurring_rules.list_rules(conn, OWNER_ID)}
    assert ids == {world.owner.rule_id, world.owner.income_rule_id, _tomb(world).inactive_rule_id}
    active = {r.id for r in recurring_rules.list_rules(conn, OWNER_ID, active_only=True)}
    assert active == {world.owner.rule_id, world.owner.income_rule_id}
    assert {r.id for r in recurring_rules.list_rules(conn, OTHER_ID)} == {
        world.other.rule_id,
        world.other.income_rule_id,
    }


@covers("recurring_rules.create_rule")
def _case_rule_create(conn: sqlite3.Connection, world: World) -> None:
    audit_before = audit_total(conn)
    with pytest.raises(ValidationError, match=r"^end date must be on or after start$"):
        recurring_rules.create_rule(
            conn, OWNER_ID, _new_rule(world, end_date=EXPENSE_RULE_DUE - dt.timedelta(days=1))
        )
    with pytest.raises(ValidationError, match=r"^day of month must be 1 to 31$"):
        recurring_rules.create_rule(conn, OWNER_ID, _new_rule(world, day_of_month=32))
    with pytest.raises(LookupError):
        recurring_rules.create_rule(
            conn, OWNER_ID, _new_rule(world, account_id=world.other.account_id)
        )
    assert audit_total(conn) == audit_before
    made = recurring_rules.create_rule(conn, OWNER_ID, _new_rule(world))
    assert (made.user_id, made.default_amount) == (OWNER_ID, 300)
    assert {r.id for r in recurring_rules.list_rules(conn, OTHER_ID)} == {
        world.other.rule_id,
        world.other.income_rule_id,
    }


@covers("recurring_rules.update_rule")
def _case_rule_update(conn: sqlite3.Connection, world: World) -> None:
    with pytest.raises(LookupError):
        recurring_rules.update_rule(
            conn, OWNER_ID, world.other.rule_id, PatchRecurringRule(default_amount=1)
        )
    other = recurring_rules.find_rule(conn, OTHER_ID, world.other.rule_id)
    assert other is not None and other.default_amount == 1_400
    with pytest.raises(ValidationError, match=r"^end date must be on or after start$"):
        recurring_rules.update_rule(
            conn,
            OWNER_ID,
            world.owner.rule_id,
            PatchRecurringRule(end_date=EXPENSE_RULE_DUE - dt.timedelta(days=1)),
        )
    updated = recurring_rules.update_rule(
        conn, OWNER_ID, world.owner.rule_id, PatchRecurringRule(default_amount=710)
    )
    assert updated.default_amount == 710


@covers("recurring_rules.deactivate_rule")
def _case_rule_deactivate(conn: sqlite3.Connection, world: World) -> None:
    with pytest.raises(LookupError):
        recurring_rules.deactivate_rule(conn, OWNER_ID, world.other.rule_id)
    other = recurring_rules.find_rule(conn, OTHER_ID, world.other.rule_id)
    assert other is not None and other.active is True
    assert recurring_rules.deactivate_rule(conn, OWNER_ID, world.owner.rule_id).active is False


@covers("recurring_rules.upsert_override")
@covers("recurring_rules.list_overrides")
@covers("recurring_rules.delete_override")
def _case_rule_overrides(conn: sqlite3.Connection, world: World) -> None:
    rule = world.owner.rule_id
    day = EXPENSE_RULE_DUE
    with pytest.raises(LookupError):
        recurring_rules.upsert_override(
            conn,
            OTHER_ID,
            NewRecurringOverride(rule_id=rule, occurrence_date=day, state=OverrideState.SKIPPED),
        )
    made = recurring_rules.upsert_override(
        conn,
        OWNER_ID,
        NewRecurringOverride(
            rule_id=rule, occurrence_date=day, state=OverrideState.OVERRIDDEN, amount_override=111
        ),
    )
    assert (made.rule_id, made.amount_override) == (rule, 111)
    assert [o.amount_override for o in recurring_rules.list_overrides(conn, OWNER_ID, rule)] == [
        111
    ]
    assert recurring_rules.list_overrides(conn, OTHER_ID, rule) == []
    recurring_rules.delete_override(conn, OTHER_ID, rule, day)  # not the caller's rule: no-op
    assert len(recurring_rules.list_overrides(conn, OWNER_ID, rule)) == 1
    recurring_rules.delete_override(conn, OWNER_ID, rule, day)
    assert recurring_rules.list_overrides(conn, OWNER_ID, rule) == []
