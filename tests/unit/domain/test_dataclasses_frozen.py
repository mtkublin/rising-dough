from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from budget_planner.domain import (
    Account,
    AccountSnapshot,
    AccountStats,
    AuditEntry,
    AuditOperation,
    BudgetDefault,
    BudgetOneOffOverride,
    BudgetRecurringOverride,
    Cadence,
    Category,
    Direction,
    FxRate,
    NewAccount,
    NewAccountSnapshot,
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
    NewCategory,
    NewFxRate,
    NewPlannedTransaction,
    NewRecurringOverride,
    NewRecurringRule,
    NewTransaction,
    Occurrence,
    OverrideState,
    PatchAccount,
    PatchCategory,
    PatchPlannedTransaction,
    PatchRecurringRule,
    PatchTransaction,
    PlannedFilter,
    PlannedTransaction,
    RecurringOverride,
    RecurringRule,
    Transaction,
    TransactionFilter,
)

_UTC_NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=UTC)


def test_account_is_frozen() -> None:
    acc = Account(
        id=1,
        user_id=1,
        name="ING",
        type=None,
        currency="PLN",
        opening_balance=0,
        is_liability=False,
        credit_limit_minor=None,
        created_at=_UTC_NOW,
        updated_at=_UTC_NOW,
        deleted_at=None,
    )
    with pytest.raises(FrozenInstanceError):
        acc.name = "Mbank"  # type: ignore[misc]


def test_category_is_frozen() -> None:
    cat = Category(
        id=1,
        user_id=1,
        name="Food",
        direction=Direction.EXPENSE,
        is_system=False,
        color=None,
        created_at=_UTC_NOW,
        updated_at=_UTC_NOW,
        deleted_at=None,
    )
    with pytest.raises(FrozenInstanceError):
        cat.direction = Direction.INCOME  # type: ignore[misc]


def test_transaction_is_frozen() -> None:
    txn = Transaction(
        id=1,
        user_id=1,
        operation_date=date(2026, 1, 1),
        category_id=1,
        account_id=1,
        dest_account_id=None,
        amount=100,
        description="",
        promoted_from_planned_id=None,
        promoted_from_recurring_rule_id=None,
        promoted_from_recurring_date=None,
        created_at=_UTC_NOW,
        updated_at=_UTC_NOW,
        deleted_at=None,
    )
    with pytest.raises(FrozenInstanceError):
        txn.amount = 200  # type: ignore[misc]


def test_transaction_filter_is_hashable() -> None:
    f = TransactionFilter(
        account_ids=(1, 2),
        category_ids=(10,),
        directions=(Direction.INCOME, Direction.EXPENSE),
    )
    # The hashable contract matters because filters flow through LRU caches.
    assert hash(f) == hash(f)


def test_planned_filter_defaults() -> None:
    f = PlannedFilter()
    assert f.account_ids == ()
    assert f.category_ids == ()
    assert f.offset == 0


def test_patch_dtos_as_dict_strips_none() -> None:
    assert PatchAccount().as_dict() == {}
    assert PatchAccount(name="X").as_dict() == {"name": "X"}
    assert PatchCategory(name="Y").as_dict() == {"name": "Y"}
    assert PatchTransaction(amount=50).as_dict() == {"amount": 50}
    assert PatchPlannedTransaction(description="d").as_dict() == {"description": "d"}
    assert PatchRecurringRule(active=False).as_dict() == {"active": False}


