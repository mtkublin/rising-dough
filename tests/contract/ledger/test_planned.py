"""Contract: /planned routes (ADR-0106 section 1, T-UT04c)."""

from __future__ import annotations

import io
import re
from datetime import timedelta

import pyarrow.parquet as pq
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.repositories import planned as planned_repo
from tests.contract.conftest import covers
from tests.contract.ledger.support import USER_ID, audit_ops, hx_events, query, scalar
from tests.ui_map import _html, ledger
from tests.ui_map.locator import by_id, role

Ids = dict[str, int]
HTMX = {"HX-Request": "true"}
FORECAST_LEDGER = {"forecast-stale": True, "ledger-stale": True}


def _form(seeded: Ids, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "operation_date": "2026-11-01",
        "category_id": seeded["exp"],
        "account_id": seeded["acc"],
        "amount": "123.45",
        "description": "contract planned",
    }
    return {**base, **overrides}


def _add_due_planned(settings: Settings, seeded: Ids) -> int:
    conn = get_connection(settings)
    try:
        pl = planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=clock.today("Europe/Warsaw") - timedelta(days=1),
                category_id=seeded["exp"],
                account_id=seeded["acc"],
                amount=999,
                description="due",
            ),
        )
        return pl.id
    finally:
        conn.close()


@covers("GET /planned/table")
def test_table_alias_renders_planned_rows(client: TestClient, seeded: Ids) -> None:
    r = client.get("/planned/table")
    assert r.status_code == 200
    assert "<html" not in r.text
    assert _html.exists(r.text, ledger.planned_row(seeded["pl"]))


