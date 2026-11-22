"""Accounts routes: status, headers, CSRF, auth, ownership, DB and audit effect (T-UT04b).

ADR-0106 section 1. Bodies are inspected only through the UI map.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from tests.contract.conftest import covers
from tests.contract.web_helpers_t_ut04b import (
    OTHER_USER_ID,
    audit_ops,
    fetch_all,
    field,
    seed_other_user,
)
from tests.ui_map import _html, accounts

pytest_plugins = ["tests.contract.web_support_t_ut04b"]  # client, anon_client, raw_client

USER_ID = 1
HX = {"HX-Request": "true"}
LOGIN_NEXT_ACCOUNTS = "/auth/login?next=%2Faccounts"
NEW_ACCOUNT = {"name": "Travel", "currency": "EUR", "opening_balance": "100.00"}


def _make_account(
    settings: Settings,
    *,
    user_id: int = USER_ID,
    name: str = "Main",
    currency: str = "PLN",
    opening: int = 0,
    liability: bool = False,
    limit: int | None = None,
) -> int:
    conn = get_connection(settings)
    try:
        return accounts_repo.create(
            conn,
            user_id,
            NewAccount(
                name=name,
                currency=currency,
                opening_balance=opening,
                is_liability=liability,
                credit_limit_minor=limit,
            ),
        ).id
    finally:
        conn.close()


def _account_rows(settings: Settings) -> list[dict[str, Any]]:
    return fetch_all(settings, "SELECT * FROM accounts ORDER BY id")


def _balance_txns(settings: Settings, account_id: int) -> list[dict[str, Any]]:
    return fetch_all(
        settings, "SELECT amount FROM transactions WHERE account_id = ?", (account_id,)
    )


@pytest.fixture
def acc_id(_migrated: Settings) -> int:
    return _make_account(_migrated)


@pytest.fixture
def foreign_id(_migrated: Settings) -> int:
    seed_other_user(_migrated)
    return _make_account(_migrated, user_id=OTHER_USER_ID, name="Theirs")


# --- GET /accounts ---------------------------------------------------------


@covers("GET /accounts")
def test_index_lists_rows_hero_and_planned_total(client: TestClient, acc_id: int) -> None:
    r = client.get("/accounts")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert _html.exists(r.text, accounts.heading)
    assert _html.exists(r.text, accounts.new_account_button)
    assert _html.exists(r.text, accounts.row(acc_id))
    assert _html.exists(r.text, accounts.planned_total)


@covers("GET /accounts")
def test_index_hides_other_users_accounts_and_soft_deleted(
    client: TestClient, acc_id: int, foreign_id: int, _migrated: Settings
) -> None:
    gone = _make_account(_migrated, name="Gone")
    conn = get_connection(_migrated)
    try:
        accounts_repo.soft_delete(conn, USER_ID, gone)
    finally:
        conn.close()
    html = client.get("/accounts").text
    assert _html.exists(html, accounts.row(acc_id))
    assert not _html.exists(html, accounts.row(foreign_id))
    assert not _html.exists(html, accounts.row(gone))


@covers("GET /accounts")
def test_index_requires_login(anon_client: TestClient) -> None:
    r = anon_client.get("/accounts", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == LOGIN_NEXT_ACCOUNTS
    hx = anon_client.get("/accounts", headers=HX, follow_redirects=False)
    assert hx.status_code == 401
    assert hx.headers["HX-Redirect"].startswith("/auth/login?next=")


# --- GET /accounts/last-checked --------------------------------------------


# --- GET /accounts/new -----------------------------------------------------


@covers("GET /accounts/new")
def test_new_form_is_slideover_with_hidden_credit_limit(client: TestClient) -> None:
    r = client.get("/accounts/new")
    assert r.status_code == 200
    assert _html.exists(r.text, accounts.account_form)
    assert _html.exists(r.text, accounts.form_name)
    assert _html.exists(r.text, accounts.form_currency)
    limit = field(r.text, accounts.form_credit_limit)
    assert limit.has_attr("disabled")
    assert limit.find_parent("label").has_attr("hidden")  # type: ignore[union-attr]
    # The create form swaps itself, not the list.
    assert _html.resolve_one(r.text, accounts.account_form)["hx-target"] == "#account-form"


@covers("GET /accounts/new")
def test_new_form_requires_login(anon_client: TestClient) -> None:
    r = anon_client.get("/accounts/new", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login")


# --- POST /accounts --------------------------------------------------------


@covers("POST /accounts")
def test_create_persists_audits_and_reloads_page(client: TestClient, _migrated: Settings) -> None:
    r = client.post("/accounts", data=NEW_ACCOUNT, headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert json.loads(r.headers["HX-Trigger"]) == {"balance-stale": True}
    assert r.headers["HX-Reswap"] == "none"
    assert r.headers["HX-Refresh"] == "true"
    rows = _account_rows(_migrated)
    assert len(rows) == 1
    assert (rows[0]["name"], rows[0]["currency"], rows[0]["user_id"]) == ("Travel", "EUR", USER_ID)
    assert "Travel" in _html.text_of(r.text, accounts.row(int(rows[0]["id"])))
    assert audit_ops(_migrated, "account") == [("create", rows[0]["id"])]
    assert len(_balance_txns(_migrated, int(rows[0]["id"]))) == 0


@covers("POST /accounts")
def test_create_credit_card_stores_limit_and_shows_it(
    client: TestClient, _migrated: Settings
) -> None:
    r = client.post(
        "/accounts",
        data={
            "name": "Visa",
            "currency": "PLN",
            "is_liability": "on",
            "credit_limit": "10000.00",
        },
    )
    assert r.status_code == 200
    row = _account_rows(_migrated)[0]
    assert row["is_liability"] == 1
    assert row["credit_limit_minor"] == 1_000_000
    text = _html.text_of(r.text, accounts.row(int(row["id"])))
    assert "credit card" in text.lower()
    assert "10,000.00" in text


@covers("POST /accounts")
@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"name": "X", "currency": "EURO"}, "currency"),
        ({"name": "   ", "currency": "PLN"}, "name"),
        ({"name": "A", "currency": "PLN", "opening_balance": "nan!"}, "opening_balance"),
        (
            {"name": "V", "currency": "PLN", "is_liability": "on", "credit_limit": ""},
            "credit_limit",
        ),
        (
            {"name": "V", "currency": "PLN", "is_liability": "on", "credit_limit": "0"},
            "credit_limit",
        ),
    ],
)
def test_create_validation_errors_are_422_and_write_nothing(
    client: TestClient, _migrated: Settings, data: dict[str, str], field: str
) -> None:
    r = client.post("/accounts", data=data)
    assert r.status_code == 422
    assert field in _html.text_of(r.text, accounts.form_errors)
    assert _account_rows(_migrated) == []
    assert audit_ops(_migrated, "account") == []
    assert "HX-Refresh" not in r.headers


@covers("POST /accounts")
def test_create_missing_required_field_is_422(client: TestClient, _migrated: Settings) -> None:
    assert client.post("/accounts", data={"currency": "PLN"}).status_code == 422
    assert _account_rows(_migrated) == []


@covers("POST /accounts")
def test_create_enforces_csrf(raw_client: TestClient, _migrated: Settings) -> None:
    r = raw_client.post("/accounts", data=NEW_ACCOUNT)
    assert r.status_code == 403
    assert _account_rows(_migrated) == []


@covers("POST /accounts")
def test_create_requires_login(anon_client: TestClient, _migrated: Settings) -> None:
    r = anon_client.post("/accounts", data=NEW_ACCOUNT, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login")
    assert _account_rows(_migrated) == []


# --- GET /accounts/{account_id}/edit ---------------------------------------


@covers("GET /accounts/{account_id}/edit")
def test_edit_form_asset_has_credit_limit_disabled(client: TestClient, acc_id: int) -> None:
    r = client.get(f"/accounts/{acc_id}/edit")
    assert r.status_code == 200
    assert field(r.text, accounts.form_name)["value"] == "Main"
    limit = field(r.text, accounts.form_credit_limit)
    assert limit.has_attr("disabled")
    assert limit.find_parent("label").has_attr("hidden")  # type: ignore[union-attr]


@covers("GET /accounts/{account_id}/edit")
def test_edit_form_liability_shows_credit_limit(client: TestClient, _migrated: Settings) -> None:
    visa = _make_account(_migrated, liability=True, limit=1_000_000, name="Visa")
    r = client.get(f"/accounts/{visa}/edit")
    assert r.status_code == 200
    limit = field(r.text, accounts.form_credit_limit)
    assert not limit.has_attr("disabled")
    assert not limit.find_parent("label").has_attr("hidden")  # type: ignore[union-attr]
    assert limit["value"] == "10000.00"


@covers("GET /accounts/{account_id}/edit")
def test_edit_form_missing_or_foreign_is_404(client: TestClient, foreign_id: int) -> None:
    assert client.get("/accounts/9999/edit").status_code == 404
    assert client.get(f"/accounts/{foreign_id}/edit").status_code == 404


@covers("GET /accounts/{account_id}/edit")
def test_edit_form_requires_login(anon_client: TestClient, acc_id: int) -> None:
    r = anon_client.get(f"/accounts/{acc_id}/edit", follow_redirects=False)
    assert r.status_code == 302


# --- POST /accounts/{account_id} -------------------------------------------


@covers("POST /accounts/{account_id}")
def test_update_renames_and_audits(client: TestClient, acc_id: int, _migrated: Settings) -> None:
    r = client.post(f"/accounts/{acc_id}", data={"name": "Renamed", "type": "checking"})
    assert r.status_code == 200
    assert json.loads(r.headers["HX-Trigger"]) == {"balance-stale": True}
    assert "Renamed" in _html.text_of(r.text, accounts.row(acc_id))
    row = _account_rows(_migrated)[0]
    assert (row["name"], row["type"]) == ("Renamed", "checking")
    assert row["currency"] == "PLN"  # currency is immutable
    assert audit_ops(_migrated, "account") == [("create", acc_id), ("update", acc_id)]


@covers("POST /accounts/{account_id}")
def test_update_asset_to_credit_card_sets_limit(
    client: TestClient, acc_id: int, _migrated: Settings
) -> None:
    r = client.post(
        f"/accounts/{acc_id}",
        data={
            "name": "Visa",
            "type": "credit_card",
            "is_liability": "on",
            "credit_limit": "5000.00",
        },
    )
    assert r.status_code == 200
    assert "5,000.00" in _html.text_of(r.text, accounts.row(acc_id))
    row = _account_rows(_migrated)[0]
    assert (row["is_liability"], row["credit_limit_minor"]) == (1, 500_000)


@covers("POST /accounts/{account_id}")
def test_update_credit_card_to_asset_clears_limit(client: TestClient, _migrated: Settings) -> None:
    visa = _make_account(_migrated, liability=True, limit=1_000_000, name="Visa")
    r = client.post(f"/accounts/{visa}", data={"name": "Visa", "type": "", "credit_limit": ""})
    assert r.status_code == 200
    row = _account_rows(_migrated)[0]
    assert (row["is_liability"], row["credit_limit_minor"]) == (0, None)


@covers("POST /accounts/{account_id}")
def test_update_validation_errors_are_422_and_change_nothing(
    client: TestClient, acc_id: int, _migrated: Settings
) -> None:
    blank = client.post(f"/accounts/{acc_id}", data={"name": "   "})
    assert blank.status_code == 422
    no_limit = client.post(
        f"/accounts/{acc_id}", data={"name": "V", "is_liability": "on", "credit_limit": ""}
    )
    assert no_limit.status_code == 422
    assert "credit_limit" in _html.text_of(no_limit.text, accounts.form_errors)
    assert _account_rows(_migrated)[0]["name"] == "Main"
    assert audit_ops(_migrated, "account") == [("create", acc_id)]


@covers("POST /accounts/{account_id}")
def test_update_missing_or_foreign_is_404(
    client: TestClient, foreign_id: int, _migrated: Settings
) -> None:
    assert client.post("/accounts/9999", data={"name": "X"}).status_code == 404
    assert client.post(f"/accounts/{foreign_id}", data={"name": "X"}).status_code == 404
    names = {r["name"] for r in _account_rows(_migrated)}
    assert names == {"Theirs"}


@covers("POST /accounts/{account_id}")
def test_update_enforces_csrf_and_login(
    raw_client: TestClient, anon_client: TestClient, acc_id: int, _migrated: Settings
) -> None:
    assert raw_client.post(f"/accounts/{acc_id}", data={"name": "Hacked"}).status_code == 403
    r = anon_client.post(f"/accounts/{acc_id}", data={"name": "Hacked"}, follow_redirects=False)
    assert r.status_code == 302
    assert _account_rows(_migrated)[0]["name"] == "Main"


# --- POST /accounts/{account_id}/delete ------------------------------------


@covers("POST /accounts/{account_id}/delete")
def test_delete_soft_deletes_with_toast_and_audit(
    client: TestClient, acc_id: int, _migrated: Settings
) -> None:
    r = client.post(f"/accounts/{acc_id}/delete")
    assert r.status_code == 200
    assert r.text == ""
    assert json.loads(r.headers["HX-Trigger"]) == {
        "balance-stale": True,
        "forecast-stale": True,
        "toast": {"variant": "success", "message": "Account deleted"},
    }
    row = _account_rows(_migrated)[0]
    assert row["deleted_at"] is not None
    assert audit_ops(_migrated, "account") == [("create", acc_id), ("delete", acc_id)]
    assert not _html.exists(client.get("/accounts").text, accounts.row(acc_id))


@covers("POST /accounts/{account_id}/delete")
def test_delete_unknown_or_foreign_is_a_noop(
    client: TestClient, foreign_id: int, _migrated: Settings
) -> None:
    before = audit_ops(_migrated, "account")
    assert client.post("/accounts/9999/delete").status_code == 200
    assert client.post(f"/accounts/{foreign_id}/delete").status_code == 200
    assert _account_rows(_migrated)[0]["deleted_at"] is None
    assert audit_ops(_migrated, "account") == before


@covers("POST /accounts/{account_id}/delete")
def test_delete_enforces_csrf_and_login(
    raw_client: TestClient, anon_client: TestClient, acc_id: int, _migrated: Settings
) -> None:
    assert raw_client.post(f"/accounts/{acc_id}/delete").status_code == 403
    r = anon_client.post(f"/accounts/{acc_id}/delete", follow_redirects=False)
    assert r.status_code == 302
    assert _account_rows(_migrated)[0]["deleted_at"] is None


# --- POST /accounts/{account_id}/snapshot ----------------------------------


@covers("POST /accounts/{account_id}/snapshot")
def test_snapshot_records_current_balance(
    client: TestClient, acc_id: int, _migrated: Settings
) -> None:
    conn = get_connection(_migrated)
    try:
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="X", direction=Direction.EXPENSE)
        )
        transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=date(2026, 10, 1),
                category_id=cat.id,
                account_id=acc_id,
                amount=1000,
            ),
        )
    finally:
        conn.close()
    r = client.post(f"/accounts/{acc_id}/snapshot")
    assert r.status_code == 200
    assert _html.exists(r.text, accounts.snapshot_item)
    assert json.loads(r.headers["HX-Trigger"]) == {
        "toast": {"variant": "success", "message": "Snapshot saved"}
    }
    snaps = fetch_all(_migrated, "SELECT account_id, balance, note FROM account_snapshots")
    assert snaps == [{"account_id": acc_id, "balance": -1000, "note": "user snapshot"}]
    assert [op for op, _ in audit_ops(_migrated, "snapshot")] == ["create"]


@covers("POST /accounts/{account_id}/snapshot")
def test_snapshot_missing_or_foreign_is_404(
    client: TestClient, foreign_id: int, _migrated: Settings
) -> None:
    assert client.post("/accounts/9999/snapshot").status_code == 404
    assert client.post(f"/accounts/{foreign_id}/snapshot").status_code == 404
    assert fetch_all(_migrated, "SELECT id FROM account_snapshots") == []


@covers("POST /accounts/{account_id}/snapshot")
def test_snapshot_enforces_csrf_and_login(
    raw_client: TestClient, anon_client: TestClient, acc_id: int, _migrated: Settings
) -> None:
    assert raw_client.post(f"/accounts/{acc_id}/snapshot").status_code == 403
    r = anon_client.post(f"/accounts/{acc_id}/snapshot", follow_redirects=False)
    assert r.status_code == 302
    assert fetch_all(_migrated, "SELECT id FROM account_snapshots") == []


# --- GET /accounts/{account_id}/reconcile ----------------------------------


@covers("GET /accounts/{account_id}/reconcile")
def test_reconcile_form_asset_asks_for_balance(client: TestClient, acc_id: int) -> None:
    r = client.get(f"/accounts/{acc_id}/reconcile")
    assert r.status_code == 200
    assert _html.exists(r.text, accounts.reconcile_dialog)
    assert _html.exists(r.text, accounts.reconcile_actual)
    assert not _html.exists(r.text, accounts.reconcile_available)


@covers("GET /accounts/{account_id}/reconcile")
def test_reconcile_form_liability_with_limit_asks_available(
    client: TestClient, _migrated: Settings
) -> None:
    card = _make_account(_migrated, liability=True, limit=500_000, opening=-123_456, name="Visa")
    r = client.get(f"/accounts/{card}/reconcile")
    assert r.status_code == 200
    assert field(r.text, accounts.reconcile_available)["value"] == "3765.44"
    help_text = _html.text_of(r.text, accounts.reconcile_available_help)
    assert "Limit 5,000.00" in help_text
    assert "1,234.56" in help_text


@covers("GET /accounts/{account_id}/reconcile")
def test_reconcile_form_liability_without_limit_asks_balance(
    client: TestClient, _migrated: Settings
) -> None:
    card = _make_account(_migrated, liability=True, limit=None, opening=-100, name="Loan")
    r = client.get(f"/accounts/{card}/reconcile")
    assert not _html.exists(r.text, accounts.reconcile_available)
    assert _html.exists(r.text, accounts.reconcile_actual)


@covers("GET /accounts/{account_id}/reconcile")
def test_reconcile_form_missing_or_foreign_is_404(client: TestClient, foreign_id: int) -> None:
    assert client.get("/accounts/9999/reconcile").status_code == 404
    assert client.get(f"/accounts/{foreign_id}/reconcile").status_code == 404


@covers("GET /accounts/{account_id}/reconcile")
def test_reconcile_form_requires_login(anon_client: TestClient, acc_id: int) -> None:
    r = anon_client.get(f"/accounts/{acc_id}/reconcile", follow_redirects=False)
    assert r.status_code == 302


# --- POST /accounts/{account_id}/reconcile ---------------------------------


def _adjustments(settings: Settings, account_id: int) -> list[int]:
    rows = fetch_all(
        settings,
        "SELECT t.amount FROM transactions t JOIN categories c ON c.id = t.category_id "
        "WHERE t.account_id = ? AND c.direction = 'adjustment'",
        (account_id,),
    )
    return [int(r["amount"]) for r in rows]


@covers("POST /accounts/{account_id}/reconcile")
def test_reconcile_records_signed_adjustment_and_row(
    client: TestClient, acc_id: int, _migrated: Settings
) -> None:
    r = client.post(f"/accounts/{acc_id}/reconcile", data={"actual_balance": "123.45"})
    assert r.status_code == 200
    assert json.loads(r.headers["HX-Trigger"]) == {"balance-stale": True, "forecast-stale": True}
    assert _html.exists(r.text, accounts.row(acc_id))
    assert _adjustments(_migrated, acc_id) == [12_345]
    assert "create" in {op for op, _ in audit_ops(_migrated, "transaction")}


@covers("POST /accounts/{account_id}/reconcile")
def test_reconcile_zero_delta_writes_nothing(
    client: TestClient, acc_id: int, _migrated: Settings
) -> None:
    r = client.post(f"/accounts/{acc_id}/reconcile", data={"actual_balance": "0"})
    assert r.status_code == 200
    assert _adjustments(_migrated, acc_id) == []
    assert audit_ops(_migrated, "transaction") == []


@covers("POST /accounts/{account_id}/reconcile")
def test_reconcile_can_also_save_snapshot(
    client: TestClient, acc_id: int, _migrated: Settings
) -> None:
    r = client.post(
        f"/accounts/{acc_id}/reconcile",
        data={"actual_balance": "10.00", "save_snapshot": "1"},
    )
    assert r.status_code == 200
    snaps = fetch_all(_migrated, "SELECT balance, note FROM account_snapshots")
    assert snaps == [{"balance": 1_000, "note": "reconcile snapshot"}]


@covers("POST /accounts/{account_id}/reconcile")
def test_reconcile_liability_by_available_credit(client: TestClient, _migrated: Settings) -> None:
    card = _make_account(_migrated, liability=True, limit=500_000, opening=-123_456, name="Visa")
    r = client.post(f"/accounts/{card}/reconcile", data={"actual_balance": "4000.00"})
    assert r.status_code == 200
    assert "Available 4,000.00 ·" in _html.text_of(r.text, accounts.row(card))
    assert _adjustments(_migrated, card) == [23_456]


@covers("POST /accounts/{account_id}/reconcile")
@pytest.mark.parametrize("value", ["-1", "5000.01", "abc"])
def test_reconcile_rejects_bad_available(
    client: TestClient, _migrated: Settings, value: str
) -> None:
    card = _make_account(_migrated, liability=True, limit=500_000, opening=-123_456, name="Visa")
    r = client.post(f"/accounts/{card}/reconcile", data={"actual_balance": value})
    assert r.status_code == 422
    assert _html.exists(r.text, accounts.form_errors)
    assert _adjustments(_migrated, card) == []


@covers("POST /accounts/{account_id}/reconcile")
def test_reconcile_bad_number_is_422(client: TestClient, acc_id: int, _migrated: Settings) -> None:
    r = client.post(f"/accounts/{acc_id}/reconcile", data={"actual_balance": "notnum"})
    assert r.status_code == 422
    assert _adjustments(_migrated, acc_id) == []


@covers("POST /accounts/{account_id}/reconcile")
def test_reconcile_missing_or_foreign_is_404(
    client: TestClient, foreign_id: int, _migrated: Settings
) -> None:
    data = {"actual_balance": "1"}
    assert client.post("/accounts/9999/reconcile", data=data).status_code == 404
    assert client.post(f"/accounts/{foreign_id}/reconcile", data=data).status_code == 404
    assert audit_ops(_migrated, "transaction") == []


@covers("POST /accounts/{account_id}/reconcile")
def test_reconcile_enforces_csrf_and_login(
    raw_client: TestClient, anon_client: TestClient, acc_id: int, _migrated: Settings
) -> None:
    data = {"actual_balance": "5.00"}
    assert raw_client.post(f"/accounts/{acc_id}/reconcile", data=data).status_code == 403
    r = anon_client.post(f"/accounts/{acc_id}/reconcile", data=data, follow_redirects=False)
    assert r.status_code == 302
    assert _adjustments(_migrated, acc_id) == []
