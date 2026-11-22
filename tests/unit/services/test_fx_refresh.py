"""NBP table A adapter and the shared refresh function (T-Q290, ADR-0145)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import httpx
import pytest

from budget_planner.adapters.fx import nbp
from budget_planner.config import Settings
from budget_planner.domain.fx import FxFetchError, NewFxRate, RateTable, StaleRateTableError
from budget_planner.repositories import fx as fx_repo
from budget_planner.services import fx as fx_service

DAY = date(2026, 11, 20)
EUR_ROW = {"currency": "euro", "code": "EUR", "mid": 4.2}


def _payload(**overrides: object) -> list[dict[str, object]]:
    table: dict[str, object] = {
        "table": "A",
        "no": "224/A/NBP/2026",
        "effectiveDate": "2026-11-20",
        "rates": [
            {"currency": "dolar amerykanski", "code": "USD", "mid": 3.6941},
            {"currency": "euro", "code": "EUR", "mid": 4.2655},
            {"currency": "jen", "code": "JPY", "mid": 0.02345},
            {"currency": "nieznana", "code": "ZZZ", "mid": 5.5},
        ],
    }
    table.update(overrides)
    return [table]


def _source(
    response: httpx.Response,
) -> tuple[nbp.NbpRateSource, httpx.Client, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response

    client = nbp.make_client(Settings(_env_file=None), transport=httpx.MockTransport(handler))
    return nbp.NbpRateSource(client), client, seen


def _stored(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    return [(str(r.date), r.from_ccy, str(r.rate)) for r in fx_repo.list_rates_to(conn, "PLN")]


class _Fake:
    def __init__(self, table: RateTable | None = None, error: str | None = None) -> None:
        self.table = table
        self.error = error

    def latest_table(self) -> RateTable | None:
        if self.error:
            raise FxFetchError(self.error)
        return self.table


def _table(effective: date = DAY, **rates: str) -> RateTable:
    return RateTable(
        effective_date=effective, rates=tuple((c, Decimal(r)) for c, r in sorted(rates.items()))
    )


def test_adapter_requests_table_a_and_parses_exact_rates() -> None:
    source, client, seen = _source(httpx.Response(200, json=_payload()))
    with client:
        table = source.latest_table()
    assert str(seen[0].url) == "https://api.nbp.pl/api/exchangerates/tables/A/?format=json"
    assert table == RateTable(
        effective_date=date(2026, 11, 20),
        rates=(("EUR", Decimal("4.2655")), ("JPY", Decimal("0.02345")), ("USD", Decimal("3.6941"))),
    )  # the unknown code ZZZ is skipped


def test_adapter_no_data_404_is_none() -> None:
    source, client, _ = _source(httpx.Response(404, text="404 NotFound - Brak danych"))
    with client:
        assert source.latest_table() is None


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json={"table": "A"}),
        httpx.Response(200, json=[]),
        httpx.Response(200, json=_payload(table="B")),
        httpx.Response(200, json=_payload(effectiveDate="20-11-2026")),
        httpx.Response(200, json=_payload(rates=[])),
        httpx.Response(200, json=_payload(rates=[{"code": "EUR", "mid": 0}])),
        httpx.Response(200, json=_payload(rates=[{"code": "EUR", "mid": -4.2}])),
        httpx.Response(200, json=_payload(rates=[{"code": "EUR", "mid": "abc"}])),
        httpx.Response(200, json=_payload(rates=[{"code": "EUR", "mid": "Infinity"}])),
        httpx.Response(200, json=_payload(rates=[{"code": "EUR", "mid": "NaN"}])),
        httpx.Response(200, json=_payload(rates=[{"code": "EUR", "mid": True}])),
        httpx.Response(200, json=_payload(rates=[{"code": "eur", "mid": 4.2}])),
        httpx.Response(200, json=_payload(rates=[EUR_ROW, {"code": "EUR", "mid": 4.3}])),
    ],
)
def test_adapter_rejects_malformed_payload(response: httpx.Response) -> None:
    source, client, _ = _source(response)
    with client, pytest.raises(FxFetchError):
        source.latest_table()


def test_adapter_unreachable_is_fetch_error() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = nbp.make_client(Settings(_env_file=None), transport=httpx.MockTransport(boom))
    with client, pytest.raises(FxFetchError):
        nbp.NbpRateSource(client).latest_table()


def test_refresh_inserts_exact_rows_and_second_run_is_idempotent(conn: sqlite3.Connection) -> None:
    source = _Fake(_table(EUR="4.2655", USD="3.6941"))
    first = fx_service.refresh_from_source(conn, source, DAY, "PLN")
    assert first is not None
    assert (first.inserted, first.updated, first.unchanged) == (("EUR", "USD"), (), ())
    assert _stored(conn) == [("2026-11-20", "EUR", "4.2655"), ("2026-11-20", "USD", "3.6941")]
    second = fx_service.refresh_from_source(conn, source, DAY, "PLN")
    assert second is not None
    assert (second.inserted, second.updated, second.unchanged) == ((), (), ("EUR", "USD"))
    assert len(_stored(conn)) == 2
    audit = conn.execute("SELECT COUNT(*) FROM audit_log WHERE entity_type = 'fx_rate'")
    assert audit.fetchone()[0] == 2


def test_refresh_updates_only_changed_rate_and_filters_currencies(conn: sqlite3.Connection) -> None:
    fx_repo.upsert_rate(
        conn, NewFxRate(date=DAY, from_ccy="EUR", to_ccy="PLN", rate=Decimal("4.0"))
    )
    result = fx_service.refresh_from_source(
        conn, _Fake(_table(EUR="4.2655", USD="3.6941")), DAY, "PLN", ["EUR"]
    )
    assert result is not None
    assert (result.inserted, result.updated) == ((), ("EUR",))
    assert _stored(conn) == [("2026-11-20", "EUR", "4.2655")]


def test_holiday_no_data_keeps_last_cached_rate(conn: sqlite3.Connection) -> None:
    fx_service.refresh_from_source(conn, _Fake(_table(EUR="4.2655")), DAY, "PLN")
    assert fx_service.refresh_from_source(conn, _Fake(None), date(2026, 11, 21), "PLN") is None
    assert _stored(conn) == [("2026-11-20", "EUR", "4.2655")]
    converter = fx_service.converter_for(conn, Settings(_env_file=None), date(2026, 11, 22))
    assert converter.rate_for("EUR") == Decimal("4.2655")


def test_stale_table_on_weekend_stores_nothing_new(conn: sqlite3.Connection) -> None:
    fx_service.refresh_from_source(conn, _Fake(_table(EUR="4.2655")), DAY, "PLN")
    again = fx_service.refresh_from_source(
        conn, _Fake(_table(EUR="4.2655")), date(2026, 11, 22), "PLN"
    )
    assert again is not None
    assert again.inserted == ()
    assert len(_stored(conn)) == 1


def test_source_failure_raises_and_cache_unchanged(conn: sqlite3.Connection) -> None:
    with pytest.raises(FxFetchError, match="boom"):
        fx_service.refresh_from_source(conn, _Fake(error="boom"), DAY, "PLN")
    assert _stored(conn) == []


def test_future_dated_table_is_rejected(conn: sqlite3.Connection) -> None:
    future = _Fake(_table(date(2026, 11, 21), EUR="4.2"))
    with pytest.raises(FxFetchError, match="after today"):
        fx_service.refresh_from_source(conn, future, DAY, "PLN")
    assert _stored(conn) == []


def test_non_pln_base_is_refused(conn: sqlite3.Connection) -> None:
    with pytest.raises(FxFetchError, match="PLN only"):
        fx_service.refresh_from_source(conn, _Fake(_table(USD="3.7")), DAY, "EUR")


def test_non_positive_rate_is_rejected_and_nothing_stored(conn: sqlite3.Connection) -> None:
    bad = RateTable(effective_date=DAY, rates=(("EUR", Decimal("4.2")), ("USD", Decimal("0"))))
    with pytest.raises(ValueError, match="fx rate"):
        fx_service.refresh_from_source(conn, _Fake(bad), DAY, "PLN")
    assert _stored(conn) == []  # the whole table rolled back


def test_has_rate_on(conn: sqlite3.Connection) -> None:
    assert not fx_service.has_rate_on(conn, "PLN", DAY)
    fx_service.refresh_from_source(conn, _Fake(_table(EUR="4.2")), DAY, "PLN")
    assert fx_service.has_rate_on(conn, "PLN", DAY)
    assert not fx_service.has_rate_on(conn, "PLN", date(2026, 11, 21))


@pytest.mark.parametrize("url", ["ftp://api.nbp.pl", "https://operator@api.nbp.pl", "api.nbp.pl"])
def test_fx_api_url_is_validated(url: str) -> None:
    with pytest.raises(ValueError, match="fx_api_url"):
        Settings(_env_file=None, fx_api_url=url)


def test_stale_table_is_rejected_whole_without_rows_or_audit(conn: sqlite3.Connection) -> None:
    fx_service.refresh_from_source(conn, _Fake(_table(EUR="4.2655")), DAY, "PLN")
    audit_sql = "SELECT COUNT(*) FROM audit_log WHERE entity_type = 'fx_rate'"
    before_audit = conn.execute(audit_sql).fetchone()[0]
    stale = _Fake(_table(DAY, EUR="4.9999", USD="3.6941"))
    with pytest.raises(StaleRateTableError, match="more than 7 days"):
        fx_service.refresh_from_source(conn, stale, date(2026, 11, 28), "PLN")
    assert _stored(conn) == [("2026-11-20", "EUR", "4.2655")]
    assert conn.execute(audit_sql).fetchone()[0] == before_audit


def test_table_exactly_at_the_age_limit_is_accepted(conn: sqlite3.Connection) -> None:
    result = fx_service.refresh_from_source(
        conn, _Fake(_table(DAY, EUR="4.2")), date(2026, 11, 27), "PLN"
    )
    assert result is not None
    assert result.inserted == ("EUR",)


def test_max_table_age_is_configurable(conn: sqlite3.Connection) -> None:
    with pytest.raises(StaleRateTableError):
        fx_service.refresh_from_source(
            conn, _Fake(_table(DAY, EUR="4.2")), date(2026, 11, 23), "PLN", max_table_age_days=2
        )
    assert StaleRateTableError.reason == "stale_table"
