"""Integration tests for POST /recurring/formula/preview (T-R41, ADR-0056 §4)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)

USER_ID = 1


@pytest.fixture
def seed_ids(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        salary = categories_repo.create(
            conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
        )
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
    finally:
        conn.close()
    return {"salary_id": salary.id, "account_id": acc.id}


def test_formula_preview_ok(client: TestClient, seed_ids: dict[str, int]) -> None:
    r = client.post(
        "/recurring/formula/preview",
        data={
            "terms[0][sign]": "+",
            "terms[0][coefficient_percent]": "25",
            "terms[0][source_category_ids]": str(seed_ids["salary_id"]),
        },
    )
    assert r.status_code == 200
    assert "data-formula-preview-ok" in r.text


def test_formula_preview_empty_returns_422(client: TestClient) -> None:
    r = client.post("/recurring/formula/preview", data={})
    assert r.status_code == 422
    assert "data-formula-preview-err" in r.text


def test_formula_preview_invalid_source(client: TestClient) -> None:
    r = client.post(
        "/recurring/formula/preview",
        data={
            "terms[0][sign]": "+",
            "terms[0][coefficient_percent]": "25",
            "terms[0][source_category_ids]": "99999",
        },
    )
    assert r.status_code == 422
    assert 'data-code="invalid_source"' in r.text


def test_formula_preview_invalid_draft_rule_id(client: TestClient) -> None:
    r = client.post(
        "/recurring/formula/preview",
        data={"draft_rule_id": "not-an-int"},
    )
    assert r.status_code == 422
