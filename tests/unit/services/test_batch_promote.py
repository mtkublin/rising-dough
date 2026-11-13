"""Unit tests for batch_promote_due in services.recurring + services.planned (T-R45)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringOverride, NewRecurringRule
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
)
from budget_planner.services import planned as planned_svc, recurring as recurring_svc

USER_ID = 1


@pytest.fixture
def seeded(conn: sqlite3.Connection) -> dict[str, int]:
    acc = accounts_repo.create(
        conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
    ).id
    groc = categories_repo.create(
        conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id
    return {"account_id": acc, "category_id": groc}


class TestRecurringBatch:
    def test_batch_zero_items_is_noop(
        self, conn: sqlite3.Connection, seeded: dict[str, int]
    ) -> None:
        result = recurring_svc.batch_promote_due(conn, USER_ID, date(2026, 10, 29))
        assert result.promoted_txn_ids == ()
        assert result.advanced_rule_ids == ()

    def test_batch_promotes_due_rule(
        self, conn: sqlite3.Connection, seeded: dict[str, int]
    ) -> None:
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 10, 1),
                category_id=seeded["category_id"],
                account_id=seeded["account_id"],
                default_amount=1_000,
                default_description="",
            ),
        )
        # Force next_due back to a past date so batch_promote picks it up.
        recurring_repo.set_next_due(
            conn, USER_ID, rule.id, next_due=date(2026, 10, 20), last_promoted_date=None
        )
        result = recurring_svc.batch_promote_due(conn, USER_ID, date(2026, 10, 29))
        assert rule.id in result.advanced_rule_ids
        assert len(result.promoted_txn_ids) == 1

    def test_batch_skips_future_rule(
        self, conn: sqlite3.Connection, seeded: dict[str, int]
    ) -> None:
        recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2027, 6, 1),
                category_id=seeded["category_id"],
                account_id=seeded["account_id"],
                default_amount=1_000,
                default_description="",
            ),
        )
        result = recurring_svc.batch_promote_due(conn, USER_ID, date(2026, 10, 29))
        assert result.promoted_txn_ids == ()

    def test_batch_handles_skipped_override(
        self, conn: sqlite3.Connection, seeded: dict[str, int]
    ) -> None:
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 10, 1),
                category_id=seeded["category_id"],
                account_id=seeded["account_id"],
                default_amount=1_000,
                default_description="",
            ),
        )
        due = date(2026, 10, 20)
        recurring_repo.set_next_due(conn, USER_ID, rule.id, next_due=due, last_promoted_date=None)
        recurring_repo.upsert_override(
            conn,
            USER_ID,
            NewRecurringOverride(
                rule_id=rule.id,
                occurrence_date=due,
                state=OverrideState.SKIPPED,
            ),
        )
        result = recurring_svc.batch_promote_due(conn, USER_ID, date(2026, 10, 29))
        assert rule.id in result.skipped_rule_ids
        assert result.promoted_txn_ids == ()


class TestPlannedBatch:
    def test_batch_zero_items_is_noop(
        self, conn: sqlite3.Connection, seeded: dict[str, int]
    ) -> None:
        result = planned_svc.batch_promote_due(conn, USER_ID, date(2026, 10, 29))
        assert result.promoted_txn_ids == ()
        assert result.promoted_planned_ids == ()

    def test_batch_promotes_due_planned(
        self, conn: sqlite3.Connection, seeded: dict[str, int]
    ) -> None:
        pl_id = planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=date(2026, 10, 25),
                category_id=seeded["category_id"],
                account_id=seeded["account_id"],
                amount=5_000,
                description="",
            ),
        ).id
        result = planned_svc.batch_promote_due(conn, USER_ID, date(2026, 10, 29))
        assert pl_id in result.promoted_planned_ids
        assert len(result.promoted_txn_ids) == 1

    def test_batch_skips_future_planned(
        self, conn: sqlite3.Connection, seeded: dict[str, int]
    ) -> None:
        planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=date(2027, 1, 10),
                category_id=seeded["category_id"],
                account_id=seeded["account_id"],
                amount=5_000,
                description="",
            ),
        )
        result = planned_svc.batch_promote_due(conn, USER_ID, date(2026, 10, 29))
        assert result.promoted_txn_ids == ()

    def test_batch_skips_already_promoted(
        self, conn: sqlite3.Connection, seeded: dict[str, int]
    ) -> None:
        pl_id = planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=date(2026, 10, 25),
                category_id=seeded["category_id"],
                account_id=seeded["account_id"],
                amount=5_000,
                description="",
            ),
        ).id
        planned_svc.promote_to_actual(conn, USER_ID, pl_id, planned_svc.PromotionEdits())
        # Second batch pass sees nothing to promote.
        result = planned_svc.batch_promote_due(conn, USER_ID, date(2026, 10, 29))
        assert result.promoted_txn_ids == ()
