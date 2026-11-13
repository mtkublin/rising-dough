"""Tests for the planned log service (T-023 / T-119).

Post-T-119 (ADR-0038): `list_planned` returns ONLY persisted rows. The
virtual-recurring union moved to `services.upcoming` + `services.income`;
tests covering the virtual expansion live in `test_upcoming.py` and
`test_income.py`.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from unittest.mock import patch

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.planned import NewPlannedTransaction, PlannedFilter
from budget_planner.domain.recurring import NewRecurringOverride, NewRecurringRule
from budget_planner.domain.transactions import TransactionFilter
from budget_planner.repositories import accounts, categories, planned, recurring, transactions
from budget_planner.services import planned as pl_svc
from budget_planner.services.planned import (
    AlreadyPromotedError,
    CannotPromoteDeletedError,
    PlannedNotFoundError,
    PromotionEdits,
    UnsupportedDirectionError,
    ValidationError,
)

USER_ID = 1


@pytest.fixture
def world(conn: sqlite3.Connection) -> dict[str, int]:
    checking = accounts.create(conn, USER_ID, NewAccount(name="Checking", currency="PLN")).id
    savings = accounts.create(conn, USER_ID, NewAccount(name="Savings", currency="PLN")).id
    eur = accounts.create(conn, USER_ID, NewAccount(name="EUR", currency="EUR")).id
    groceries = categories.create(
        conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id
    rent = categories.create(
        conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id
    salary = categories.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    ).id
    transit = categories.find_by_name(conn, USER_ID, "Transit")
    reconciliation = categories.find_by_name(conn, USER_ID, "Reconciliation")
    assert transit is not None and reconciliation is not None
    rule_rent = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 5),
            category_id=rent,
            account_id=checking,
            default_amount=200_000,
            default_description="rent",
        ),
    )
    # Overrides still persisted so other services (`upcoming`, `income`)
    # can exercise them without reconstituting the fixture.
    recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rule_rent.id,
            occurrence_date=date(2026, 3, 5),
            state=OverrideState.SKIPPED,
        ),
    )
    recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rule_rent.id,
            occurrence_date=date(2026, 4, 5),
            state=OverrideState.OVERRIDDEN,
            amount_override=210_000,
        ),
    )
    p1 = planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 2, 20),
            category_id=groceries,
            account_id=checking,
            amount=12_345,
            description="valentine groceries",
        ),
    ).id
    # Persisted materialisation of the Jan 5 recurring occurrence (historical dedup target).
    p2 = planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 1, 5),
            category_id=rent,
            account_id=checking,
            amount=200_000,
            description="rent (edited)",
            recurring_rule_id=rule_rent.id,
            occurrence_date=date(2026, 1, 5),
        ),
    ).id
    return {
        "checking": checking,
        "savings": savings,
        "eur": eur,
        "groceries": groceries,
        "rent": rent,
        "salary": salary,
        "transit": transit.id,
        "reconciliation": reconciliation.id,
        "rule_rent": rule_rent.id,
        "p1": p1,
        "p2": p2,
    }


# ---------------------------------------------------------------------------
# list_planned — persisted-only after T-119
# ---------------------------------------------------------------------------
def test_list_planned_persisted_only(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    """No virtual rows ever surface — only ``kind='persisted'`` is possible."""
    rows = pl_svc.list_planned(
        conn,
        USER_ID,
        PlannedFilter(date_from=date(2026, 1, 1), date_to=date(2026, 12, 31)),
    )
    assert rows  # fixture seeds at least two persisted rows
    assert all(r.kind == "persisted" for r in rows)
    assert all(r.persisted_id is not None for r in rows)


def test_list_planned_no_virtual_rows_in_month_without_persisted(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """February: active rule exists but no persisted row — list stays empty."""
    rows = pl_svc.list_planned(
        conn,
        USER_ID,
        PlannedFilter(date_from=date(2026, 2, 1), date_to=date(2026, 2, 28)),
    )
    rent_rows = [r for r in rows if r.recurring_rule_id == world["rule_rent"]]
    assert rent_rows == []


def test_list_planned_category_filter(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    rows = pl_svc.list_planned(
        conn,
        USER_ID,
        PlannedFilter(
            date_from=date(2026, 1, 1),
            date_to=date(2026, 6, 30),
            category_ids=(world["groceries"],),
        ),
    )
    assert len(rows) == 1
    assert rows[0].persisted_id == world["p1"]


def test_list_planned_account_filter(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    rows = pl_svc.list_planned(
        conn,
        USER_ID,
        PlannedFilter(
            date_from=date(2026, 1, 1),
            date_to=date(2026, 6, 30),
            account_ids=(world["savings"],),
        ),
    )
    assert rows == ()


def test_list_planned_recurring_rule_id_filter_excludes(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    rows = pl_svc.list_planned(
        conn,
        USER_ID,
        PlannedFilter(
            date_from=date(2026, 1, 1),
            date_to=date(2026, 3, 31),
            recurring_rule_id=world["rule_rent"],
        ),
    )
    assert all(r.recurring_rule_id == world["rule_rent"] for r in rows)


def test_list_planned_promoted_filter_excludes(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    pl_svc.promote_to_actual(conn, USER_ID, world["p1"], PromotionEdits())
    rows = pl_svc.list_planned(
        conn,
        USER_ID,
        PlannedFilter(date_from=date(2026, 1, 1), date_to=date(2026, 6, 30), promoted=False),
    )
    assert all(not r.is_promoted for r in rows)


def test_list_planned_sort_order(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    rows = pl_svc.list_planned(
        conn,
        USER_ID,
        PlannedFilter(date_from=date(2026, 1, 1), date_to=date(2026, 6, 30)),
    )
    dates = [r.operation_date for r in rows]
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# promote_to_actual
# ---------------------------------------------------------------------------
def test_promote_happy_path(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    txn = pl_svc.promote_to_actual(conn, USER_ID, world["p1"], PromotionEdits())
    assert txn.promoted_from_planned_id == world["p1"]
    assert txn.amount == 12_345
    assert txn.operation_date == date(2026, 2, 20)
    pt = planned.find_by_id(conn, USER_ID, world["p1"])
    assert pt is not None
    assert pt.promoted_to_txn_id == txn.id


def test_promote_with_edits(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    txn = pl_svc.promote_to_actual(
        conn,
        USER_ID,
        world["p1"],
        PromotionEdits(
            operation_date=date(2026, 2, 22),
            amount_minor=11_000,
            description="valentine (edited)",
        ),
    )
    assert txn.operation_date == date(2026, 2, 22)
    assert txn.amount == 11_000
    assert txn.description == "valentine (edited)"


def test_promote_already_blocked(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    pl_svc.promote_to_actual(conn, USER_ID, world["p1"], PromotionEdits())
    with pytest.raises(AlreadyPromotedError):
        pl_svc.promote_to_actual(conn, USER_ID, world["p1"], PromotionEdits())


def test_promote_deleted_raises(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    planned.soft_delete(conn, USER_ID, world["p1"])
    with pytest.raises(CannotPromoteDeletedError):
        pl_svc.promote_to_actual(conn, USER_ID, world["p1"], PromotionEdits())


def test_promote_adjustment_unsupported(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    adj_p = planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 3, 1),
            category_id=world["reconciliation"],
            account_id=world["checking"],
            amount=100,
        ),
    ).id
    with pytest.raises(UnsupportedDirectionError):
        pl_svc.promote_to_actual(conn, USER_ID, adj_p, PromotionEdits())


def test_promote_transit_cross_currency_rejected(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    trans_p = planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 3, 1),
            category_id=world["transit"],
            account_id=world["checking"],
            dest_account_id=world["eur"],
            amount=1000,
        ),
    ).id
    with pytest.raises(ValidationError):
        pl_svc.promote_to_actual(conn, USER_ID, trans_p, PromotionEdits())


def test_promote_transit_same_currency(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    trans_p = planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 3, 1),
            category_id=world["transit"],
            account_id=world["checking"],
            dest_account_id=world["savings"],
            amount=1000,
        ),
    ).id
    txn = pl_svc.promote_to_actual(conn, USER_ID, trans_p, PromotionEdits())
    assert txn.dest_account_id == world["savings"]


def test_promote_unknown_id(conn: sqlite3.Connection) -> None:
    with pytest.raises(PlannedNotFoundError):
        pl_svc.promote_to_actual(conn, USER_ID, 9999, PromotionEdits())


def test_promote_amount_zero_rejected(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        pl_svc.promote_to_actual(conn, USER_ID, world["p1"], PromotionEdits(amount_minor=0))


def test_rollback_on_stamp_failure(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    empty = TransactionFilter()
    before = len(transactions.list_filtered(conn, USER_ID, filters=empty))
    with (
        patch(
            "budget_planner.services.planned.planned_repo.stamp_promotion",
            side_effect=RuntimeError("boom"),
        ),
        pytest.raises(RuntimeError),
    ):
        pl_svc.promote_to_actual(conn, USER_ID, world["p1"], PromotionEdits())
    after = len(transactions.list_filtered(conn, USER_ID, filters=empty))
    assert before == after
    pt = planned.find_by_id(conn, USER_ID, world["p1"])
    assert pt is not None
    assert pt.promoted_to_txn_id is None
