"""T-JPY — native-currency amounts use the currency's own decimals (ADR-0006/0008)."""

from __future__ import annotations

from datetime import date

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
)
from budget_planner.web.templating import build_jinja_env

TODAY = date(2026, 11, 6)


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("budget_planner.web.routers.accounts._today", lambda: TODAY)


@pytest.fixture
def jpy_id(_migrated: Settings) -> int:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, 1, NewAccount(name="Tokyo", currency="JPY", opening_balance=100_000)
        ).id
        cat = categories_repo.create(
            conn, 1, NewCategory(name="Rent", direction=Direction.EXPENSE)
        ).id
        planned_repo.create(
            conn,
            1,
            NewPlannedTransaction(
                operation_date=date(2026, 11, 20),
                category_id=cat,
                account_id=acc,
                amount=30_000,
                description="p",
            ),
        )
        return acc
    finally:
        conn.close()


def test_jpy_balance_and_planned_net_have_no_decimals(client: TestClient, jpy_id: int) -> None:
    soup = BeautifulSoup(client.get("/accounts").text, "html.parser")
    row = soup.select_one(f"#account-{jpy_id}")
    assert row is not None
    text = " ".join(row.get_text().split())
    assert "100,000JPY" in text.replace(" ", "")
    assert "\u221230,000 planned → 70,000" in text
    assert "1,000.00" not in text


def test_money_num_filter_per_currency() -> None:
    env = build_jinja_env(Settings(_env_file=None))
    out = env.from_string(
        "{{ 123456|money_num('JPY') }}|{{ 123456|money_num('PLN') }}|"
        "{{ -500|money_num('JPY', abs_value=True) }}|{{ 500|money_num('EUR', signed=True) }}|"
        "[{{ none|money_num('JPY') }}]|{{ 'JPY'|currency_decimals }}"
    ).render()
    assert out == "123,456|1,234.56|500|+5.00|[]|0"
