"""T-031 transactions router — structural + mutation tests."""

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
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from tests.ui_map import _html, entries, ledger

USER_ID = 1


@pytest.fixture
def seeded(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        acc2 = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Savings", currency="PLN", opening_balance=0)
        )
        groc = categories_repo.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        )
        salary = categories_repo.create(
            conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
        )
        return {"acc": acc.id, "acc2": acc2.id, "groc": groc.id, "salary": salary.id}
    finally:
        conn.close()


def _create_txn(
    settings: Settings, acc_id: int, cat_id: int, *, amount: int = 100, desc: str = "x"
) -> int:
    conn = get_connection(settings)
    try:
        txn = transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=date(2026, 10, 1),
                category_id=cat_id,
                account_id=acc_id,
                amount=amount,
                description=desc,
            ),
        )
        return txn.id
    finally:
        conn.close()


def _new_txn_id(settings: Settings) -> int:
    conn = get_connection(settings)
    try:
        return int(conn.execute("SELECT MAX(id) FROM transactions").fetchone()[0])
    finally:
        conn.close()


def test_list_page_redirects_to_ledger(client: TestClient, seeded: dict[str, int]) -> None:
    """T-070: ``/transactions`` returns 302 to the unified ledger (actual view)."""
    r = client.get("/transactions", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/ledger?view=actual"


def test_table_fragment_is_not_full_page(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.get("/transactions/table")
    assert r.status_code == 200
    assert _html.exists(r.text, ledger.table)
    assert not _html.exists(r.text, ledger.heading)  # fragment: no page chrome


def test_new_form_fragment(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.get("/transactions/new", headers={"HX-Request": "true"})
    assert r.status_code == 200
    form = _html.resolve_one(r.text, entries.dialog).find("form")
    assert form is not None
    assert form.get("hx-post") == "/transactions"
    date_field = _html.resolve_one(r.text, entries.field_date)
    account = _html.resolve_one(r.text, entries.field_account)
    amount = _html.resolve_one(r.text, entries.hero_amount)
    assert (date_field.get("name"), date_field.get("type")) == ("operation_date", "date")
    assert account.get("name") == "account_id"
    assert amount.get("name") == "amount"
    # The category is picked from the shared picker; its radios post as "category".
    assert _html.exists(r.text, entries.category_group)


def test_create_valid_persists_and_triggers(
    client: TestClient, seeded: dict[str, int], _migrated: Settings
) -> None:
    r = client.post(
        "/transactions",
        data={
            "operation_date": "2026-10-20",
            "category_id": seeded["groc"],
            "account_id": seeded["acc"],
            "amount": "12.34",
            "description": "Test",
        },
    )
    assert r.status_code == 200
    assert _html.exists(r.text, ledger.row(_new_txn_id(_migrated)))
    hx = json.loads(r.headers["HX-Trigger"])
    assert hx == {"balance-stale": True, "forecast-stale": True, "ledger-stale": True}
    conn = get_connection(_migrated)
    try:
        row = conn.execute("SELECT amount, description FROM transactions").fetchone()
    finally:
        conn.close()
    assert row[0] == 1234
    assert row[1] == "Test"


def _create_data(seeded: dict[str, int]) -> dict[str, str | int]:
    return {
        "operation_date": "2026-10-20",
        "category_id": seeded["groc"],
        "account_id": seeded["acc"],
        "amount": "12.34",
    }


def test_create_off_ledger_refreshes_page_without_swap(
    client: TestClient, seeded: dict[str, int]
) -> None:
    # T-D141: the Add overlay is opened from Today etc.; no table to swap into.
    r = client.post(
        "/transactions",
        data=_create_data(seeded),
        headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/today"},
    )
    assert r.status_code == 200
    assert r.headers["HX-Reswap"] == "none"
    assert r.headers["HX-Refresh"] == "true"


def test_create_on_ledger_does_not_refresh_page(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.post(
        "/transactions",
        data=_create_data(seeded),
        headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/ledger?view=actual"},
    )
    assert r.status_code == 200
    assert r.headers["HX-Reswap"] == "none"
    assert "HX-Refresh" not in r.headers


def test_new_form_posts_into_the_modal_root_not_the_ledger_table(
    client: TestClient, seeded: dict[str, int]
) -> None:
    r = client.get("/transactions/new", headers={"HX-Request": "true"})
    form = _html.resolve_one(r.text, entries.dialog).find("form")
    assert form is not None
    assert form.get("hx-target") == "#modal-root"


def test_new_form_on_a_plain_page_load_opens_the_dialog_through_the_shell(
    client: TestClient, seeded: dict[str, int]
) -> None:
    """The top bar links here: a full load is a shell page that fetches ``/add`` on load."""
    r = client.get("/transactions/new")
    assert r.status_code == 200
    opener = _html.resolve_one(r.text, entries.opener)
    assert (opener.get("hx-get"), opener.get("hx-trigger")) == (
        "/add?when=happened&dialog=1",
        "load",
    )


def test_create_invalid_amount_returns_form(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.post(
        "/transactions",
        data={
            "operation_date": "2026-10-20",
            "category_id": seeded["groc"],
            "account_id": seeded["acc"],
            "amount": "-5",
        },
    )
    assert r.status_code == 422
    assert "amount" in _html.text_of(r.text, ledger.form_errors)


def test_create_rejects_cross_currency_transit(client: TestClient, _migrated: Settings) -> None:
    conn = get_connection(_migrated)
    try:
        acc_pln = accounts_repo.create(conn, USER_ID, NewAccount(name="A", currency="PLN"))
        acc_eur = accounts_repo.create(conn, USER_ID, NewAccount(name="B", currency="EUR"))
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Transit X", direction=Direction.TRANSIT)
        )
    finally:
        conn.close()
    r = client.post(
        "/transactions",
        data={
            "operation_date": "2026-10-20",
            "category_id": cat.id,
            "account_id": acc_pln.id,
            "dest_account_id": acc_eur.id,
            "amount": "10",
        },
    )
    assert r.status_code == 422
    assert "cross-currency" in _html.text_of(r.text, ledger.form_errors)


def test_edit_and_update(client: TestClient, seeded: dict[str, int], _migrated: Settings) -> None:
    txn_id = _create_txn(_migrated, seeded["acc"], seeded["groc"], amount=5000)
    r = client.get(f"/transactions/{txn_id}/edit", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert _html.resolve_one(r.text, ledger.form).get("hx-post") == f"/transactions/{txn_id}"
    assert ledger.control(r.text, ledger.field_amount).get("value") == "50.00"
    r2 = client.post(
        f"/transactions/{txn_id}",
        data={
            "operation_date": "2026-10-02",
            "category_id": seeded["groc"],
            "account_id": seeded["acc"],
            "amount": "99.99",
            "description": "new",
        },
    )
    assert r2.status_code == 200
    assert json.loads(r2.headers["HX-Trigger"]) == {
        "balance-stale": True,
        "forecast-stale": True,
        "ledger-stale": True,
    }


def test_delete_soft_deletes(
    client: TestClient, seeded: dict[str, int], _migrated: Settings
) -> None:
    txn_id = _create_txn(_migrated, seeded["acc"], seeded["groc"])
    r = client.post(f"/transactions/{txn_id}/delete")
    assert r.status_code == 200
    assert r.text == ""
    assert "balance-stale" in r.headers["HX-Trigger"]
    conn = get_connection(_migrated)
    try:
        row = conn.execute("SELECT deleted_at FROM transactions WHERE id = ?", (txn_id,)).fetchone()
    finally:
        conn.close()
    assert row[0] is not None


def test_export_csv(client: TestClient, seeded: dict[str, int], _migrated: Settings) -> None:
    for i in range(3):
        _create_txn(_migrated, seeded["acc"], seeded["groc"], amount=100 + i, desc=f"row{i}")
    r = client.get("/transactions/export?format=csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert len(lines) == 4  # header + 3


def test_export_parquet(client: TestClient, seeded: dict[str, int], _migrated: Settings) -> None:
    _create_txn(_migrated, seeded["acc"], seeded["groc"])
    r = client.get("/transactions/export?format=parquet")
    assert r.status_code == 200
    tbl = pq.read_table(io.BytesIO(r.content))
    assert tbl.num_rows == 1


def test_create_rejects_unknown_account_and_category(
    client: TestClient,
) -> None:
    r = client.post(
        "/transactions",
        data={
            "operation_date": "2026-10-20",
            "category_id": 9999,
            "account_id": 9999,
            "amount": "10",
        },
    )
    assert r.status_code == 422
    assert "unknown account" in _html.text_of(r.text, ledger.form_errors)


def test_create_rejects_bad_date(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.post(
        "/transactions",
        data={
            "operation_date": "not-a-date",
            "category_id": seeded["groc"],
            "account_id": seeded["acc"],
            "amount": "10",
        },
    )
    assert r.status_code == 422
    assert "operation_date" in _html.text_of(r.text, ledger.form_errors)


def test_create_rejects_bad_amount_string(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.post(
        "/transactions",
        data={
            "operation_date": "2026-10-20",
            "category_id": seeded["groc"],
            "account_id": seeded["acc"],
            "amount": "abc",
        },
    )
    assert r.status_code == 422


def test_edit_404(client: TestClient) -> None:
    r = client.get("/transactions/9999/edit")
    assert r.status_code == 404


def test_update_404(client: TestClient, seeded: dict[str, int]) -> None:
    r = client.post(
        "/transactions/9999",
        data={
            "operation_date": "2026-10-20",
            "category_id": seeded["groc"],
            "account_id": seeded["acc"],
            "amount": "10",
        },
    )
    assert r.status_code == 404


def test_update_invalid(client: TestClient, seeded: dict[str, int], _migrated: Settings) -> None:
    txn_id = _create_txn(_migrated, seeded["acc"], seeded["groc"])
    r = client.post(
        f"/transactions/{txn_id}",
        data={
            "operation_date": "bad",
            "category_id": seeded["groc"],
            "account_id": seeded["acc"],
            "amount": "-1",
        },
    )
    assert r.status_code == 422


def test_bad_query_params_tolerated(client: TestClient, seeded: dict[str, int]) -> None:
    # Legacy path redirects to /ledger (T-070); follow it to confirm the
    # ledger likewise tolerates garbled query params.
    r = client.get("/transactions?account_id=notanint&page=notanint&min_amount=xx")
    assert r.status_code == 200


def test_filter_by_category(
    client: TestClient, seeded: dict[str, int], _migrated: Settings
) -> None:
    _create_txn(_migrated, seeded["acc"], seeded["groc"], desc="g")
    _create_txn(_migrated, seeded["acc"], seeded["salary"], desc="s")
    r = client.get(f"/transactions/table?category_id={seeded['groc']}")
    assert r.status_code == 200
    rows = _html.resolve(r.text, ledger.table_rows("actual"))
    texts = {" ".join(row.get_text(" ").split()) for row in rows}
    assert any(" g " in f" {t} " for t in texts)
    assert not any(" s " in f" {t} " for t in texts)


# ---------------------------------------------------------------------------
# T-085 — Transaction-form credit-card soft warning (ADR-0024)


@pytest.fixture
def visa_setup(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        visa = accounts_repo.create(
            conn,
            USER_ID,
            NewAccount(
                name="Visa",
                currency="PLN",
                is_liability=True,
                credit_limit_minor=1_000_000,
            ),
        )
        asset = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Bank", currency="PLN", opening_balance=200_000)
        )
        expense = categories_repo.create(
            conn, USER_ID, NewCategory(name="X", direction=Direction.EXPENSE)
        )
        income = categories_repo.create(
            conn, USER_ID, NewCategory(name="Pay", direction=Direction.INCOME)
        )
        return {
            "visa": visa.id,
            "asset": asset.id,
            "expense": expense.id,
            "income": income.id,
        }
    finally:
        conn.close()


def test_preview_hidden_for_asset_account(client: TestClient, visa_setup: dict[str, int]) -> None:
    r = client.get(
        "/transactions/_limit_preview",
        params={
            "account_id": visa_setup["asset"],
            "category_id": visa_setup["expense"],
            "amount": "100.00",
        },
    )
    assert r.status_code == 200
    assert _html.exists(r.text, ledger.limit_preview)
    assert _html.text_of(r.text, ledger.limit_preview) == ""


def test_preview_shows_available_for_within_limit_expense(
    client: TestClient, visa_setup: dict[str, int]
) -> None:
    r = client.get(
        "/transactions/_limit_preview",
        params={
            "account_id": visa_setup["visa"],
            "category_id": visa_setup["expense"],
            "amount": "500.00",
        },
    )
    assert r.status_code == 200
    text = _html.text_of(r.text, ledger.limit_preview)
    assert "After this transaction" in text
    assert "9,500.00" in text


def test_preview_shows_over_limit_for_overshoot_expense(
    client: TestClient, visa_setup: dict[str, int]
) -> None:
    r = client.get(
        "/transactions/_limit_preview",
        params={
            "account_id": visa_setup["visa"],
            "category_id": visa_setup["expense"],
            "amount": "15000.00",
        },
    )
    assert r.status_code == 200
    text = _html.text_of(r.text, ledger.limit_preview)
    assert "Over limit" in text
    assert "5,000.00" in text


def test_preview_handles_adjustment_signed_amount(
    client: TestClient, visa_setup: dict[str, int], _migrated: Settings
) -> None:
    conn = get_connection(_migrated)
    try:
        adj_cat = categories_repo.find_by_name(conn, USER_ID, "Reconciliation")
        assert adj_cat is not None
    finally:
        conn.close()
    r = client.get(
        "/transactions/_limit_preview",
        params={
            "account_id": visa_setup["visa"],
            "category_id": adj_cat.id,
            "amount": "100.00",
        },
    )
    assert r.status_code == 200


def test_preview_updates_on_amount_change(client: TestClient, visa_setup: dict[str, int]) -> None:
    r1 = client.get(
        "/transactions/_limit_preview",
        params={
            "account_id": visa_setup["visa"],
            "category_id": visa_setup["expense"],
            "amount": "100.00",
        },
    )
    r2 = client.get(
        "/transactions/_limit_preview",
        params={
            "account_id": visa_setup["visa"],
            "category_id": visa_setup["expense"],
            "amount": "500.00",
        },
    )
    assert "9,900.00" in _html.text_of(r1.text, ledger.limit_preview)
    assert "9,500.00" in _html.text_of(r2.text, ledger.limit_preview)


def test_preview_bad_amount_returns_blank_fragment(
    client: TestClient, visa_setup: dict[str, int]
) -> None:
    r = client.get(
        "/transactions/_limit_preview",
        params={
            "account_id": visa_setup["visa"],
            "category_id": visa_setup["expense"],
            "amount": "not-a-number",
        },
    )
    assert r.status_code == 200
    assert _html.text_of(r.text, ledger.limit_preview) == ""


def test_form_submits_even_when_over_limit(client: TestClient, visa_setup: dict[str, int]) -> None:
    r = client.post(
        "/transactions",
        data={
            "operation_date": "2026-10-27",
            "category_id": visa_setup["expense"],
            "account_id": visa_setup["visa"],
            "amount": "15000.00",
            "description": "overshoot",
        },
    )
    assert r.status_code == 200


_ON_TODAY = {"HX-Request": "true", "HX-Current-URL": "http://testserver/today"}
_ON_LEDGER = {"HX-Request": "true", "HX-Current-URL": "http://testserver/ledger?view=actual"}


def _update_data(seeded: dict[str, int], amount: str = "99.99") -> dict[str, str | int]:
    return {
        "operation_date": "2026-10-02",
        "category_id": seeded["groc"],
        "account_id": seeded["acc"],
        "amount": amount,
    }


def test_edit_form_targets_itself_and_closes_on_success(
    client: TestClient, seeded: dict[str, int], _migrated: Settings
) -> None:
    txn_id = _create_txn(_migrated, seeded["acc"], seeded["groc"])
    r = client.get(f"/transactions/{txn_id}/edit")
    form = _html.resolve_one(r.text, ledger.form)
    assert form.get("hx-target") == "#txn-form"
    assert form.has_attr("data-close-overlay-on-success")


def test_update_off_ledger_refreshes_page_without_swap(
    client: TestClient, seeded: dict[str, int], _migrated: Settings
) -> None:
    txn_id = _create_txn(_migrated, seeded["acc"], seeded["groc"])
    r = client.post(f"/transactions/{txn_id}", data=_update_data(seeded), headers=_ON_TODAY)
    assert r.status_code == 200
    assert r.headers["HX-Reswap"] == "none"
    assert r.headers["HX-Refresh"] == "true"
    assert "ledger-stale" in r.headers["HX-Trigger"]


def test_update_on_ledger_does_not_refresh_page(
    client: TestClient, seeded: dict[str, int], _migrated: Settings
) -> None:
    txn_id = _create_txn(_migrated, seeded["acc"], seeded["groc"])
    r = client.post(f"/transactions/{txn_id}", data=_update_data(seeded), headers=_ON_LEDGER)
    assert r.headers["HX-Reswap"] == "none"
    assert "HX-Refresh" not in r.headers
    assert "ledger-stale" in r.headers["HX-Trigger"]


def test_update_invalid_amount_rerenders_form_in_place(
    client: TestClient, seeded: dict[str, int], _migrated: Settings
) -> None:
    txn_id = _create_txn(_migrated, seeded["acc"], seeded["groc"])
    r = client.post(
        f"/transactions/{txn_id}", data=_update_data(seeded, amount="0"), headers=_ON_TODAY
    )
    assert r.status_code == 422
    assert _html.exists(r.text, ledger.form)
    assert "amount" in _html.text_of(r.text, ledger.form_errors)
