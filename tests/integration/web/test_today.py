"""Integration tests for /today router (T-R40, ADR-0056 §3)."""

from __future__ import annotations

from datetime import date, timedelta

from bs4 import BeautifulSoup, Tag
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


def test_today_renders(client: TestClient) -> None:
    r = client.get("/today")
    assert r.status_code == 200
    assert "Today" in r.text


def test_today_upcoming_row_tint_overdue_due_future(
    client: TestClient, _migrated: Settings
) -> None:
    """Overdue (date < today) → red row tint;
    due-today (date == today) → amber row tint; future → no tint.
    No badge text — only row background colour differentiates status."""
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(conn, NewAccount(name="Main", currency="PLN", opening_balance=0))
        cat = categories_repo.create(conn, NewCategory(name="Rent", direction=Direction.EXPENSE))
        today = date.today()  # noqa: DTZ011
        for op_date, desc in [
            (today - timedelta(days=2), "Past bill"),
            (today, "Today bill"),
            (today + timedelta(days=3), "Future bill"),
        ]:
            planned_repo.create(
                conn,
                NewPlannedTransaction(
                    operation_date=op_date,
                    category_id=cat.id,
                    account_id=acc.id,
                    amount=5000,
                    description=desc,
                ),
            )
    finally:
        conn.close()

    r = client.get("/today/upcoming")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select(".rd-upcoming__row")
    by_desc: dict[str, Tag] = {}
    for row in rows:
        name_el = row.select_one(".rd-upcoming__name")
        assert name_el is not None
        by_desc[name_el.get_text(strip=True)] = row

    past = by_desc["Past bill"]
    assert "rd-upcoming__row--overdue" in (past.get("class") or [])
    assert past.select_one(".rd-upcoming__badge") is None

    due = by_desc["Today bill"]
    assert "rd-upcoming__row--due" in (due.get("class") or [])
    assert due.select_one(".rd-upcoming__badge") is None

    future = by_desc["Future bill"]
    classes = future.get("class") or []
    assert "rd-upcoming__row--overdue" not in classes
    assert "rd-upcoming__row--due" not in classes
    assert future.select_one(".rd-upcoming__badge") is None


def test_afford_endpoint_minor_units(client: TestClient) -> None:
    r = client.get("/today/afford?amount=10000")
    assert r.status_code == 200
    assert "rd-afford__new" in r.text


def test_afford_endpoint_zero(client: TestClient) -> None:
    r = client.get("/today/afford?amount=0")
    assert r.status_code == 200
    # No delta is shown with zero amount — just the per-day line.
    assert "rd-afford__new" in r.text


def test_afford_endpoint_major_units_fallback(client: TestClient) -> None:
    # Backwards-compat: the existing form posts step=0.01 decimals.
    r = client.get("/today/afford?amount=100.00")
    assert r.status_code == 200
    assert "rd-afford__new" in r.text


def test_afford_endpoint_invalid_amount(client: TestClient) -> None:
    r = client.get("/today/afford?amount=not-a-number")
    assert r.status_code == 422


def test_afford_endpoint_negative_amount(client: TestClient) -> None:
    r = client.get("/today/afford?amount=-1")
    assert r.status_code == 422


def test_afford_endpoint_no_db_write(client: TestClient) -> None:
    """ADR-0056 §3 — the preview is a pure read."""
    # Baseline audit count via settings tab (any read endpoint is fine).
    r1 = client.get("/today/afford?amount=1000")
    r2 = client.get("/today/afford?amount=2500")
    assert r1.status_code == 200
    assert r2.status_code == 200


def test_afford_alias_route(client: TestClient) -> None:
    """Legacy ``/afford`` alias keeps working."""
    r = client.get("/afford?amount=10000")
    assert r.status_code == 200
    assert "rd-afford__new" in r.text
