"""Deterministic-enough seed for the crawler, built through the real forms.

Runs against the per-test scratch DB only. Dates are relative to today so
the Today / ledger pages always have rows in range; the inventory
normalises dates and ids, so drift does not show up in the diff.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import APIRequestContext


@dataclass(frozen=True)
class SeedIds:
    account_id: int
    savings_id: int
    expense_category_id: int
    income_category_id: int
    transaction_id: int
    planned_id: int
    recurring_id: int


def _post(request: APIRequestContext, url: str, form: dict[str, str | float | bool]) -> None:
    resp = request.post(url, form=form)
    assert resp.ok, f"seed POST {url} failed: {resp.status} {resp.text()[:300]}"


def _scalar(db_path: Path, sql: str, params: tuple[object, ...] = ()) -> int:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        row = conn.execute(sql, params).fetchone()
    finally:
        conn.close()
    assert row is not None, f"seed lookup returned nothing: {sql}"
    return int(row[0])


def seed_world(request: APIRequestContext, base_url: str, db_path: Path) -> SeedIds:
    # The owner login must be an admin so /settings/users (404 for others) is crawlable.
    conn = sqlite3.connect(db_path.as_posix(), timeout=10)
    try:
        conn.execute("UPDATE users SET is_admin = 1 WHERE id = 1")
        conn.commit()
    finally:
        conn.close()
    today = datetime.now().astimezone().date()

    def d(offset: int) -> str:
        return (today + timedelta(days=offset)).isoformat()

    _post(
        request,
        f"{base_url}/accounts",
        {"name": "Checking", "currency": "PLN", "opening_balance": "1000.00"},
    )
    _post(
        request,
        f"{base_url}/accounts",
        {"name": "Savings", "currency": "PLN", "opening_balance": "5000.00"},
    )
    _post(request, f"{base_url}/categories", {"name": "Groceries", "direction": "expense"})
    _post(request, f"{base_url}/categories", {"name": "Paycheck", "direction": "income"})

    account_id = _scalar(db_path, "SELECT id FROM accounts WHERE name = 'Checking'")
    savings_id = _scalar(db_path, "SELECT id FROM accounts WHERE name = 'Savings'")
    expense_id = _scalar(db_path, "SELECT id FROM categories WHERE name = 'Groceries'")
    income_id = _scalar(db_path, "SELECT id FROM categories WHERE name = 'Paycheck'")

    for offset, amount, desc in ((-3, "42.50", "weekly shop"), (-1, "12.00", "bread")):
        _post(
            request,
            f"{base_url}/transactions",
            {
                "operation_date": d(offset),
                "category_id": str(expense_id),
                "account_id": str(account_id),
                "amount": amount,
                "description": desc,
            },
        )
    _post(
        request,
        f"{base_url}/transactions",
        {
            "operation_date": d(-2),
            "category_id": str(income_id),
            "account_id": str(account_id),
            "amount": "3000.00",
            "description": "salary",
        },
    )
    _post(
        request,
        f"{base_url}/planned",
        {
            "operation_date": d(5),
            "category_id": str(expense_id),
            "account_id": str(account_id),
            "amount": "80.00",
            "description": "planned shop",
        },
    )
    _post(
        request,
        f"{base_url}/recurring",
        {
            "cadence": "monthly",
            "start_date": d(-20),
            "category_id": str(expense_id),
            "account_id": str(account_id),
            "default_amount": "55.00",
            "default_description": "subscription",
        },
    )
    txn_id = _scalar(db_path, "SELECT MIN(id) FROM transactions WHERE deleted_at IS NULL")
    planned_id = _scalar(
        db_path, "SELECT MIN(id) FROM planned_transactions WHERE deleted_at IS NULL"
    )
    rule_id = _scalar(db_path, "SELECT MIN(id) FROM recurring_rules WHERE deleted_at IS NULL")
    return SeedIds(
        account_id=account_id,
        savings_id=savings_id,
        expense_category_id=expense_id,
        income_category_id=income_id,
        transaction_id=txn_id,
        planned_id=planned_id,
        recurring_id=rule_id,
    )
