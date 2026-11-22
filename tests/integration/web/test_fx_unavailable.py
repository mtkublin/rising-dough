"""ADR-0139: a missing FX rate is a visible 503, never a wrong number; renders never fetch."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from budget_planner.adapters.fx import nbp
from budget_planner.cli import refresh_fx
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.repositories import accounts as accounts_repo, fx as fx_repo
from tests.ui_map import _html

USER_ID = 1


def _eur_account(settings: Settings) -> None:
    conn = get_connection(settings)
    try:
        accounts_repo.create(
            conn, USER_ID, NewAccount(name="Euro", currency="EUR", opening_balance=100_000)
        )
    finally:
        conn.close()


@pytest.mark.parametrize("route", ["/today", "/forecast", "/plan?tab=forecast"])
def test_page_with_foreign_account_and_no_rate_is_503_without_network(
    client: TestClient,
    _migrated: Settings,
    monkeypatch: pytest.MonkeyPatch,
    route: str,
) -> None:
    def _boom(*_a: object, **_k: object) -> None:
        raise AssertionError("network FX fetch during page render")

    monkeypatch.setattr(nbp.NbpRateSource, "latest_table", _boom)
    monkeypatch.setattr(nbp, "make_client", _boom)
    _eur_account(_migrated)
    response = client.get(route)
    assert response.status_code == 503
    assert "EUR->PLN" in _html.page_text(response.text)


def test_refresh_cli_caches_rate_and_page_then_renders(
    client: TestClient, _migrated: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    _eur_account(_migrated)
    payload = [
        {
            "table": "A",
            "effectiveDate": "2026-01-02",
            "rates": [{"currency": "euro", "code": "EUR", "mid": 4.2}],
        }
    ]
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, json=payload))
    db_path = _migrated.database_url.removeprefix("sqlite:///")
    rc = refresh_fx.main(["--db", db_path, "--currency", "EUR"], transport=transport)
    assert rc == 0
    assert "2026-01-02: inserted 1, updated 0, unchanged 0" in capsys.readouterr().out
    conn = get_connection(_migrated)
    try:
        assert [
            (str(r.date), r.from_ccy, str(r.rate)) for r in fx_repo.list_rates_to(conn, "PLN")
        ] == [("2026-01-02", "EUR", "4.2")]
    finally:
        conn.close()
    assert client.get("/today").status_code == 200
