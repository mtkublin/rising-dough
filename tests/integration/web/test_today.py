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


def test_afford_preview_without_amount_has_no_delta(client: TestClient) -> None:
    html = client.get("/today/afford?amount=0").text
    assert _html.exists(html, today.afford_per_day)
    assert not _html.exists(html, today.afford_delta)


def test_afford_delta_is_signed_per_day(client: TestClient) -> None:
    # Spending can only lower the per-day budget, so the delta is negative or zero.
    delta = _html.text_of(client.get("/afford?amount=100.00").text, today.afford_delta)
    assert delta.endswith("/ day")
    assert delta.startswith(("-", "+"))
