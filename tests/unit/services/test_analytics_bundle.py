"""Unit tests for :func:`services.analytics.bundle` (T-R43, ADR-0056 §6)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.services import analytics as analytics_svc

USER_ID = 1


@pytest.fixture
def seeded(conn: sqlite3.Connection) -> dict[str, int]:
    acc = accounts_repo.create(
        conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
    )
    income_cat = categories_repo.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    )
    groc = categories_repo.create(
        conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    )
    rent = categories_repo.create(
        conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    )
    # 3 expense + 1 income txns across two months in the trailing-12 window.
    for d, cid, amt in (
        (date(2026, 1, 5), groc.id, 5_000),
        (date(2026, 1, 20), rent.id, 50_000),
        (date(2026, 2, 10), groc.id, 7_000),
        (date(2026, 2, 15), income_cat.id, 100_000),
    ):
        transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=d,
                category_id=cid,
                account_id=acc.id,
                amount=amt,
                description="",
            ),
        )
    return {
        "account_id": acc.id,
        "groc_id": groc.id,
        "rent_id": rent.id,
        "income_id": income_cat.id,
    }


def test_bundle_month_period(conn: sqlite3.Connection, seeded: dict[str, int]) -> None:
    data = analytics_svc.bundle(conn, USER_ID, today=date(2026, 2, 20), period="month")
    assert data.period == "month"
    # Only Feb txns in spend-by-category (groc 7_000).
    labels = {r.category_name: r.amount_minor for r in data.spend_by_category}
    assert labels == {"Groceries": 7_000}


def test_bundle_year_period(conn: sqlite3.Connection, seeded: dict[str, int]) -> None:
    data = analytics_svc.bundle(conn, USER_ID, today=date(2026, 6, 1), period="year")
    labels = {r.category_name: r.amount_minor for r in data.spend_by_category}
    assert labels["Groceries"] == 12_000
    assert labels["Rent"] == 50_000


def test_bundle_trailing_12_averages_divide_by_12(
    conn: sqlite3.Connection, seeded: dict[str, int]
) -> None:
    data = analytics_svc.bundle(conn, USER_ID, today=date(2026, 2, 20), period="month")
    avgs = {r.category_name: r.amount_minor for r in data.twelve_month_averages}
    # (5000 + 7000) / 12 = 1000, (50000) / 12 = 4167
    assert avgs["Groceries"] == 1_000
    assert avgs["Rent"] == 4_167


def test_bundle_monthly_flow_sorted(conn: sqlite3.Connection, seeded: dict[str, int]) -> None:
    data = analytics_svc.bundle(conn, USER_ID, today=date(2026, 2, 20), period="month")
    flow = data.income_vs_expense_monthly
    assert [p.label for p in flow] == sorted(p.label for p in flow)
    by_month = {p.label: p for p in flow}
    assert by_month["2026-01"].expense_minor == 55_000
    assert by_month["2026-02"].income_minor == 100_000
    assert by_month["2026-02"].expense_minor == 7_000


def test_bundle_largest_items_ranked(conn: sqlite3.Connection, seeded: dict[str, int]) -> None:
    data = analytics_svc.bundle(conn, USER_ID, today=date(2026, 6, 1), period="year")
    assert data.largest_items[0].amount_minor == 50_000  # Rent is biggest expense


def test_bundle_largest_limit(conn: sqlite3.Connection, seeded: dict[str, int]) -> None:
    data = analytics_svc.bundle(
        conn, USER_ID, today=date(2026, 6, 1), period="year", largest_limit=1
    )
    assert len(data.largest_items) == 1


def test_bundle_empty_db(conn: sqlite3.Connection) -> None:
    data = analytics_svc.bundle(conn, USER_ID, today=date(2026, 1, 15), period="month")
    assert data.spend_by_category == ()
    assert data.income_vs_expense_monthly == ()
    assert data.largest_items == ()


def test_bundle_trailing_period_window(conn: sqlite3.Connection, seeded: dict[str, int]) -> None:
    data = analytics_svc.bundle(conn, USER_ID, today=date(2026, 2, 20), period="trailing-12")
    # Trailing 12 starts 2025-03.
    assert data.period_start == date(2025, 3, 1)
