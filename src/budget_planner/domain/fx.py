"""FX rate entity + New DTO (ADR-0006 / ADR-0008 / ADR-0139)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


class FxFetchError(RuntimeError):
    """A live rate could not be fetched or the provider's answer was unusable."""


class StaleRateTableError(FxFetchError):
    """A published table is dated too long before today and is rejected whole (ADR-0145)."""

    reason = "stale_table"


#: Default for ``Settings.fx_max_table_age_days`` (same value, ADR-0145 amendment 2026-11-22).
DEFAULT_MAX_TABLE_AGE_DAYS = 7


def validate_rate(rate: Decimal) -> Decimal:
    """Return ``rate`` when it is a finite number greater than zero, else raise ``ValueError``."""
    if not rate.is_finite() or rate <= 0:
        raise ValueError(f"fx rate must be a finite number > 0, got {rate}")
    return rate


@dataclass(frozen=True, slots=True, kw_only=True)
class RateTable:
    """One published rate table: ``rates`` are ``(code, PLN per one unit)`` pairs (ADR-0145).

    Every rate is finite and ``> 0`` and every code appears once; the adapter
    guarantees this, the service re-checks it before storing.
    """

    effective_date: date
    rates: tuple[tuple[str, Decimal], ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class FxRate:
    """Append-only exchange rate for a specific (date, from_ccy, to_ccy)."""

    id: int
    date: date
    from_ccy: str
    to_ccy: str
    rate: Decimal
    fetched_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class NewFxRate:
    """Insertable fields for a new FX rate (``rate`` must be finite and > 0)."""

    date: date
    from_ccy: str
    to_ccy: str
    rate: Decimal

    def __post_init__(self) -> None:
        validate_rate(self.rate)
