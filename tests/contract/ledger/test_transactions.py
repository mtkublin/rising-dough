"""Contract: /transactions routes (ADR-0106 section 1, T-UT04c)."""

from __future__ import annotations

import io

import pyarrow.parquet as pq
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from tests.contract.conftest import covers
from tests.contract.ledger.support import audit_ops, hx_events, scalar, txn_form
from tests.ui_map import _html, entries, errors, ledger
from tests.ui_map.locator import by_id

Ids = dict[str, int]
HTMX = {"HX-Request": "true"}
STALE = {"balance-stale": True, "forecast-stale": True, "ledger-stale": True}


@covers("GET /transactions")
def test_list_redirects_to_actual_ledger(client: TestClient) -> None:
    r = client.get("/transactions", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/ledger?view=actual"


@covers("GET /transactions/table")
def test_table_alias_matches_ledger_fragment(client: TestClient, seeded: Ids) -> None:
    r = client.get("/transactions/table")
    assert r.status_code == 200
    assert "<html" not in r.text
    assert _html.exists(r.text, ledger.table)
    assert _html.exists(r.text, ledger.row(seeded["txn"]))


@covers("GET /transactions/_limit_preview")
def test_limit_preview_blank_ok_and_malformed_ids_422(client: TestClient, seeded: Ids) -> None:
    blank = client.get("/transactions/_limit_preview")
    assert blank.status_code == 200
    non_liability = client.get(
        "/transactions/_limit_preview",
        params={"account_id": seeded["acc"], "category_id": seeded["exp"], "amount": "10"},
    )
    assert non_liability.status_code == 200
    garbage = client.get(
        "/transactions/_limit_preview",
        params={"account_id": "x", "category_id": "y", "amount": "z"},
    )
    assert garbage.status_code == 422  # T-Q282: malformed ids are a 422, not a blank preview
    bad_txn = client.get(
        "/transactions/_limit_preview",
        params={"account_id": seeded["acc"], "category_id": seeded["exp"], "txn_id": "x"},
    )
    assert bad_txn.status_code == 422  # T-UR34d: the edited transaction id is validated too


@covers("POST /transactions")
def test_create_persists_audits_and_signals(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    r = client.post("/transactions", data=txn_form(seeded))
    assert r.status_code == 200
    assert hx_events(r) == {**STALE, "today-stale": True, "budget-stale": True}
    assert "HX-Reswap" not in r.headers
    assert "HX-Refresh" not in r.headers  # off the ledger: events refetch, the flash stays
    new_id = scalar(_migrated, "SELECT MAX(id) FROM transactions")
    assert new_id != seeded["txn"]
    assert scalar(_migrated, "SELECT amount FROM transactions WHERE id = ?", (new_id,)) == 1234
    assert audit_ops(_migrated, "transaction", new_id) == ["create"]


@covers("POST /transactions")
def test_create_on_ledger_page_skips_refresh(client: TestClient, seeded: Ids) -> None:
    r = client.post(
        "/transactions",
        data=txn_form(seeded),
        headers={"HX-Current-URL": "https://testserver/ledger?view=actual"},
    )
    assert r.status_code == 200
    assert r.headers["HX-Reswap"] == "none"
    assert "HX-Refresh" not in r.headers


@covers("POST /transactions")
def test_create_validation_errors_are_422_and_write_nothing(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    before = scalar(_migrated, "SELECT COUNT(*) FROM transactions")
    for bad in (
        {"operation_date": "nope"},
        {"amount": "-5"},
        {"amount": "abc"},
        {"account_id": 99999},
        {"category_id": 99999},
    ):
        r = client.post("/transactions", data=txn_form(seeded, **bad))
        assert r.status_code == 422, bad
        assert "HX-Trigger" not in r.headers
    same = client.post(
        "/transactions",
        data=txn_form(seeded, category_id=seeded["move"], dest_account_id=seeded["acc"]),
    )
    assert same.status_code == 422
    assert scalar(_migrated, "SELECT COUNT(*) FROM transactions") == before


@covers("POST /transactions")
def test_create_transit_with_destination(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    r = client.post(
        "/transactions",
        data=txn_form(seeded, category_id=seeded["move"], dest_account_id=seeded["acc2"]),
    )
    assert r.status_code == 200
    assert (
        scalar(_migrated, "SELECT dest_account_id FROM transactions ORDER BY id DESC LIMIT 1")
        == seeded["acc2"]
    )


@covers("GET /transactions/{txn_id}/edit")
def test_edit_form_and_unknown_id(client: TestClient, seeded: Ids) -> None:
    ok = client.get(f"/transactions/{seeded['txn']}/edit", headers=HTMX)
    assert ok.status_code == 200
    assert _html.count(ok.text, entries.edit_dialog) == 1
    assert ok.headers["HX-Retarget"] == "#modal-root"
    missing = client.get("/transactions/99999/edit")
    assert missing.status_code == 404
    assert _html.text_of(missing.text, errors.heading) == "Not found"
    flash = client.get("/transactions/99999/edit", headers=HTMX)
    assert flash.status_code == 404
    assert "Transaction not found" in _html.text_of(flash.text, by_id("flash-region"))


@covers("POST /transactions/{txn_id}")
def test_update_persists_audits_and_signals(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    r = client.post(
        f"/transactions/{seeded['txn']}", data=txn_form(seeded, amount="77", description="edited")
    )
    assert r.status_code == 200
    assert hx_events(r) == STALE
    assert r.headers["HX-Reswap"] == "none"
    assert (
        scalar(_migrated, "SELECT amount FROM transactions WHERE id = ?", (seeded["txn"],)) == 7700
    )
    assert audit_ops(_migrated, "transaction", seeded["txn"]) == ["create", "update"]


@covers("POST /transactions/{txn_id}")
def test_update_errors(client: TestClient, seeded: Ids, _migrated: Settings) -> None:
    bad = client.post(f"/transactions/{seeded['txn']}", data=txn_form(seeded, amount="0"))
    assert bad.status_code == 422
    assert (
        scalar(_migrated, "SELECT amount FROM transactions WHERE id = ?", (seeded["txn"],)) == 1500
    )
    missing = client.post("/transactions/99999", data=txn_form(seeded))
    assert missing.status_code == 404
    assert _html.text_of(missing.text, errors.heading) == "Not found"


@covers("POST /transactions/{txn_id}/delete", "POST /transactions/{txn_id}/restore")
def test_delete_then_restore_round_trip(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    deleted = client.post(f"/transactions/{seeded['txn']}/delete")
    assert deleted.status_code == 200
    assert deleted.headers["HX-Reswap"] == "delete"
    assert _html.count(deleted.text, entries.toast_undo) == 1
    assert hx_events(deleted) == STALE
    assert (
        scalar(
            _migrated,
            "SELECT deleted_at IS NOT NULL FROM transactions WHERE id = ?",
            (seeded["txn"],),
        )
        == 1
    )
    restored = client.post(f"/transactions/{seeded['txn']}/restore")
    assert restored.status_code == 200
    assert hx_events(restored) == {
        **STALE,
        "toast": {"variant": "success", "message": "Transaction restored"},
    }
    assert (
        scalar(
            _migrated, "SELECT deleted_at IS NULL FROM transactions WHERE id = ?", (seeded["txn"],)
        )
        == 1
    )
    ops = audit_ops(_migrated, "transaction", seeded["txn"])
    assert ops[0] == "create"
    assert len(ops) == 3


@covers("POST /transactions/{txn_id}/restore")
def test_restore_unknown_id_is_404(client: TestClient, seeded: Ids) -> None:
    r = client.post("/transactions/99999/restore")
    assert r.status_code == 404
    assert _html.text_of(r.text, errors.heading) == "Not found"


@covers("GET /transactions/export")
def test_export_csv_and_parquet(client: TestClient, seeded: Ids) -> None:
    csv = client.get("/transactions/export")
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    assert csv.headers["content-disposition"].startswith('attachment; filename="transactions_')
    assert "seed txn" in csv.text
    filtered = client.get("/transactions/export", params={"q": "zzz-none"})
    assert "seed txn" not in filtered.text
    pq_resp = client.get("/transactions/export", params={"format": "parquet"})
    assert pq_resp.headers["content-type"] == "application/vnd.apache.parquet"
    table = pq.read_table(io.BytesIO(pq_resp.content))
    assert table.num_rows == 1
