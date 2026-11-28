"""Contract tests: budget mutations and the override form (T-UT04d, ADR-0106 section 1).

Status, HX-* headers, CSRF, auth and DB / audit effects only; markup is read
through the UI map.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from budget_planner.domain.preferences import PREF_INCOME_ANCHOR_CATEGORY_ID
from budget_planner.repositories import (
    budgets as budgets_repo,
    preferences as preferences_repo,
)
from tests.contract.conftest import covers
from tests.contract.test_plan_support import USER_ID, audit_count, audit_total, hx_events
from tests.ui_map import _html, plan

pytest_plugins = ("tests.contract.test_plan_support",)

ALL_MUTATIONS = (
    ("/budget/defaults/{c}", {"amount": "10"}),
    ("/budget/one-off/{c}/2026/10", {"amount": "10"}),
    ("/budget/rules/{c}/overrides", {"tier": "default", "amount": "10"}),
    ("/budget/preferences/income-anchor", {"category_id": ""}),
)

# --- auth / CSRF (every mutating plan route) --------------------------------


@covers(
    "POST /budget/defaults/{category_id}",
    "POST /budget/one-off/{category_id}/{year}/{month}",
    "POST /budget/rules/{category_id}/overrides",
    "POST /budget/preferences/income-anchor",
)
@pytest.mark.parametrize(("path", "data"), ALL_MUTATIONS)
def test_mutations_require_csrf_token(
    raw_client: TestClient, db: sqlite3.Connection, cat_id: int, path: str, data: dict[str, str]
) -> None:
    before = audit_total(db)
    r = raw_client.post(path.format(c=cat_id), data=data)
    assert r.status_code == 403
    assert r.json() == {"detail": "missing_cookie"}
    assert audit_total(db) == before


@covers(
    "POST /budget/defaults/{category_id}",
    "POST /budget/one-off/{category_id}/{year}/{month}",
    "POST /budget/rules/{category_id}/overrides",
    "POST /budget/preferences/income-anchor",
)
@pytest.mark.parametrize(("path", "data"), ALL_MUTATIONS)
def test_mutations_require_a_session(
    anon_client: TestClient, db: sqlite3.Connection, cat_id: int, path: str, data: dict[str, str]
) -> None:
    before = audit_total(db)
    r = anon_client.post(path.format(c=cat_id), data=data, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login?next=")
    assert audit_total(db) == before


@covers("POST /budget/defaults/{category_id}")
def test_mutation_without_session_over_htmx_is_401_with_redirect(
    anon_client: TestClient, cat_id: int
) -> None:
    r = anon_client.post(
        f"/budget/defaults/{cat_id}",
        data={"amount": "1"},
        headers={"HX-Request": "true", "HX-Current-URL": "https://testserver/budget"},
    )
    assert r.status_code == 401
    assert r.headers["HX-Redirect"].startswith("/auth/login?next=")


# --- POST /budget/defaults/{category_id} -------------------------------------


@covers("POST /budget/defaults/{category_id}")
def test_set_default_writes_row_audits_and_signals_stale(
    client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    r = client.post(f"/budget/defaults/{cat_id}", data={"amount": "15.50"})
    assert r.status_code == 200
    assert "budget-stale" in hx_events(r.headers)
    row = budgets_repo.get_default(db, USER_ID, cat_id)
    assert row is not None
    assert row.amount == 1550
    assert audit_count(db, "budget_default") == 1


@covers("POST /budget/defaults/{category_id}")
def test_set_default_twice_updates_in_place(
    client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "100"})
    client.post(f"/budget/defaults/{cat_id}", data={"amount": "200"})
    row = budgets_repo.get_default(db, USER_ID, cat_id)
    assert row is not None
    assert row.amount == 20000
    assert audit_count(db, "budget_default") == 2


@covers("POST /budget/defaults/{category_id}")
@pytest.mark.parametrize(
    ("category", "amount", "status"),
    [("9999", "100", 404), ("{c}", "nan", 422), ("{c}", "-5", 422), ("{c}", "abc", 422)],
)
def test_set_default_rejects_bad_input_without_side_effects(
    client: TestClient,
    *,
    db: sqlite3.Connection,
    cat_id: int,
    category: str,
    amount: str,
    status: int,
) -> None:
    r = client.post(f"/budget/defaults/{category.format(c=cat_id)}", data={"amount": amount})
    assert r.status_code == status
    assert "HX-Trigger" not in r.headers
    assert budgets_repo.get_default(db, USER_ID, cat_id) is None
    assert audit_count(db, "budget_default") == 0


# --- POST /budget/one-off/{category_id}/{year}/{month} ------------------------


@covers("POST /budget/one-off/{category_id}/{year}/{month}")
def test_set_one_off_writes_override_and_audits(
    client: TestClient, db: sqlite3.Connection, cat_id: int
) -> None:
    r = client.post(f"/budget/one-off/{cat_id}/2026/10", data={"amount": "99"})
    assert r.status_code == 200
    assert "budget-stale" in hx_events(r.headers)
    assert audit_count(db, "budget_one_off_override") == 1


@covers("POST /budget/one-off/{category_id}/{year}/{month}")
@pytest.mark.parametrize(
    ("category", "month", "amount", "status"),
    [("9999", "10", "1", 404), ("{c}", "14", "1", 422), ("{c}", "10", "nope", 422)],
)
def test_set_one_off_rejects_bad_input(
    client: TestClient,
    *,
    db: sqlite3.Connection,
    cat_id: int,
    category: str,
    month: str,
    amount: str,
    status: int,
) -> None:
    r = client.post(
        f"/budget/one-off/{category.format(c=cat_id)}/2026/{month}", data={"amount": amount}
    )
    assert r.status_code == status
    assert audit_count(db, "budget_one_off_override") == 0


# --- POST /budget/rules/{category_id}/overrides -------------------------------


@covers("POST /budget/rules/{category_id}/overrides")
@pytest.mark.parametrize(
    ("form", "entity"),
    [
        ({"tier": "recurring", "month": "6", "amount": "250"}, "budget_recurring_override"),
        (
            {"tier": "one-off", "month": "7", "year": "2026", "amount": "99"},
            "budget_one_off_override",
        ),
        ({"tier": "default", "amount": "75"}, "budget_default"),
    ],
)
def test_create_override_dispatches_by_tier(
    client: TestClient, db: sqlite3.Connection, cat_id: int, form: dict[str, str], entity: str
) -> None:
    r = client.post(f"/budget/rules/{cat_id}/overrides", data=form)
    assert r.status_code == 200
    assert "budget-stale" in hx_events(r.headers)
    assert audit_count(db, entity) == 1


@covers("POST /budget/rules/{category_id}/overrides")
@pytest.mark.parametrize(
    ("category", "form", "status"),
    [
        ("9999", {"tier": "recurring", "month": "6", "amount": "1"}, 404),
        ("{c}", {"tier": "monthly", "month": "6", "amount": "1"}, 422),
        ("{c}", {"tier": "recurring", "month": "13", "amount": "1"}, 422),
        ("{c}", {"tier": "recurring", "month": "6", "amount": "nope"}, 422),
        ("{c}", {"tier": "one-off", "month": "7", "year": "bogus", "amount": "1"}, 422),
    ],
)
def test_create_override_rejects_bad_input(
    client: TestClient,
    *,
    db: sqlite3.Connection,
    cat_id: int,
    category: str,
    form: dict[str, str],
    status: int,
) -> None:
    before = audit_total(db)
    r = client.post(f"/budget/rules/{category.format(c=cat_id)}/overrides", data=form)
    assert r.status_code == status
    assert "HX-Trigger" not in r.headers
    assert audit_total(db) == before


# --- POST /budget/preferences/income-anchor -----------------------------------


@covers("POST /budget/preferences/income-anchor")
def test_income_anchor_set_then_clear(
    client: TestClient, db: sqlite3.Connection, income_cat_id: int
) -> None:
    r = client.post("/budget/preferences/income-anchor", data={"category_id": str(income_cat_id)})
    assert r.status_code == 200
    assert "budget-stale" in hx_events(r.headers)
    row = preferences_repo.get(db, USER_ID, PREF_INCOME_ANCHOR_CATEGORY_ID)
    assert row is not None
    assert row.value == str(income_cat_id)

    r = client.post("/budget/preferences/income-anchor", data={"category_id": ""})
    assert r.status_code == 200
    assert "budget-stale" in hx_events(r.headers)
    assert preferences_repo.get(db, USER_ID, PREF_INCOME_ANCHOR_CATEGORY_ID) is None


@covers("POST /budget/preferences/income-anchor")
@pytest.mark.parametrize("value", ["{expense}", "9999", "abc"])
def test_income_anchor_rejects_invalid_category(
    client: TestClient, db: sqlite3.Connection, cat_id: int, value: str
) -> None:
    r = client.post(
        "/budget/preferences/income-anchor", data={"category_id": value.format(expense=cat_id)}
    )
    assert r.status_code == 422
    assert "HX-Trigger" not in r.headers
    assert preferences_repo.get(db, USER_ID, PREF_INCOME_ANCHOR_CATEGORY_ID) is None


# --- GET /budget/rules/{category_id}/overrides/new ----------------------------


@covers("GET /budget/rules/{category_id}/overrides/new")
def test_override_form_is_a_dialog_fragment_with_cancel(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/budget/rules/{cat_id}/overrides/new?year=2026&month=3")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert _html.count(r.text, plan.override_tier) == 3
    assert _html.exists(r.text, plan.override_amount)
    assert _html.exists(r.text, plan.override_save)
    assert _html.exists(r.text, plan.override_cancel)
    assert not _html.exists(r.text, plan.heading)  # fragment, not a page


@covers("GET /budget/rules/{category_id}/overrides/new")
def test_override_form_opens_in_the_modal_root(client: TestClient, cat_id: int) -> None:
    r = client.get(f"/budget/rules/{cat_id}/overrides/new?year=2026&month=3")
    assert r.status_code == 200
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert r.headers["HX-Reswap"] == "innerHTML"


@covers("GET /budget/rules/{category_id}/overrides/new")
def test_override_form_unknown_category_is_404(client: TestClient) -> None:
    assert client.get("/budget/rules/9999/overrides/new").status_code == 404


@covers("GET /budget/rules/{category_id}/overrides/new")
def test_override_form_requires_a_session(anon_client: TestClient, cat_id: int) -> None:
    r = anon_client.get(f"/budget/rules/{cat_id}/overrides/new", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login?next=")