@covers("POST /planned")
def test_create_persists_audits_and_signals(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    r = client.post("/planned", data=_form(seeded))
    assert r.status_code == 200
    assert hx_events(r) == FORECAST_LEDGER
    assert r.headers["HX-Reswap"] == "none"
    assert r.headers["HX-Refresh"] == "true"
    new_id = scalar(_migrated, "SELECT MAX(id) FROM planned_transactions")
    assert new_id != seeded["pl"]
    assert (
        scalar(_migrated, "SELECT amount FROM planned_transactions WHERE id = ?", (new_id,))
        == 12345
    )
    assert audit_ops(_migrated, "planned_transaction", new_id) == ["create"]


@covers("POST /planned")
def test_create_on_ledger_skips_refresh(client: TestClient, seeded: Ids) -> None:
    r = client.post(
        "/planned", data=_form(seeded), headers={"HX-Current-URL": "https://testserver/ledger"}
    )
    assert r.status_code == 200
    assert "HX-Refresh" not in r.headers


@covers("POST /planned")
def test_create_validation_errors(client: TestClient, seeded: Ids, _migrated: Settings) -> None:
    before = scalar(_migrated, "SELECT COUNT(*) FROM planned_transactions")
    for bad in (
        {"operation_date": "nope"},
        {"amount": "-1"},
        {"amount": "abc"},
        {"account_id": 99999},
        {"category_id": 99999},
        {"dest_account_id": "zzz"},
        {"dest_account_id": 99999},
        {"dest_account_id": seeded["acc"]},
    ):
        r = client.post("/planned", data=_form(seeded, **bad))
        assert r.status_code == 422, bad
        assert "HX-Trigger" not in r.headers
    assert scalar(_migrated, "SELECT COUNT(*) FROM planned_transactions") == before


@covers("GET /planned/{planned_id}/edit")
def test_edit_form_and_unknown_id(client: TestClient, seeded: Ids) -> None:
    ok = client.get(f"/planned/{seeded['pl']}/edit", headers=HTMX)
    assert ok.status_code == 200
    assert ok.headers["HX-Retarget"] == "#modal-root"  # a dialog now, not a slide-over
    assert _html.exists(ok.text, role("dialog", re.compile(r"^edit planned")))
    assert "<html" not in ok.text
    assert client.get("/planned/99999/edit").status_code == 404


@covers("POST /planned/{planned_id}")
def test_update_persists_audits_and_signals(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    r = client.post(f"/planned/{seeded['pl']}", data=_form(seeded, amount="9"))
    assert r.status_code == 200
    assert hx_events(r) == FORECAST_LEDGER
    # the dialog closes: #modal-root is emptied out of band (was HX-Reswap none + reload)
    assert "HX-Reswap" not in r.headers
    assert _html.resolve_one(r.text, by_id("modal-root")).get("hx-swap-oob") == "innerHTML"
    assert (
        scalar(_migrated, "SELECT amount FROM planned_transactions WHERE id = ?", (seeded["pl"],))
        == 900
    )
    assert audit_ops(_migrated, "planned_transaction", seeded["pl"]) == ["create", "update"]


@covers("POST /planned/{planned_id}")
def test_update_errors(client: TestClient, seeded: Ids, _migrated: Settings) -> None:
    bad = client.post(f"/planned/{seeded['pl']}", data=_form(seeded, amount="0"))
    assert bad.status_code == 422
    assert (
        scalar(_migrated, "SELECT amount FROM planned_transactions WHERE id = ?", (seeded["pl"],))
        == 2500
    )
    assert client.post("/planned/99999", data=_form(seeded)).status_code == 404


@covers("POST /planned/{planned_id}/delete", "POST /planned/{planned_id}/restore")
def test_delete_then_restore_round_trip(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    deleted = client.post(f"/planned/{seeded['pl']}/delete")
    assert deleted.status_code == 200
    assert hx_events(deleted) == FORECAST_LEDGER
    sql = "SELECT deleted_at IS NOT NULL FROM planned_transactions WHERE id = ?"
    assert scalar(_migrated, sql, (seeded["pl"],)) == 1
    restored = client.post(f"/planned/{seeded['pl']}/restore")
    assert restored.status_code == 200
    assert hx_events(restored) == {
        **FORECAST_LEDGER,
        "toast": {"variant": "success", "message": "Planned entry restored"},
    }
    assert scalar(_migrated, sql, (seeded["pl"],)) == 0
    assert len(audit_ops(_migrated, "planned_transaction", seeded["pl"])) == 3


@covers("POST /planned/{planned_id}/delete", "POST /planned/{planned_id}/restore")
def test_delete_and_restore_unknown_id_are_404(client: TestClient, seeded: Ids) -> None:
    assert client.post("/planned/99999/delete").status_code == 404
    assert client.post("/planned/99999/restore").status_code == 404


@covers("GET /planned/{planned_id}/promote")
def test_promote_form_and_unknown_id(client: TestClient, seeded: Ids) -> None:
    modal = client.get(f"/planned/{seeded['pl']}/promote", headers=HTMX)
    assert modal.status_code == 200
    assert "<html" not in modal.text
    assert client.get("/planned/99999/promote").status_code == 404


def test_inline_promote_route_is_gone(client: TestClient, seeded: Ids) -> None:
    """T-UR24: the inline promote form route no longer exists."""
    assert client.get(f"/planned/{seeded['pl']}/promote/inline", headers=HTMX).status_code == 404


@covers("POST /planned/{planned_id}/promote")
def test_promote_creates_transaction_and_links_it(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    txns_before = scalar(_migrated, "SELECT COUNT(*) FROM transactions")
    r = client.post(
        f"/planned/{seeded['pl']}/promote",
        data={"operation_date": "2026-11-02", "amount": "25", "description": "promoted"},
    )
    assert r.status_code == 200
    assert hx_events(r) == {"balance-stale": True, "forecast-stale": True, "ledger-stale": True}
    assert r.headers["HX-Reswap"] == "none"
    assert scalar(_migrated, "SELECT COUNT(*) FROM transactions") == txns_before + 1
    linked = scalar(
        _migrated,
        "SELECT promoted_to_txn_id FROM planned_transactions WHERE id = ?",
        (seeded["pl"],),
    )
    assert linked is not None
    assert audit_ops(_migrated, "transaction", linked) == ["create"]


@covers("POST /planned/{planned_id}/promote")
def test_promote_errors(client: TestClient, seeded: Ids, _migrated: Settings) -> None:
    for bad in (
        {"operation_date": "nope", "amount": "5"},
        {"operation_date": "2026-11-02", "amount": "-3"},
    ):
        assert client.post(f"/planned/{seeded['pl']}/promote", data=bad).status_code == 422
    ok = {"operation_date": "2026-11-02", "amount": "5"}
    assert client.post(f"/planned/{seeded['pl']}/promote", data=ok).status_code == 200
    again = client.post(f"/planned/{seeded['pl']}/promote", data=ok)
    assert again.status_code == 422  # already promoted
    assert client.post("/planned/99999/promote", data=ok).status_code == 404


@covers("POST /planned/batch/promote-due", "POST /planned/batch/undo")
def test_batch_promote_due_and_undo(client: TestClient, seeded: Ids, _migrated: Settings) -> None:
    due_id = _add_due_planned(_migrated, seeded)
    r = client.post("/planned/batch/promote-due")
    assert r.status_code == 204
    events = hx_events(r)
    toast = events["toast"]
    assert toast["undo_url"] == "/planned/batch/undo"
    assert events["ledger-stale"] is True
    payload = toast["undo_payload"]
    assert len(payload["promoted_txn_ids"]) == 1
    assert payload["promoted_planned_ids"] == [due_id]
    sql = "SELECT promoted_to_txn_id FROM planned_transactions WHERE id = ?"
    assert scalar(_migrated, sql, (due_id,)) == payload["promoted_txn_ids"][0]
    # the future-dated seed row is untouched
    assert scalar(_migrated, sql, (seeded["pl"],)) is None

    undo = client.post(
        "/planned/batch/undo",
        data={
            "promoted_txn_ids": ",".join(map(str, payload["promoted_txn_ids"])),
            "promoted_planned_ids": ",".join(map(str, payload["promoted_planned_ids"])),
        },
    )
    assert undo.status_code == 204
    assert hx_events(undo)["toast"] == {"variant": "info", "message": "Undone"}
    assert scalar(_migrated, sql, (due_id,)) is None
    txn_deleted = query(
        _migrated,
        "SELECT deleted_at IS NOT NULL FROM transactions WHERE id = ?",
        (payload["promoted_txn_ids"][0],),
    )
    assert txn_deleted[0][0] == 1


@covers("POST /planned/batch/undo")
def test_batch_undo_rejects_malformed_ids(client: TestClient, seeded: Ids) -> None:
    r = client.post("/planned/batch/undo", data={"promoted_txn_ids": "a,b"})
    assert r.status_code == 422


@covers("POST /planned/batch/promote-due")
def test_batch_promote_due_with_nothing_due_is_a_noop_toast(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    r = client.post("/planned/batch/promote-due")
    assert r.status_code == 204
    assert hx_events(r)["toast"]["undo_payload"] == {
        "promoted_txn_ids": [],
        "promoted_planned_ids": [],
    }


@covers("GET /planned/export")
def test_export_csv_and_parquet(client: TestClient, seeded: Ids) -> None:
    csv = client.get("/planned/export", params={"date_from": "2000-01-01", "date_to": "2100-01-01"})
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    assert csv.headers["content-disposition"].startswith('attachment; filename="planned_')
    assert "seed planned" in csv.text
    resp = client.get("/planned/export", params={"format": "parquet", "scope": "unpromoted"})
    assert resp.headers["content-type"] == "application/vnd.apache.parquet"
    assert isinstance(pq.read_table(io.BytesIO(resp.content)).num_rows, int)
