"""Contract: /ledger page + fragments (ADR-0106 section 1, T-UT04c)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from budget_planner.config import Settings
from tests.contract.conftest import covers
from tests.ui_map import _html, ledger

Ids = dict[str, int]


@covers("GET /ledger")
def test_ledger_page_renders_each_view(client: TestClient, seeded: Ids) -> None:
    for view in ("actual", "planned", "recurring"):
        r = client.get("/ledger", params={"view": view})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert _html.exists(r.text, ledger.heading)
        assert _html.exists(r.text, ledger.table_container)


@covers("GET /ledger")
def test_ledger_unknown_view_is_422_and_empty_view_is_actual(
    client: TestClient, seeded: Ids
) -> None:
    assert client.get("/ledger", params={"view": "bogus"}).status_code == 422
    r = client.get("/ledger", params={"view": ""})
    assert r.status_code == 200
    assert _html.exists(r.text, ledger.row(seeded["txn"]))


@covers("GET /ledger", "GET /ledger/table")
def test_ledger_filters_and_pagination(client: TestClient, seeded: Ids) -> None:
    hit = client.get("/ledger/table", params={"q": "seed txn"})
    miss = client.get("/ledger/table", params={"q": "no-such-description"})
    assert _html.exists(hit.text, ledger.row(seeded["txn"]))
    assert not _html.exists(miss.text, ledger.row(seeded["txn"]))
    by_account = client.get("/ledger/table", params={"account_id": seeded["acc2"]})
    assert not _html.exists(by_account.text, ledger.row(seeded["txn"]))
    # page_size is clamped; a malformed value is a 422 (T-Q282), never a silent default.
    assert client.get("/ledger", params={"page_size": "99999"}).status_code == 200
    odd = client.get("/ledger", params={"page": "x", "date_from": "nope"})
    assert odd.status_code == 422


@covers("GET /ledger/table")
def test_ledger_table_is_a_fragment_per_view(client: TestClient, seeded: Ids) -> None:
    actual = client.get("/ledger/table")
    assert actual.status_code == 200
    assert "<html" not in actual.text
    assert _html.exists(actual.text, ledger.row(seeded["txn"]))
    planned = client.get("/ledger/table", params={"view": "planned"})
    assert _html.exists(planned.text, ledger.planned_row(seeded["pl"]))
    recurring = client.get("/ledger/table", params={"view": "recurring"})
    assert _html.exists(recurring.text, ledger.recurring_row(seeded["rule"]))


@covers("GET /ledger/recently-deleted")
def test_recently_deleted_lists_soft_deleted_rows(
    client: TestClient, seeded: Ids, _migrated: Settings
) -> None:
    empty = client.get("/ledger/recently-deleted")
    assert empty.status_code == 200
    assert _html.exists(empty.text, ledger.recently_deleted_heading)
    assert not _html.exists(empty.text, ledger.deleted_row("txn", seeded["txn"]))
    client.post(f"/transactions/{seeded['txn']}/delete")
    after = client.get("/ledger/recently-deleted")
    assert after.status_code == 200
    assert _html.exists(after.text, ledger.restore("txn", seeded["txn"]))


@covers("GET /ledger/recently-deleted/panel")
def test_recently_deleted_panel_lists_the_deleted_row(client: TestClient, seeded: Ids) -> None:
    client.post(f"/transactions/{seeded['txn']}/delete")
    panel = client.get("/ledger/recently-deleted/panel")
    assert panel.status_code == 200
    assert "<html" not in panel.text
    assert _html.exists(panel.text, ledger.restore("txn", seeded["txn"]))
