"""T-034 planned router."""

from __future__ import annotations

import io
import json
from datetime import date

import pyarrow.parquet as pq
import pytest
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


@pytest.fixture
def ctx(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(conn, NewAccount(name="Main", currency="PLN"))
        cat = categories_repo.create(conn, NewCategory(name="Rent", direction=Direction.EXPENSE))
        pl = planned_repo.create(
            conn,
            NewPlannedTransaction(
                operation_date=date(2026, 10, 15),
                category_id=cat.id,
                account_id=acc.id,
                amount=50000,
                description="rent",
            ),
        )
        return {"acc": acc.id, "cat": cat.id, "pl": pl.id}
    finally:
        conn.close()


def test_index_redirects_to_ledger(client: TestClient, ctx: dict[str, int]) -> None:
    """T-070: ``/planned`` returns 302 to the unified ledger (planned view)."""
    r = client.get("/planned", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/ledger?view=planned"


def test_table_fragment(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.get("/planned/table")
    assert "<html" not in r.text
    assert "planned-table" in r.text


def test_new_form(client: TestClient) -> None:
    r = client.get("/planned/new")
    assert r.status_code == 200
    assert 'name="operation_date"' in r.text


def test_create(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        "/planned",
        data={
            "operation_date": "2026-11-01",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "amount": "123.45",
            "description": "x",
        },
    )
    assert r.status_code == 200
    assert "forecast-stale" in r.headers["HX-Trigger"]


def test_create_bad_amount(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        "/planned",
        data={
            "operation_date": "2026-11-01",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "amount": "-1",
        },
    )
    assert r.status_code == 422


def test_create_bad_date(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        "/planned",
        data={
            "operation_date": "bad",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "amount": "1",
        },
    )
    assert r.status_code == 422


def test_create_unknown_account(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        "/planned",
        data={
            "operation_date": "2026-11-01",
            "category_id": ctx["cat"],
            "account_id": 9999,
            "amount": "10",
        },
    )
    assert r.status_code == 422


def test_edit(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.get(f"/planned/{ctx['pl']}/edit")
    assert r.status_code == 200
    assert 'name="amount"' in r.text and 'value="500.00"' in r.text


def test_edit_404(client: TestClient) -> None:
    assert client.get("/planned/9999/edit").status_code == 404


def test_update(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/planned/{ctx['pl']}",
        data={
            "operation_date": "2026-10-20",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "amount": "77.77",
        },
    )
    assert r.status_code == 200
    assert "forecast-stale" in r.headers["HX-Trigger"]


def test_update_404(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        "/planned/9999",
        data={
            "operation_date": "2026-10-20",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "amount": "10",
        },
    )
    assert r.status_code == 404


def test_update_invalid(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/planned/{ctx['pl']}",
        data={
            "operation_date": "bad",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "amount": "-1",
        },
    )
    assert r.status_code == 422


def test_delete(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(f"/planned/{ctx['pl']}/delete")
    assert r.status_code == 200
    assert "forecast-stale" in r.headers["HX-Trigger"]


def test_delete_404(client: TestClient) -> None:
    assert client.post("/planned/9999/delete").status_code == 404


def test_promote_form(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.get(f"/planned/{ctx['pl']}/promote")
    assert r.status_code == 200
    assert "Promote" in r.text


def test_promote_form_404(client: TestClient) -> None:
    assert client.get("/planned/9999/promote").status_code == 404


def test_promote_submit(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/planned/{ctx['pl']}/promote",
        data={"operation_date": "2026-10-20", "amount": "500", "description": "r"},
    )
    assert r.status_code == 200
    hx = json.loads(r.headers["HX-Trigger"])
    assert hx == {"balance-stale": True, "forecast-stale": True, "ledger-stale": True}


def test_promote_submit_invalid(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/planned/{ctx['pl']}/promote",
        data={"operation_date": "bad", "amount": "-1"},
    )
    assert r.status_code == 422


def test_promote_submit_404(client: TestClient) -> None:
    r = client.post(
        "/planned/9999/promote",
        data={"operation_date": "2026-10-20", "amount": "1"},
    )
    assert r.status_code == 404


def test_promote_already_promoted(client: TestClient, ctx: dict[str, int]) -> None:
    client.post(
        f"/planned/{ctx['pl']}/promote",
        data={"operation_date": "2026-10-20", "amount": "500"},
    )
    r = client.post(
        f"/planned/{ctx['pl']}/promote",
        data={"operation_date": "2026-10-20", "amount": "500"},
    )
    assert r.status_code == 422


def test_export_csv(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.get("/planned/export?format=csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")


def test_export_parquet(client: TestClient, ctx: dict[str, int]) -> None:
    # Explicit date window — ctx creates a planned on 2026-10-15 and the
    # default window is "current calendar month" (services.planned.
    # _default_window), which drops the fixture row once today rolls past
    # Oct 2026.
    r = client.get("/planned/export?format=parquet&date_from=2026-10-01&date_to=2026-10-31")
    assert r.status_code == 200
    tbl = pq.read_table(io.BytesIO(r.content))
    assert tbl.num_rows >= 1
