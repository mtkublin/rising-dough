"""T-Q235 (Q-035): bounded work per request.

Page size clamp, body and field-length limits (422/413, nothing stored),
cheap ``/ready`` (no full ``integrity_check`` per unauthenticated probe),
and COUNT/SUM-based ledger counts and balances.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.limits import (
    DESCRIPTION_MAX_LENGTH,
    MAX_BODY_BYTES,
    NAME_MAX_LENGTH,
    PAGE_SIZE_MAX,
)
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.services import balance as balance_service
from budget_planner.web.app import create_app

USER_ID = 1
OTHER_USER_ID = 2
_OPENING = 1000


@pytest.fixture
def seeded(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=_OPENING)
        )
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
        )
        return {"acc": acc.id, "cat": cat.id}
    finally:
        conn.close()


def _txn_form(seeded: dict[str, int], description: str) -> dict[str, Any]:
    return {
        "operation_date": "2026-10-01",
        "category_id": seeded["cat"],
        "account_id": seeded["acc"],
        "amount": "12.34",
        "description": description,
    }


def _count(settings: Settings, table: str) -> int:
    conn = get_connection(settings)
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608
    finally:
        conn.close()


def test_page_size_maximum_is_500() -> None:
    assert PAGE_SIZE_MAX == 500


def test_page_size_request_is_clamped(client: TestClient, seeded: dict[str, int]) -> None:
    from starlette.requests import Request  # noqa: PLC0415

    from budget_planner.web.routers.ledger import parse_filters  # noqa: PLC0415

    scope = {
        "type": "http",
        "query_string": b"page_size=1000000",
        "headers": [],
        "method": "GET",
        "path": "/ledger",
    }
    assert parse_filters(Request(scope)).page_size == PAGE_SIZE_MAX
    assert client.get("/ledger?page_size=1000000").status_code == 200


def test_overlong_transaction_description_is_rejected_and_not_stored(
    client: TestClient, _migrated: Settings, seeded: dict[str, int]
) -> None:
    r = client.post("/transactions", data=_txn_form(seeded, "x" * (DESCRIPTION_MAX_LENGTH + 1)))
    assert r.status_code == 422
    assert f"at most {DESCRIPTION_MAX_LENGTH} characters" in r.text
    assert _count(_migrated, "transactions") == 0


def test_max_length_transaction_description_is_accepted(
    client: TestClient, _migrated: Settings, seeded: dict[str, int]
) -> None:
    r = client.post("/transactions", data=_txn_form(seeded, "x" * DESCRIPTION_MAX_LENGTH))
    assert r.status_code == 200
    assert _count(_migrated, "transactions") == 1


def test_overlong_account_name_is_rejected_and_not_stored(
    client: TestClient, _migrated: Settings, seeded: dict[str, int]
) -> None:
    before = _count(_migrated, "accounts")
    r = client.post("/accounts", data={"name": "n" * (NAME_MAX_LENGTH + 1), "currency": "PLN"})
    assert r.status_code == 422
    assert f"at most {NAME_MAX_LENGTH} characters" in r.text
    assert _count(_migrated, "accounts") == before


def test_overlong_category_name_is_rejected_and_not_stored(
    client: TestClient, _migrated: Settings, seeded: dict[str, int]
) -> None:
    before = _count(_migrated, "categories")
    r = client.post(
        "/categories", data={"name": "n" * (NAME_MAX_LENGTH + 1), "direction": "expense"}
    )
    assert r.status_code == 422
    assert f"at most {NAME_MAX_LENGTH} characters" in r.text
    assert _count(_migrated, "categories") == before


def test_oversized_body_is_rejected_before_storing(
    client: TestClient, _migrated: Settings, seeded: dict[str, int]
) -> None:
    r = client.post("/transactions", data=_txn_form(seeded, "x" * (MAX_BODY_BYTES + 1)))
    assert r.status_code == 413
    assert _count(_migrated, "transactions") == 0


def test_ready_does_not_run_integrity_check(
    monkeypatch: pytest.MonkeyPatch, _migrated: Settings
) -> None:
    statements: list[str] = []
    real = get_connection

    def traced(cfg: Settings) -> sqlite3.Connection:
        conn = real(cfg)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr("budget_planner.web.routers.health.get_connection", traced)
    c = TestClient(create_app(settings=_migrated))
    for _ in range(3):
        assert c.get("/ready").status_code == 200
    assert statements  # the probe did touch the DB
    lowered = " ".join(statements).lower()
    assert "integrity_check" not in lowered
    assert "quick_check" not in lowered


def test_ready_503_does_not_echo_exception_text() -> None:
    cfg = Settings(_env_file=None, database_url="sqlite:////nonexistent/dir/x.db")
    r = TestClient(create_app(settings=cfg)).get("/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "not_ready", "detail": "database unavailable"}


def test_count_and_balance_use_aggregates_and_exact_values(
    _migrated: Settings, seeded: dict[str, int]
) -> None:
    conn = get_connection(_migrated)
    try:
        other_acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Other", currency="PLN", opening_balance=0)
        )
        for amount in (100, 250):
            transactions_repo.create(
                conn,
                USER_ID,
                NewTransaction(
                    operation_date=date(2026, 10, 1),
                    category_id=seeded["cat"],
                    account_id=seeded["acc"],
                    amount=amount,
                ),
            )
        gone = transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=date(2026, 10, 2),
                category_id=seeded["cat"],
                account_id=seeded["acc"],
                amount=9999,
            ),
        )
        transactions_repo.soft_delete(conn, USER_ID, gone.id)
        transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=date(2026, 10, 3),
                category_id=seeded["cat"],
                account_id=other_acc.id,
                amount=77,
            ),
        )
        assert transactions_repo.count_filtered(conn, USER_ID) == 3
        assert transactions_repo.count_filtered(conn, OTHER_USER_ID) == 0
        assert balance_service.derive_balance(conn, USER_ID, seeded["acc"]) == _OPENING - 350
        assert (
            balance_service.derive_balance(
                conn, USER_ID, seeded["acc"], as_of_date=date(2026, 9, 30)
            )
            == _OPENING
        )
    finally:
        conn.close()
