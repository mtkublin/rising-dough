"""Today routes: status, window range, validation, read-only, auth (T-UT04b).

ADR-0106 section 1. Bodies are inspected only through the UI map; the upcoming
status comes from the row's ``data-status`` hook, not from class names.
"""

from __future__ import annotations

from datetime import date, timedelta

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
from tests.contract.conftest import covers
from tests.contract.web_helpers_t_ut04b import (
    OTHER_USER_ID,
    fetch_all,
    seed_other_user,
)
from tests.ui_map import _html, today

pytest_plugins = ["tests.contract.web_support_t_ut04b"]  # client, anon_client, raw_client

USER_ID = 1
AFFORD_PATHS = ["/today/afford"]  # bare /afford alias removed (T-Q257)


def _seed_planned(settings: Settings, user_id: int, offsets: dict[str, int]) -> dict[str, int]:
    """One planned expense per ``{description: days_from_today}``; returns ids."""
    conn = get_connection(settings)
    try:
        acc = accounts_repo.create(
            conn, user_id, NewAccount(name="Main", currency="PLN", opening_balance=0)
        ).id
        cat = categories_repo.create(
            conn, user_id, NewCategory(name="Rent", direction=Direction.EXPENSE)
        ).id
        base = date.today()  # noqa: DTZ011
        return {
            desc: planned_repo.create(
                conn,
                user_id,
                NewPlannedTransaction(
                    operation_date=base + timedelta(days=days),
                    category_id=cat,
                    account_id=acc,
                    amount=5000,
                    description=desc,
                ),
            ).id
            for desc, days in offsets.items()
        }
    finally:
        conn.close()


def _audit_count(settings: Settings) -> int:
    return len(fetch_all(settings, "SELECT id FROM audit_log"))


# --- GET /today ------------------------------------------------------------


@covers("GET /today")
def test_today_page_renders_hero_and_upcoming(client: TestClient) -> None:
    r = client.get("/today")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert _html.exists(r.text, today.heading)
    assert _html.exists(r.text, today.upcoming)
    assert _html.exists(r.text, today.afford_per_day)


@covers("GET /today")
def test_today_page_lists_upcoming_inside_the_default_window(
    client: TestClient, _migrated: Settings
) -> None:
    ids = _seed_planned(_migrated, USER_ID, {"Soon": 3})
    html = client.get("/today").text
    assert _html.exists(html, today.upcoming_planned(ids["Soon"]).inside(today.upcoming))


@covers("GET /today")
def test_today_page_is_read_only(client: TestClient, _migrated: Settings) -> None:
    before = _audit_count(_migrated)
    assert client.get("/today?window=7").status_code == 200
    assert _audit_count(_migrated) == before


@covers("GET /today")
def test_today_page_requires_login(anon_client: TestClient) -> None:
    r = anon_client.get("/today", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/auth/login?next=%2Ftoday"
    hx = anon_client.get("/today", headers={"HX-Request": "true"}, follow_redirects=False)
    assert hx.status_code == 401


# --- GET /today/upcoming ---------------------------------------------------


@covers("GET /today/upcoming")
def test_upcoming_empty_state(client: TestClient) -> None:
    r = client.get("/today/upcoming")
    assert r.status_code == 200
    assert _html.count(r.text, today.upcoming_rows) == 0


@covers("GET /today/upcoming")
def test_upcoming_row_status_overdue_due_future(client: TestClient, _migrated: Settings) -> None:
    ids = _seed_planned(_migrated, USER_ID, {"Past bill": -2, "Today bill": 0, "Future bill": 3})
    html = client.get("/today/upcoming").text
    status = {
        name: _html.resolve_one(html, today.upcoming_planned(pid))["data-status"]
        for name, pid in ids.items()
    }
    assert status == {"Past bill": "overdue", "Today bill": "due", "Future bill": "upcoming"}
    assert "Past bill" in _html.text_of(html, today.upcoming_planned(ids["Past bill"]))
    assert _html.exists(html, today.promote.inside(today.upcoming_planned(ids["Past bill"])))


@covers("GET /today/upcoming")
@pytest.mark.parametrize(
    ("window", "expected"),
    [
        ("7", {"Soon"}),
        ("30", {"Soon", "Later"}),
        ("all", {"Soon", "Later", "Far"}),
        ("bogus", {"Soon", "Later"}),  # unknown window falls back to the 30-day default
        (None, {"Soon", "Later"}),
    ],
)
def test_upcoming_window_range(
    client: TestClient, _migrated: Settings, window: str | None, expected: set[str]
) -> None:
    ids = _seed_planned(_migrated, USER_ID, {"Soon": 3, "Later": 20, "Far": 90})
    r = client.get("/today/upcoming", params={"window": window} if window else None)
    assert r.status_code == 200
    shown = {name for name, pid in ids.items() if _html.exists(r.text, today.upcoming_planned(pid))}
    assert shown == expected


@covers("GET /today/upcoming")
def test_upcoming_is_owner_scoped_and_read_only(client: TestClient, _migrated: Settings) -> None:
    seed_other_user(_migrated)
    theirs = _seed_planned(_migrated, OTHER_USER_ID, {"Theirs": 2})
    before = _audit_count(_migrated)
    r = client.get("/today/upcoming")
    assert not _html.exists(r.text, today.upcoming_planned(theirs["Theirs"]))
    assert _audit_count(_migrated) == before


@covers("GET /today/upcoming")
def test_upcoming_requires_login(anon_client: TestClient) -> None:
    r = anon_client.get("/today/upcoming", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login")


# --- GET /today/afford ---------------------------------------------------


@covers("GET /today/afford")
@pytest.mark.parametrize("path", AFFORD_PATHS)
@pytest.mark.parametrize("amount", ["10000", "100.00", "0", ""])
def test_afford_accepts_non_negative_amounts(client: TestClient, path: str, amount: str) -> None:
    r = client.get(path, params={"amount": amount})
    assert r.status_code == 200
    assert _html.exists(r.text, today.afford_per_day)
    # The signed per-day delta only shows for a positive amount.
    assert _html.exists(r.text, today.afford_delta) is (amount not in {"0", ""})


@covers("GET /today/afford")
@pytest.mark.parametrize("path", AFFORD_PATHS)
@pytest.mark.parametrize("amount", ["not-a-number", "-1"])
def test_afford_rejects_invalid_amount(client: TestClient, path: str, amount: str) -> None:
    r = client.get(path, params={"amount": amount})
    assert r.status_code == 422


@covers("GET /today/afford")
@pytest.mark.parametrize("path", AFFORD_PATHS)
def test_afford_is_a_pure_read(client: TestClient, _migrated: Settings, path: str) -> None:
    before = _audit_count(_migrated)
    assert client.get(path, params={"amount": "2500"}).status_code == 200
    assert _audit_count(_migrated) == before


@covers("GET /today/afford")
@pytest.mark.parametrize("path", AFFORD_PATHS)
def test_afford_requires_login(anon_client: TestClient, path: str) -> None:
    r = anon_client.get(path, params={"amount": "1"}, follow_redirects=False)
    assert r.status_code == 302
    hx = anon_client.get(path, params={"amount": "1"}, headers={"HX-Request": "true"})
    assert hx.status_code == 401
