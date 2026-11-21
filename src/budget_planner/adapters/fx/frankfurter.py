"""Frankfurter (ECB) live-rate adapter (ADR-0139).

The only place that talks HTTP for FX. ``make_client`` is the single client
factory (production and tests alike; tests pass ``httpx.MockTransport``) and
always sets ``base_url`` so the relative ``/<date>`` request resolves.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

import httpx

from budget_planner.config import Settings
from budget_planner.domain.fx import FxFetchError, RateFetcher, validate_rate

HTTP_TIMEOUT_SECONDS = 5.0


def make_client(
    settings: Settings, *, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    """Build the FX client bound to ``settings.fx_api_url``."""
    return httpx.Client(
        base_url=settings.fx_api_url, timeout=HTTP_TIMEOUT_SECONDS, transport=transport
    )


def parse_remote_quote(payload: object, to_ccy: str) -> Decimal:
    """Pull ``rates[to_ccy]`` out of a frankfurter response as a validated Decimal."""
    if not isinstance(payload, dict):
        raise FxFetchError("fx payload is not an object")
    rates = payload.get("rates")
    if not isinstance(rates, dict) or to_ccy not in rates:
        raise FxFetchError(f"fx payload has no rate for {to_ccy}")
    try:
        # Always via str() to avoid float drift (ADR-0006 risk note).
        return validate_rate(Decimal(str(rates[to_ccy])))
    except (InvalidOperation, ValueError) as exc:
        raise FxFetchError(f"fx payload rate for {to_ccy} is invalid: {exc}") from exc


def fetch_quote(client: httpx.Client, on_date: dt.date, from_ccy: str, to_ccy: str) -> Decimal:
    """GET one historical rate; every failure surfaces as ``FxFetchError``."""
    try:
        response = client.get(f"/{on_date.isoformat()}", params={"from": from_ccy, "to": to_ccy})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise FxFetchError(f"fx fetch {from_ccy}->{to_ccy} failed: {exc}") from exc
    return parse_remote_quote(payload, to_ccy)


def make_fetcher(client: httpx.Client) -> RateFetcher:
    """Bind ``client`` into the ``RateFetcher`` port used by ``services.fx.refresh_rates``."""

    def _fetch(on_date: dt.date, from_ccy: str, to_ccy: str) -> Decimal:
        return fetch_quote(client, on_date, from_ccy, to_ccy)

    return _fetch
