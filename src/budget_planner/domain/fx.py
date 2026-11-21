"""FX rate entity + New DTO (ADR-0006 / ADR-0008 / ADR-0139)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


class FxFetchError(RuntimeError):
    """A live rate could not be fetched or the provider's answer was unusable."""


def validate_rate(rate: Decimal) -> Decimal:
    """Return ``rate`` when it is a finite number greater than zero, else raise ``ValueError``."""
    if not rate.is_finite() or rate <= 0:
        raise ValueError(f"fx rate must be a finite number > 0, got {rate}")
    return rate


# Injected port for the live fetch: (on_date, from_ccy, to_ccy) -> rate.
# Implementations raise ``FxFetchError`` on any failure (adapters/fx).
RateFetcher = Callable[[date, str, str], Decimal]


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
