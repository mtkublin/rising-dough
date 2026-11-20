"""Contract: /recurring routes (ADR-0106 section 1, T-UT04c)."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.repositories import recurring as recurring_repo
from tests.contract.conftest import covers
from tests.contract.ledger.support import audit_ops, hx_events, query, rule_form, scalar
from tests.ui_map import _html, ledger

Ids = dict[str, int]
HTMX = {"HX-Request": "true"}
FORECAST_LEDGER = {"forecast-stale": True, "ledger-stale": True}
PROMOTE_EVENTS = {"ledger-stale": True, "forecast-stale": True, "budget-stale": True}


def _next_due(settings: Settings, rule_id: int) -> str:
    return str(scalar(settings, "SELECT next_due FROM recurring_rules WHERE id = ?", (rule_id,)))


def _make_due(settings: Settings, rule_id: int) -> None:
    conn = get_connection(settings)
    try:
        recurring_repo.set_next_due(
            conn,
            1,
            rule_id,
            next_due=date.today() - timedelta(days=1),  # noqa: DTZ011
            last_promoted_date=None,
        )
    finally:
        conn.close()


@covers("GET /recurring")
def test_index_redirects_to_recurring_ledger(client: TestClient) -> None:
    r = client.get("/recurring", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/ledger?view=recurring"


@covers("GET /recurring/new")
def test_new_form_is_a_slideover(client: TestClient, seeded: Ids) -> None:
    r = client.get("/recurring/new", headers=HTMX)
    assert r.status_code == 200
    assert "<html" not in r.text


@covers("POST /recurring")
def test_create_persists_audits_and_signals(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    r = client.post("/recurring", data=rule_form(seeded))
    assert r.status_code == 200
    assert hx_events(r) == FORECAST_LEDGER
    assert r.headers["HX-Reswap"] == "none"
    assert r.headers["HX-Refresh"] == "true"
    new_id = scalar(_migrated, "SELECT MAX(id) FROM recurring_rules")
    assert new_id != seeded["rule"]
    assert (
        scalar(_migrated, "SELECT default_amount FROM recurring_rules WHERE id = ?", (new_id,))
        == 50000
    )
    assert audit_ops(_migrated, "recurring_rule", new_id) == ["create"]


@covers("POST /recurring")
def test_create_with_past_end_date_is_born_inactive(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    r = client.post("/recurring", data=rule_form(seeded, end_date="2026-03-01"))
    assert r.status_code == 200
    new_id = scalar(_migrated, "SELECT MAX(id) FROM recurring_rules")
    assert scalar(_migrated, "SELECT active FROM recurring_rules WHERE id = ?", (new_id,)) == 0


@covers("POST /recurring")
def test_create_with_formula_term(client: TestClient, seeded: Ids, _migrated: Settings) -> None:
    r = client.post(
        "/recurring",
        data=rule_form(
            seeded,
            category_id=seeded["exp"],
            amount_source="formula",
            default_amount="",
            **{
                "terms[0][sign]": "+",
                "terms[0][coefficient_percent]": "10",
                "terms[0][source_category_ids]": str(seeded["inc"]),
            },
        ),
    )
    assert r.status_code == 200
    new_id = scalar(_migrated, "SELECT MAX(id) FROM recurring_rules")
    assert (
        scalar(
            _migrated,
            "SELECT amount_formula IS NOT NULL FROM recurring_rules WHERE id = ?",
            (new_id,),
        )
        == 1
    )


@covers("POST /recurring")
def test_create_validation_errors(client: TestClient, seeded: Ids, _migrated: Settings) -> None:
    before = scalar(_migrated, "SELECT COUNT(*) FROM recurring_rules")
    for bad in (
        {"cadence": "bogus"},
        {"start_date": "nope"},
        {"end_date": "2025-01-01"},
        {"default_amount": "abc"},
        {"default_amount": "-4"},
        {"account_id": "x"},
        {"account_id": 99999},
        {"category_id": 99999},
    ):
        r = client.post("/recurring", data=rule_form(seeded, **bad))
        assert r.status_code == 422, bad
        assert "HX-Trigger" not in r.headers
    assert scalar(_migrated, "SELECT COUNT(*) FROM recurring_rules") == before


@covers("GET /recurring/{rule_id}/edit")
def test_edit_form_and_unknown_id(client: TestClient, seeded: Ids) -> None:
    ok = client.get(f"/recurring/{seeded['rule']}/edit", headers=HTMX)
    assert ok.status_code == 200
    assert "<html" not in ok.text
    assert client.get("/recurring/99999/edit").status_code == 404


@covers("POST /recurring/{rule_id}")
def test_update_persists_audits_and_signals(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    r = client.post(
        f"/recurring/{seeded['rule']}",
        data=rule_form(seeded, default_amount="12", cadence="yearly"),
    )
    assert r.status_code == 200
    assert hx_events(r) == FORECAST_LEDGER
    assert r.headers["HX-Reswap"] == "none"
    row = query(
        _migrated,
        "SELECT default_amount, cadence FROM recurring_rules WHERE id = ?",
        (seeded["rule"],),
    )[0]
    assert (row[0], row[1]) == (1200, "yearly")
    assert audit_ops(_migrated, "recurring_rule", seeded["rule"]) == ["create", "update"]


@covers("POST /recurring/{rule_id}")
def test_update_errors(client: TestClient, seeded: Ids, _migrated: Settings) -> None:
    rid = seeded["rule"]
    assert (
        client.post(f"/recurring/{rid}", data=rule_form(seeded, cadence="bogus")).status_code == 422
    )
    assert (
        client.post(f"/recurring/{rid}", data=rule_form(seeded, account_id="x")).status_code == 422
    )
    assert client.post("/recurring/99999", data=rule_form(seeded)).status_code == 404
    assert (
        scalar(_migrated, "SELECT default_amount FROM recurring_rules WHERE id = ?", (rid,))
        == 50000
    )


@covers("POST /recurring/{rule_id}/deactivate")
def test_deactivate_soft_deletes_the_rule(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    r = client.post(f"/recurring/{seeded['rule']}/deactivate")
    assert r.status_code == 200
    assert r.text == ""
    assert hx_events(r) == FORECAST_LEDGER
    assert (
        scalar(_migrated, "SELECT active FROM recurring_rules WHERE id = ?", (seeded["rule"],)) == 0
    )
    assert len(audit_ops(_migrated, "recurring_rule", seeded["rule"])) == 2
    assert client.post("/recurring/99999/deactivate").status_code == 404


@covers(
    "GET /recurring/{rule_id}/overrides/new",
    "POST /recurring/{rule_id}/overrides",
    "POST /recurring/{rule_id}/overrides/{occurrence_date}/delete",
)
def test_override_add_and_delete_round_trip(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    rid = seeded["rule"]
    form = client.get(f"/recurring/{rid}/overrides/new", headers=HTMX)
    assert form.status_code == 200
    assert "<html" not in form.text
    assert client.get("/recurring/99999/overrides/new").status_code == 404

    due = date.fromisoformat(_next_due(_migrated, rid))
    added = client.post(
        f"/recurring/{rid}/overrides",
        data={"year": due.year, "month": due.month, "amount": "42,50"},
    )
    assert added.status_code == 200
    assert hx_events(added) == FORECAST_LEDGER
    assert added.headers["HX-Reswap"] == "none"
    occ = scalar(
        _migrated,
        "SELECT occurrence_date FROM recurring_rule_overrides WHERE rule_id = ?",
        (rid,),
    )
    assert (
        scalar(
            _migrated,
            "SELECT amount_override FROM recurring_rule_overrides WHERE rule_id = ?",
            (rid,),
        )
        == 4250
    )
    assert audit_ops(
        _migrated,
        "recurring_override",
        scalar(_migrated, "SELECT id FROM recurring_rule_overrides WHERE rule_id = ?", (rid,)),
    )

    removed = client.post(f"/recurring/{rid}/overrides/{occ}/delete")
    assert removed.status_code == 200
    assert hx_events(removed) == FORECAST_LEDGER
    assert (
        scalar(_migrated, "SELECT COUNT(*) FROM recurring_rule_overrides WHERE rule_id = ?", (rid,))
        == 0
    )


@covers(
    "POST /recurring/{rule_id}/overrides",
    "POST /recurring/{rule_id}/overrides/{occurrence_date}/delete",
)
def test_override_errors(client: TestClient, seeded: Ids, _migrated: Settings) -> None:
    rid = seeded["rule"]
    base = {"year": 2026, "month": 5, "amount": "10"}
    for bad in ({"month": 13}, {"year": 1800}, {"amount": "abc"}, {"amount": "0"}):
        r = client.post(f"/recurring/{rid}/overrides", data={**base, **bad})
        assert r.status_code == 422, bad
    assert client.post("/recurring/99999/overrides", data=base).status_code == 404
    assert client.post(f"/recurring/{rid}/overrides/not-a-date/delete").status_code == 422
    assert client.post("/recurring/99999/overrides/2026-05-01/delete").status_code == 404
    assert scalar(_migrated, "SELECT COUNT(*) FROM recurring_rule_overrides") == 0


@covers("POST /recurring/formula/preview")
def test_formula_preview_statuses(client: TestClient, seeded: Ids, _migrated: Settings) -> None:
    # a formula source must be a category with history: give `inc` a rule first
    client.post("/recurring", data=rule_form(seeded, category_id=seeded["inc"]))
    ok = client.post(
        "/recurring/formula/preview",
        data={
            "terms[0][sign]": "+",
            "terms[0][coefficient_percent]": "25",
            "terms[0][source_category_ids]": str(seeded["inc"]),
        },
    )
    assert ok.status_code == 200
    assert "<html" not in ok.text
    assert client.post("/recurring/formula/preview", data={}).status_code == 422
    assert client.post("/recurring/formula/preview", data={"draft_rule_id": "x"}).status_code == 422
    bad_src = client.post(
        "/recurring/formula/preview",
        data={
            "terms[0][sign]": "+",
            "terms[0][coefficient_percent]": "25",
            "terms[0][source_category_ids]": "nope",
        },
    )
    assert bad_src.status_code == 422
    # preview never writes
    assert scalar(_migrated, "SELECT COUNT(*) FROM recurring_rules") == 2


@covers("GET /recurring/{rule_id}/promote", "GET /recurring/{rule_id}/promote/inline")
def test_promote_forms_and_unknown_id(client: TestClient, seeded: Ids) -> None:
    rid = seeded["rule"]
    assert client.get(f"/recurring/{rid}/promote", headers=HTMX).status_code == 200
    inline = client.get(
        f"/recurring/{rid}/promote/inline", params={"date": "2026-05-01"}, headers=HTMX
    )
    assert inline.status_code == 200
    assert "<html" not in inline.text
    assert client.get("/recurring/99999/promote").status_code == 404
    assert client.get("/recurring/99999/promote/inline").status_code == 404


@covers("POST /recurring/{rule_id}/promote")
def test_promote_creates_transaction_and_advances_rule(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    rid = seeded["rule"]
    due_before = _next_due(_migrated, rid)
    txns_before = scalar(_migrated, "SELECT COUNT(*) FROM transactions")
    r = client.post(
        f"/recurring/{rid}/promote",
        data={"operation_date": "2026-11-02", "amount": "33", "description": "promoted rule"},
    )
    assert r.status_code == 200
    assert hx_events(r) == PROMOTE_EVENTS
    assert r.headers["HX-Reswap"] == "none"
    assert scalar(_migrated, "SELECT COUNT(*) FROM transactions") == txns_before + 1
    assert _next_due(_migrated, rid) > due_before
    assert audit_ops(_migrated, "recurring_rule", rid)[-1] == "update"


@covers("POST /recurring/{rule_id}/promote")
def test_promote_errors(client: TestClient, seeded: Ids, _migrated: Settings) -> None:
    rid = seeded["rule"]
    assert (
        client.post(f"/recurring/{rid}/promote", data={"operation_date": "nope"}).status_code == 422
    )
    assert client.post(f"/recurring/{rid}/promote", data={"amount": "-1"}).status_code == 422
    assert client.post(f"/recurring/{rid}/promote", data={"amount": "abc"}).status_code == 422
    assert client.post("/recurring/99999/promote", data={}).status_code == 404
    client.post(f"/recurring/{rid}/deactivate")
    assert client.post(f"/recurring/{rid}/promote", data={}).status_code == 422  # inactive


@covers("POST /recurring/{rule_id}/skip-next")
def test_skip_next_advances_without_a_transaction(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    rid = seeded["rule"]
    due_before = _next_due(_migrated, rid)
    txns_before = scalar(_migrated, "SELECT COUNT(*) FROM transactions")
    r = client.post(f"/recurring/{rid}/skip-next")
    assert r.status_code == 200
    assert hx_events(r) == PROMOTE_EVENTS
    assert _html.exists(r.text, ledger.recurring_row(rid))
    assert _next_due(_migrated, rid) > due_before
    assert scalar(_migrated, "SELECT COUNT(*) FROM transactions") == txns_before
    assert client.post("/recurring/99999/skip-next").status_code == 404
    client.post(f"/recurring/{rid}/deactivate")
    assert client.post(f"/recurring/{rid}/skip-next").status_code == 422


@covers("POST /recurring/batch/promote-due", "POST /recurring/batch/undo")
def test_batch_promote_due_and_undo(client: TestClient, seeded: Ids, _migrated: Settings) -> None:
    rid = seeded["rule"]
    _make_due(_migrated, rid)
    due_before = _next_due(_migrated, rid)
    r = client.post("/recurring/batch/promote-due")
    assert r.status_code == 204
    events = hx_events(r)
    toast = events["toast"]
    assert toast["undo_url"] == "/recurring/batch/undo"
    assert events["budget-stale"] is True
    payload = toast["undo_payload"]
    assert rid in payload["advanced_rule_ids"]
    assert payload["promoted_txn_ids"]
    assert _next_due(_migrated, rid) > due_before

    undo = client.post(
        "/recurring/batch/undo",
        data={
            "promoted_txn_ids": ",".join(map(str, payload["promoted_txn_ids"])),
            "advanced_rule_ids": ",".join(map(str, payload["advanced_rule_ids"])),
        },
    )
    assert undo.status_code == 204
    assert hx_events(undo)["toast"] == {"variant": "info", "message": "Undone"}
    assert _next_due(_migrated, rid) == due_before
    deleted = scalar(
        _migrated,
        "SELECT deleted_at IS NOT NULL FROM transactions WHERE id = ?",
        (payload["promoted_txn_ids"][0],),
    )
    assert deleted == 1


@covers("POST /recurring/batch/undo")
def test_batch_undo_rejects_malformed_ids(client: TestClient, seeded: Ids) -> None:
    assert client.post("/recurring/batch/undo", data={"advanced_rule_ids": "x"}).status_code == 422
