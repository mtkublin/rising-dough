"""Unit tests for :func:`services.recurring_formula.preview` (T-R41, ADR-0056 §4)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.recurring import (
    NewRecurringRule,
)
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from budget_planner.services import recurring_formula as formula_svc

USER_ID = 1


@pytest.fixture
def seeded(conn: sqlite3.Connection) -> dict[str, int]:
    acc = accounts_repo.create(
        conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
    )
    salary = categories_repo.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    )
    tax = categories_repo.create(
        conn, USER_ID, NewCategory(name="Tax", direction=Direction.EXPENSE)
    )
    # Seed a recurring rule in Salary category so the formula has a source.
    recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 1),
            category_id=salary.id,
            account_id=acc.id,
            default_amount=100_000,
            default_description="salary",
        ),
    )
    # Also a transaction so sums have something to accrue.
    transactions_repo.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 1, 15),
            category_id=salary.id,
            account_id=acc.id,
            amount=100_000,
            description="",
        ),
    )
    return {
        "account_id": acc.id,
        "salary_id": salary.id,
        "tax_id": tax.id,
    }


class TestPreview:
    def test_empty_returns_empty_error(
        self, conn: sqlite3.Connection, seeded: dict[str, int]
    ) -> None:
        result = formula_svc.preview(conn, USER_ID, date(2026, 2, 1), None, [])
        assert isinstance(result, formula_svc.PreviewError)
        assert result.code == "empty"

    def test_single_valid_term_returns_ok(
        self, conn: sqlite3.Connection, seeded: dict[str, int]
    ) -> None:
        drafts = [
            formula_svc.DraftTerm(
                sign="+",
                coefficient_percent="25",
                source_category_ids=(seeded["salary_id"],),
            )
        ]
        result = formula_svc.preview(conn, USER_ID, date(2026, 2, 1), None, drafts)
        assert isinstance(result, formula_svc.PreviewOk)
        assert result.amount_minor == 25_000  # 25% of 100_000

    def test_invalid_source_returns_error_with_term_index(
        self, conn: sqlite3.Connection, seeded: dict[str, int]
    ) -> None:
        drafts = [
            formula_svc.DraftTerm(
                sign="+",
                coefficient_percent="10",
                source_category_ids=(seeded["salary_id"],),
            ),
            formula_svc.DraftTerm(
                sign="+",
                coefficient_percent="10",
                source_category_ids=(99_999,),  # bogus
            ),
        ]
        result = formula_svc.preview(conn, USER_ID, date(2026, 2, 1), None, drafts)
        assert isinstance(result, formula_svc.PreviewError)
        assert result.code == "invalid_source"
        assert result.offending_term_index == 1

    def test_non_positive_result(self, conn: sqlite3.Connection, seeded: dict[str, int]) -> None:
        # Minus one term that cancels — net zero → non_positive.
        drafts = [
            formula_svc.DraftTerm(
                sign="+",
                coefficient_percent="25",
                source_category_ids=(seeded["salary_id"],),
            ),
            formula_svc.DraftTerm(
                sign="-",
                coefficient_percent="25",
                source_category_ids=(seeded["salary_id"],),
            ),
        ]
        result = formula_svc.preview(conn, USER_ID, date(2026, 2, 1), None, drafts)
        assert isinstance(result, formula_svc.PreviewError)
        assert result.code == "non_positive"

    def test_malformed_coefficient_returns_invalid_source_code(
        self, conn: sqlite3.Connection, seeded: dict[str, int]
    ) -> None:
        drafts = [
            formula_svc.DraftTerm(
                sign="+",
                coefficient_percent="not-a-number",
                source_category_ids=(seeded["salary_id"],),
            )
        ]
        result = formula_svc.preview(conn, USER_ID, date(2026, 2, 1), None, drafts)
        assert isinstance(result, formula_svc.PreviewError)
        assert result.offending_term_index == 0

    def test_self_cycle_detected(self, conn: sqlite3.Connection, seeded: dict[str, int]) -> None:
        # Simulate editing the salary rule and referencing its own category:
        # exclude_rule_id = the salary rule id. Preview should flag cycle.
        rules = recurring_repo.list_rules(conn, USER_ID, active_only=True)
        salary_rule = next(r for r in rules if r.category_id == seeded["salary_id"])
        drafts = [
            formula_svc.DraftTerm(
                sign="+",
                coefficient_percent="25",
                source_category_ids=(seeded["salary_id"],),
            )
        ]
        result = formula_svc.preview(conn, USER_ID, date(2026, 2, 1), salary_rule.id, drafts)
        assert isinstance(result, formula_svc.PreviewError)
        assert result.code == "cycle"

    def test_preview_is_pure_read(self, conn: sqlite3.Connection, seeded: dict[str, int]) -> None:
        """ADR-0056 §4 — no DB write."""
        before = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        drafts = [
            formula_svc.DraftTerm(
                sign="+",
                coefficient_percent="25",
                source_category_ids=(seeded["salary_id"],),
            )
        ]
        formula_svc.preview(conn, USER_ID, date(2026, 2, 1), None, drafts)
        after = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        assert before == after
