"""T-ACC1 — Accounts tab planned net sub-line + hero total (ADR-0089)."""

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

USER_ID = 1
TODAY = date(2026, 11, 6)


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("budget_planner.web.routers.accounts._today", lambda: TODAY)


@pytest.fixture
def ids(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        out: dict[str, int] = {}
        for key, name, liab in (
            ("out", "Outflow", False),
            ("inn", "Inflow", False),
            ("zero", "Zero", False),
            ("card", "Card", True),
        ):
            out[key] = accounts_repo.create(
                conn,
                USER_ID,
                NewAccount(
                    name=name,
                    currency="PLN",
                    opening_balance=1_240_000 if key == "out" else (-50_000 if liab else 0),
                    is_liability=liab,
                    credit_limit_minor=200_000 if liab else None,
                ),
            ).id
        exp = categories_repo.create(
            conn, USER_ID, NewCategory(name="Bills", direction=Direction.EXPENSE)
        ).id
        inc = categories_repo.create(
            conn, USER_ID, NewCategory(name="Gift", direction=Direction.INCOME)
        ).id
        for acct, cat, amt, day in (
            ("out", exp, 982_401, 20),
            ("inn", inc, 70_000, 15),
            ("card", exp, 10_000, 18),
        ):
            planned_repo.create(
                conn,
                USER_ID,
                NewPlannedTransaction(
                    operation_date=date(2026, 11, day),
                    category_id=cat,
                    account_id=out[acct],
                    amount=amt,
                    description="p",
                ),
            )
        return out
    finally:
        conn.close()


def _row_text(html: str, account_id: int) -> str:
    soup = BeautifulSoup(html, "html.parser")
    row = soup.select_one(f"#account-{account_id}")
    assert row is not None
    return " ".join(row.get_text().split())


def test_outflow_subline_with_sign_and_projection(client: TestClient, ids: dict[str, int]) -> None:
    html = client.get("/accounts").text
    assert "\u22129,824.01 planned → 2,575.99" in _row_text(html, ids["out"])
    soup = BeautifulSoup(html, "html.parser")
    span = soup.select_one(f"#account-{ids['out']} .rd-acct-planned span")
    assert span is not None
    assert "neg" in span["class"]


def test_inflow_subline_positive(client: TestClient, ids: dict[str, int]) -> None:
    html = client.get("/accounts").text
    assert "+700.00 planned → 700.00" in _row_text(html, ids["inn"])
    soup = BeautifulSoup(html, "html.parser")
    span = soup.select_one(f"#account-{ids['inn']} .rd-acct-planned span")
    assert span is not None
    assert "pos" in span["class"]


def test_zero_net_hides_subline(client: TestClient, ids: dict[str, int]) -> None:
    html = client.get("/accounts").text
    assert "planned" not in _row_text(html, ids["zero"])


def test_liability_has_subline_and_keeps_available(client: TestClient, ids: dict[str, int]) -> None:
    text = _row_text(client.get("/accounts").text, ids["card"])
    assert "\u2212100.00 planned → -600.00" in text
    assert "Available" in text


def test_reconcile_row_includes_subline(client: TestClient, ids: dict[str, int]) -> None:
    r = client.post(f"/accounts/{ids['out']}/reconcile", data={"actual_balance": "12400.00"})
    assert r.status_code == 200
    assert "\u22129,824.01 planned → 2,575.99" in " ".join(
        BeautifulSoup(r.text, "html.parser").get_text().split()
    )


def test_hero_planned_total(client: TestClient, ids: dict[str, int]) -> None:
    soup = BeautifulSoup(client.get("/accounts").text, "html.parser")
    hero = soup.select_one("#accounts-planned-total")
    assert hero is not None
    # -9824.01 + 700.00 - 100.00
    assert "\u22129,224.01" in hero.get_text()


def test_archived_category_with_planned_row_does_not_crash(
    client: TestClient, ids: dict[str, int], _migrated: Settings
) -> None:
    conn = get_connection(_migrated)
    try:
        bills = categories_repo.find_by_name(conn, USER_ID, "Bills")
        assert bills is not None
        categories_repo.soft_delete(conn, USER_ID, bills.id)
    finally:
        conn.close()
    r = client.get("/accounts")
    assert r.status_code == 200
    assert "\u22129,824.01 planned" in _row_text(r.text, ids["out"])
