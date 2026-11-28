"""T-Q219 (Q-014): value-asserting tests for branches the `...` coverage exclusion used to hide.

Covers router validation and error branches that were invisible while the coverage
``exclude_lines`` entry matched every line containing an ellipsis.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.domain.transactions import NewTransaction, TransactionFilter
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    snapshots as snapshots_repo,
    transactions as transactions_repo,
)
from tests.ui_map import _html
from tests.ui_map.locator import by_id

USER_ID = 1
MISSING = 99_999


@pytest.fixture
def ctx(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(conn, USER_ID, NewAccount(name="Main", currency="PLN"))
        other = accounts_repo.create(conn, USER_ID, NewAccount(name="Other", currency="PLN"))
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
        )
        transit = categories_repo.create(
            conn, USER_ID, NewCategory(name="Move", direction=Direction.TRANSIT)
        )
        pl = planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=date(2026, 10, 15),
                category_id=cat.id,
                account_id=acc.id,
                amount=50000,
            ),
        )
        txn = transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=date(2026, 10, 15),
                category_id=cat.id,
                account_id=acc.id,
                amount=5000,
            ),
        )
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 1, 1),
                category_id=cat.id,
                account_id=acc.id,
                default_amount=50000,
            ),
        )
        return {
            "acc": acc.id,
            "other": other.id,
            "cat": cat.id,
            "transit": transit.id,
            "planned": pl.id,
            "txn": txn.id,
            "rule": rule.id,
        }
    finally:
        conn.close()


def _txn_form(ctx: dict[str, int], **over: object) -> dict[str, object]:
    form: dict[str, object] = {
        "operation_date": "2026-10-20",
        "category_id": ctx["cat"],
        "account_id": ctx["acc"],
        "amount": "12.34",
    }
    form.update(over)
    return form


def _txn_count(settings: Settings) -> int:
    conn = get_connection(settings)
    try:
        return len(transactions_repo.list_filtered(conn, USER_ID, TransactionFilter()))
    finally:
        conn.close()


# --- transactions router -------------------------------------------------


def test_create_transit_non_numeric_destination_is_422(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    before = _txn_count(_migrated)
    r = client.post(
        "/transactions",
        data=_txn_form(ctx, category_id=ctx["transit"], dest_account_id="abc"),
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-dest_account_id-error": "▲ invalid destination",
    }
    assert _txn_count(_migrated) == before


def test_create_transit_unknown_destination_is_422(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    before = _txn_count(_migrated)
    r = client.post(
        "/transactions",
        data=_txn_form(ctx, category_id=ctx["transit"], dest_account_id=str(MISSING)),
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-dest_account_id-error": "▲ unknown destination",
    }
    assert _txn_count(_migrated) == before


def test_create_transit_valid_destination_is_stored(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    r = client.post(
        "/transactions",
        data=_txn_form(ctx, category_id=ctx["transit"], dest_account_id=str(ctx["other"])),
    )
    assert r.status_code in (200, 204)
    conn = get_connection(_migrated)
    try:
        rows = [
            t
            for t in transactions_repo.list_filtered(conn, USER_ID, TransactionFilter())
            if t.category_id == ctx["transit"]
        ]
    finally:
        conn.close()
    assert [(t.amount, t.account_id, t.dest_account_id) for t in rows] == [
        (1234, ctx["acc"], ctx["other"])
    ]


def test_edit_transaction_unknown_account_is_422_and_row_unchanged(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    r = client.post(
        f"/transactions/{ctx['txn']}",
        data=_txn_form(ctx, account_id=MISSING),
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-account_id-error": "▲ unknown account",
    }
    conn = get_connection(_migrated)
    try:
        row = transactions_repo.find_by_id(conn, USER_ID, ctx["txn"])
    finally:
        conn.close()
    assert row is not None
    assert (row.account_id, row.amount) == (ctx["acc"], 5000)


# --- planned router ------------------------------------------------------


def _planned_form(ctx: dict[str, int], **over: object) -> dict[str, object]:
    form: dict[str, object] = {
        "operation_date": "2026-11-01",
        "category_id": ctx["cat"],
        "account_id": ctx["acc"],
        "amount": "10.00",
    }
    form.update(over)
    return form


def _planned_count(settings: Settings) -> int:
    conn = get_connection(settings)
    try:
        row = conn.execute("SELECT COUNT(*) FROM planned_transactions").fetchone()
        return int(row[0])
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("over", "line_id", "message"),
    [
        ({"category_id": MISSING}, "catpick-new-entry-error", "unknown category"),
        ({"dest_account_id": "abc"}, "field-dest_account_id-error", "invalid dest account"),
        ({"dest_account_id": str(MISSING)}, "field-dest_account_id-error", "unknown dest account"),
    ],
)
def test_create_planned_validation_errors_are_422(
    client: TestClient,
    ctx: dict[str, int],
    _migrated: Settings,
    over: dict[str, object],
    line_id: str,
    message: str,
) -> None:
    before = _planned_count(_migrated)
    r = client.post("/planned", data=_planned_form(ctx, **over))
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {line_id: f"▲ {message}"}
    assert _planned_count(_migrated) == before


def test_edit_planned_unknown_account_is_422(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/planned/{ctx['planned']}",
        data=_planned_form(ctx, account_id=MISSING),
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-account_id-error": "▲ unknown account",
    }


# --- recurring router ----------------------------------------------------


def test_override_month_before_rule_start_is_422_with_message(
    client: TestClient, ctx: dict[str, int]
) -> None:
    r = client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": 2025, "month": 6, "amount": "10.00"},
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-month-error": "▲ rule has no occurrence in 2025-06",
    }


# --- categories router ---------------------------------------------------


def test_update_category_rejects_bad_color_and_keeps_name(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    r = client.post(f"/categories/{ctx['cat']}", data={"name": "Renamed", "color": "not-a-color"})
    assert r.status_code == 422
    conn = get_connection(_migrated)
    try:
        cat = categories_repo.find_by_id(conn, USER_ID, ctx["cat"])
    finally:
        conn.close()
    assert cat is not None
    assert cat.name == "Rent"


# --- accounts router -----------------------------------------------------


def test_reconcile_ignores_a_posted_category_and_saves_a_snapshot(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    r = client.post(
        f"/accounts/{ctx['acc']}/reconcile",
        data={"actual_balance": "100.00", "category_id": "abc", "save_snapshot": "1"},
    )
    assert r.status_code == 200
    conn = get_connection(_migrated)
    try:
        snaps = snapshots_repo.list_for_account(conn, USER_ID, ctx["acc"])
    finally:
        conn.close()
    assert [s.balance for s in snaps] == [10_000]
    assert [s.note for s in snaps] == ["reconcile snapshot"]


def test_update_account_blank_name_rerenders_form_with_error(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    r = client.post(f"/accounts/{ctx['acc']}", data={"name": "   ", "currency": "PLN"})
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-name-error": "▲ Name is required",
    }
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.find_by_id(conn, USER_ID, ctx["acc"])
    finally:
        conn.close()
    assert acc is not None
    assert acc.name == "Main"


# --- budget router -------------------------------------------------------


def test_override_default_tier_sets_default_and_emits_trigger(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    r = client.post(
        f"/budget/rules/{ctx['cat']}/overrides",
        data={"tier": "default", "amount": "250.00"},
    )
    assert r.status_code == 200
    assert "Rent budget saved" in _html.all_text(r.text, by_id("flash-region"))
    assert "budget-stale" in r.headers["HX-Trigger"]
    conn = get_connection(_migrated)
    try:
        default = budgets_repo.get_default(conn, USER_ID, ctx["cat"])
    finally:
        conn.close()
    assert default is not None
    assert default.amount == 25_000


def test_override_non_numeric_month_is_422(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/budget/rules/{ctx['cat']}/overrides",
        data={"tier": "one-off", "month": "x", "year": "2026", "amount": "1.00"},
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "dialog-error-month": "▲ Month: pick a month from 1 to 12",
    }