def test_new_dtos_construct_with_minimal_fields() -> None:
    assert NewAccount(name="ING", currency="PLN").opening_balance == 0
    assert NewCategory(name="Food", direction=Direction.EXPENSE).is_system is False
    NewTransaction(operation_date=date(2026, 1, 1), category_id=1, account_id=1, amount=100)
    NewPlannedTransaction(operation_date=date(2026, 1, 1), category_id=1, account_id=1, amount=100)
    NewRecurringRule(
        cadence=Cadence.MONTHLY,
        start_date=date(2026, 1, 1),
        category_id=1,
        account_id=1,
        default_amount=100,
    )
    NewRecurringOverride(rule_id=1, occurrence_date=date(2026, 2, 1), state=OverrideState.SKIPPED)
    NewBudgetDefault(category_id=1, amount=1000)
    NewBudgetRecurringOverride(category_id=1, month=12, amount=2000)
    NewBudgetOneOffOverride(category_id=1, year=2026, month=1, amount=3000)
    NewAccountSnapshot(account_id=1, balance=100)
    NewFxRate(date=date(2026, 1, 1), from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.5"))


def test_entity_dataclasses_round_trip() -> None:
    plan = PlannedTransaction(
        id=1,
        user_id=1,
        operation_date=date(2026, 1, 1),
        category_id=1,
        account_id=1,
        dest_account_id=None,
        amount=100,
        description="",
        recurring_rule_id=None,
        occurrence_date=None,
        promoted_to_txn_id=None,
        created_at=_UTC_NOW,
        updated_at=_UTC_NOW,
        deleted_at=None,
    )
    assert plan.amount == 100

    rule = RecurringRule(
        id=1,
        user_id=1,
        cadence=Cadence.MONTHLY,
        start_date=date(2026, 1, 1),
        end_date=None,
        category_id=1,
        account_id=1,
        dest_account_id=None,
        default_amount=100,
        default_description="",
        day_of_month=1,
        month_of_year=None,
        active=True,
        next_due=date(2026, 1, 1),
        last_promoted_date=None,
        created_at=_UTC_NOW,
        updated_at=_UTC_NOW,
        deleted_at=None,
    )
    assert rule.cadence is Cadence.MONTHLY

    ovr = RecurringOverride(
        id=1,
        rule_id=1,
        occurrence_date=date(2026, 2, 1),
        state=OverrideState.OVERRIDDEN,
        amount_override=200,
        description_override=None,
        date_override=None,
        created_at=_UTC_NOW,
    )
    assert ovr.state is OverrideState.OVERRIDDEN

    occ = Occurrence(
        rule_id=1,
        occurrence_date=date(2026, 2, 1),
        effective_date=date(2026, 2, 1),
        category_id=1,
        account_id=1,
        dest_account_id=None,
        amount=200,
        description="",
        is_overridden=True,
        is_skipped=False,
    )
    assert occ.is_overridden is True

    bd = BudgetDefault(
        id=1,
        user_id=1,
        category_id=1,
        amount=1000,
        created_at=_UTC_NOW,
        updated_at=_UTC_NOW,
        deleted_at=None,
    )
    assert bd.amount == 1000
    assert (
        BudgetRecurringOverride(
            id=1,
            user_id=1,
            category_id=1,
            month=12,
            amount=2000,
            created_at=_UTC_NOW,
            updated_at=_UTC_NOW,
            deleted_at=None,
        ).month
        == 12
    )
    assert (
        BudgetOneOffOverride(
            id=1,
            user_id=1,
            category_id=1,
            year=2026,
            month=1,
            amount=3000,
            created_at=_UTC_NOW,
            updated_at=_UTC_NOW,
            deleted_at=None,
        ).year
        == 2026
    )

    snap = AccountSnapshot(id=1, account_id=1, taken_at=_UTC_NOW, balance=100, note="")
    assert snap.balance == 100
    assert (
        AccountStats(
            account_id=1,
            balance=100,
            base_balance=100,
            txn_count=1,
            last_txn_date=None,
        ).balance
        == 100
    )
    fx = FxRate(
        id=1,
        date=date(2026, 1, 1),
        from_ccy="EUR",
        to_ccy="PLN",
        rate=Decimal("4.5"),
        fetched_at=_UTC_NOW,
    )
    assert fx.rate == Decimal("4.5")

    audit = AuditEntry(
        id=1,
        entity_type="account",
        entity_id=1,
        changed_at=_UTC_NOW,
        operation=AuditOperation.CREATE,
        prev_json=None,
        new_json="{}",
    )
    assert audit.operation is AuditOperation.CREATE
