"""FxConverter, refresh path and live client factory (T-Q212, ADR-0139)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import httpx
import pytest

from budget_planner.adapters.fx import frankfurter
from budget_planner.config import Settings
from budget_planner.domain.fx import FxFetchError, NewFxRate
from budget_planner.repositories import fx as fx_repo
from budget_planner.services import fx as fx_service
from budget_planner.services.fx import FxUnavailableError

DAY = date(2026, 2, 1)


def _put(conn: sqlite3.Connection, on: date, rate: str, ccy: str = "EUR") -> None:
    fx_repo.upsert_rate(conn, NewFxRate(date=on, from_ccy=ccy, to_ccy="PLN", rate=Decimal(rate)))


def _converter(conn: sqlite3.Connection) -> fx_service.FxConverter:
    return fx_service.converter_for(conn, Settings(_env_file=None), DAY)


def test_identity_needs_no_rate(conn: sqlite3.Connection) -> None:
    assert _converter(conn).to_base(12_345, "PLN") == 12_345


def test_exact_date_then_latest_on_or_before(conn: sqlite3.Connection) -> None:
    _put(conn, date(2026, 1, 15), "4.28")
    _put(conn, DAY, "4.40")
    _put(conn, date(2026, 2, 20), "9.99")
    fx = _converter(conn)
    assert fx.rate_for("EUR", DAY) == Decimal("4.40")
    assert fx.rate_for("EUR", date(2026, 1, 20)) == Decimal("4.28")
    assert fx.rate_for("EUR") == Decimal("4.40")  # reference day, never the future row


def test_missing_rate_raises_never_rate_one(conn: sqlite3.Connection) -> None:
    fx = _converter(conn)
    with pytest.raises(FxUnavailableError, match="EUR->PLN"):
        fx.to_base(100, "EUR")
    _put(conn, date(2026, 3, 1), "4")  # only a later rate cached
    with pytest.raises(FxUnavailableError):
        _converter(conn).to_base(100, "EUR", DAY)


def test_rounds_half_even_and_preserves_sign(conn: sqlite3.Connection) -> None:
    _put(conn, DAY, "0.5")
    fx = _converter(conn)
    assert fx.to_base(5, "EUR") == 2  # 0.025 PLN -> 2.5 grosz -> half even
    assert fx.to_base(7, "EUR") == 4  # 3.5 -> 4
    assert fx.to_base(-7, "EUR") == -4


def test_zero_decimal_currency(conn: sqlite3.Connection) -> None:
    _put(conn, DAY, "0.0275", "JPY")
    assert _converter(conn).to_base(10_000, "JPY") == 27_500


@pytest.mark.parametrize("bad", ["0", "-1", "NaN", "Infinity"])
def test_new_rate_rejects_non_positive_or_non_finite(bad: str) -> None:
    with pytest.raises(ValueError, match="fx rate"):
        NewFxRate(date=DAY, from_ccy="EUR", to_ccy="PLN", rate=Decimal(bad))


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return frankfurter.make_client(Settings(_env_file=None), transport=handler)


def test_client_factory_sets_base_url_and_fetch_succeeds() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"rates": {"PLN": 4.2655}})

    with _client(httpx.MockTransport(handler)) as client:
        rate = frankfurter.fetch_quote(client, DAY, "EUR", "PLN")
    assert rate == Decimal("4.2655")
    assert str(seen[0].url) == "https://api.frankfurter.app/2026-02-01?from=EUR&to=PLN"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, json=[1]),
        httpx.Response(200, json={"rates": []}),
        httpx.Response(200, json={"rates": {"USD": 1}}),
        httpx.Response(200, json={"rates": {"PLN": 0}}),
        httpx.Response(200, json={"rates": {"PLN": "abc"}}),
        httpx.Response(200, content=b"not json"),
    ],
)
def test_fetch_failures_surface_as_fetch_error(response: httpx.Response) -> None:
    with _client(httpx.MockTransport(lambda _r: response)) as client, pytest.raises(FxFetchError):
        frankfurter.fetch_quote(client, DAY, "EUR", "PLN")


def test_unreachable_provider_is_fetch_error() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with _client(httpx.MockTransport(boom)) as client, pytest.raises(FxFetchError):
        frankfurter.fetch_quote(client, DAY, "EUR", "PLN")


def test_refresh_caches_rate_and_converter_sees_it(conn: sqlite3.Connection) -> None:
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, json={"rates": {"PLN": "4.5"}}))
    with _client(transport) as client:
        outcomes = fx_service.refresh_rates(
            conn, frankfurter.make_fetcher(client), DAY, "PLN", ["EUR", "PLN", "EUR"]
        )
    assert [(o.from_ccy, o.rate, o.error) for o in outcomes] == [("EUR", Decimal("4.5"), None)]
    assert _converter(conn).to_base(1_000, "EUR") == 4_500


def test_refresh_reports_failures_and_stores_nothing(conn: sqlite3.Connection) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["from"] == "USD":
            return httpx.Response(200, json={"rates": {"PLN": "-3"}})
        return httpx.Response(503)

    with _client(httpx.MockTransport(handler)) as client:
        outcomes = fx_service.refresh_rates(
            conn, frankfurter.make_fetcher(client), DAY, "PLN", ["EUR", "USD"]
        )
    assert all(o.rate is None and o.error for o in outcomes)
    assert fx_repo.list_rates_to(conn, "PLN") == []
