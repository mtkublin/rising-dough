"""NBP table A adapter: the only place that talks HTTP for FX (ADR-0145).

``make_client`` is the single client factory (production and tests alike; tests
pass ``httpx.MockTransport``) and always sets ``base_url``. ``NbpRateSource``
implements the ``RateSource`` port. Every failure surfaces as ``FxFetchError``.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from typing import Final

import httpx

from budget_planner.config import Settings
from budget_planner.domain.fx import FxFetchError, RateTable, validate_rate
from budget_planner.domain.money import ISO_4217_CURRENCIES

logger = logging.getLogger(__name__)

HTTP_TIMEOUT_SECONDS: Final = 10.0
MAX_BODY_BYTES: Final = 1_000_000  # the real table is about 15 KB
TABLE_A_PATH: Final = "/api/exchangerates/tables/A/"
_CODE_RE: Final = re.compile(r"[A-Z]{3}", re.ASCII)
_KNOWN_CODES: Final = frozenset(ISO_4217_CURRENCIES)


def make_client(
    settings: Settings, *, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    """Build the FX client bound to ``settings.fx_api_url``."""
    return httpx.Client(
        base_url=settings.fx_api_url,
        timeout=HTTP_TIMEOUT_SECONDS,
        follow_redirects=False,
        transport=transport,
    )


def _parse_date(raw: object) -> dt.date:
    if not isinstance(raw, str):
        raise FxFetchError("nbp payload effectiveDate is not a string")
    try:
        return dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise FxFetchError(f"nbp payload effectiveDate is invalid: {raw!r}") from exc


def _parse_row(row: object) -> tuple[str, Decimal]:
    if not isinstance(row, dict):
        raise FxFetchError("nbp payload rate row is not an object")
    code, mid = row.get("code"), row.get("mid")
    if not isinstance(code, str) or _CODE_RE.fullmatch(code) is None:
        raise FxFetchError(f"nbp payload has an invalid currency code: {code!r}")
    if isinstance(mid, bool) or not isinstance(mid, (int, float, str)):
        raise FxFetchError(f"nbp payload rate for {code} is not a number")
    try:
        # Always via str() to avoid float drift (ADR-0006 risk note).
        return code, validate_rate(Decimal(str(mid)))
    except (InvalidOperation, ValueError) as exc:
        raise FxFetchError(f"nbp payload rate for {code} is invalid: {exc}") from exc


def _parse_rows(raw_rates: object) -> tuple[tuple[str, Decimal], ...]:
    if not isinstance(raw_rates, list) or not raw_rates:
        raise FxFetchError("nbp payload has no rates")
    parsed = [_parse_row(row) for row in raw_rates]
    codes = [code for code, _ in parsed]
    if len(set(codes)) != len(codes):
        raise FxFetchError("nbp payload repeats a currency code")
    skipped = sorted(set(codes) - _KNOWN_CODES)
    if skipped:
        logger.warning("nbp table skipped unknown codes: %s", ",".join(skipped))
    return tuple(sorted((c, r) for c, r in parsed if c in _KNOWN_CODES))


def parse_table_a(payload: object) -> RateTable:
    """Validate an NBP table A answer and return it; any defect rejects the whole payload."""
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise FxFetchError("nbp payload is not a one-table list")
    table = payload[0]
    if table.get("table") != "A":
        raise FxFetchError(f"nbp payload is not table A: {table.get('table')!r}")
    return RateTable(
        effective_date=_parse_date(table.get("effectiveDate")),
        rates=_parse_rows(table.get("rates")),
    )


@dataclass(frozen=True, slots=True)
class NbpRateSource:
    """``RateSource`` over NBP's latest table A."""

    client: httpx.Client

    def latest_table(self) -> RateTable | None:
        try:
            response = self.client.get(TABLE_A_PATH, params={"format": "json"})
            if response.status_code == HTTPStatus.NOT_FOUND:
                return None  # NBP: "Brak danych" (no data); the cache keeps the last rates
            response.raise_for_status()
            if len(response.content) > MAX_BODY_BYTES:
                raise FxFetchError("nbp response is too large")
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise FxFetchError(f"nbp fetch failed: {exc}") from exc
        return parse_table_a(payload)


@contextlib.contextmanager
def open_source(settings: Settings) -> Iterator[NbpRateSource]:
    """A ``NbpRateSource`` over a client that is closed on exit (the daily task's opener)."""
    with make_client(settings) as client:
        yield NbpRateSource(client)
