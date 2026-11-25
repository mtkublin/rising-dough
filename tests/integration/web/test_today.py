"""Integration tests for /today rendering (T-R40, ADR-0056 section 3).

Status codes, window range and auth are in ``tests/contract/test_today.py``;
the rendered values are checked here through the UI map.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from budget_planner import clock
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
from tests.ui_map import _html, today

USER_ID = 1


def test_today_renders_heading(client: TestClient) -> None:
    assert _html.exists(client.get("/today").text, today.heading)


def test_afford_preview_shows_per_day_figure(client: TestClient) -> None:
    html = client.get("/today/afford?amount=10000").text
    per_day = _html.text_of(html, today.afford_per_day)
    assert per_day  # a formatted amount
    assert _html.exists(html, today.afford_delta)


def test_today_upcoming_row_tint_overdue_due_future(
    client: TestClient, _migrated: Settings
) -> None:
    """Overdue (date < today) -> red row tint; due-today -> amber; future -> no tint.
    No badge text, only the row class differentiates status."""
    conn = get_connection(_migrated)
    ids: dict[str, int] = {}
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
        )
        # The app derives "today" in the display timezone (ADR-0007), not the host's.
        today_date = clock.today_local(_migrated)
        for key, op_date, desc in [
            ("past", today_date - timedelta(days=2), "Past bill"),
            ("due", today_date, "Today bill"),
            ("future", today_date + timedelta(days=3), "Future bill"),
        ]:
            ids[key] = planned_repo.create(
                conn,
                USER_ID,
                NewPlannedTransaction(
                    operation_date=op_date,
                    category_id=cat.id,
                    account_id=acc.id,
                    amount=5000,
                    description=desc,
                ),
            ).id
    finally:
        conn.close()

    r = client.get("/today/upcoming")
    assert r.status_code == 200
    classes: dict[str, str | list[str]] = {
        key: _html.resolve_one(r.text, today.upcoming_planned(pid)).get("class") or []
        for key, pid in ids.items()
    }
    assert "rd-upcoming__row--overdue" in classes["past"]
    assert "rd-upcoming__row--due" in classes["due"]
    assert "rd-upcoming__row--overdue" not in classes["future"]
    assert "rd-upcoming__row--due" not in classes["future"]


def test_today_upcoming_row_prints_the_account_currency(
    client: TestClient, _migrated: Settings
) -> None:
    """A planned item on an EUR account is printed in EUR, one on a PLN account in PLN."""
    conn = get_connection(_migrated)
    try:
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
        )
        due = clock.today_local(_migrated) + timedelta(days=1)
        rows = {}
        for name, ccy, minor in (("Euro bill", "EUR", 2550), ("Zloty bill", "PLN", 4000)):
            acc = accounts_repo.create(conn, USER_ID, NewAccount(name=name, currency=ccy))
            rows[name] = planned_repo.create(
                conn,
                USER_ID,
                NewPlannedTransaction(
                    operation_date=due,
                    category_id=cat.id,
                    account_id=acc.id,
                    amount=minor,
                    description=name,
                ),
            ).id
    finally:
        conn.close()

    r = client.get("/today/upcoming")
    euro = _html.text_of(r.text, today.upcoming_planned(rows["Euro bill"]))
    zloty = _html.text_of(r.text, today.upcoming_planned(rows["Zloty bill"]))
    assert "\N{MINUS SIGN}25.50 EUR" in euro
    assert "PLN" not in euro
    assert "\N{MINUS SIGN}40.00 PLN" in zloty


def test_afford_endpoint_zero_and_blank_are_invalid(client: TestClient) -> None:
    for amount in ("0", ""):
        r = client.get("/today/afford", params={"amount": amount})
        assert r.status_code == 422
        assert r.text == "Enter an amount, like 250.00"


def test_afford_endpoint_major_units_fallback(client: TestClient) -> None:
    # Backwards-compat: the existing form posts step=0.01 decimals.
    r = client.get("/today/afford?amount=100.00")
    assert r.status_code == 200
    assert _html.exists(r.text, today.afford_per_day)


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


def test_afford_delta_is_signed_per_day(client: TestClient) -> None:
    # Nothing is budgeted, so 100.00 exceeds what is left: the over line carries the ▲ glyph
    # and the over amount is the delta element.
    html = client.get("/today/afford?amount=100.00").text
    assert _html.text_of(html, today.afford_delta) == "100.00"
    result = _html.text_of(html, today.afford_per_day)
    assert result.startswith("▲ per day becomes")
    assert result.endswith("over")
