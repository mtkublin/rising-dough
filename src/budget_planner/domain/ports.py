"""Ports for effects the pure layers must not perform themselves (ADR-0021 amendment).

Entropy comes in through :class:`TokenSource`; the adapter over the stdlib CSPRNG lives in
``adapters/entropy.py`` and is injected at the web edge. Tests inject a deterministic fake.
Live FX rates come in through :class:`RateSource` (ADR-0145); the NBP adapter lives in
``adapters/fx/nbp.py``.
"""

from __future__ import annotations

from typing import Protocol

from budget_planner.domain.fx import RateTable


class TokenSource(Protocol):
    """A source of URL-safe random tokens."""

    def new_token(self, nbytes: int) -> str:
        """Return a URL-safe text token built from ``nbytes`` random bytes."""
        ...


class RateSource(Protocol):
    """A provider of the latest published FX rate table (PLN per unit)."""

    def latest_table(self) -> RateTable | None:
        """Return the latest table, or ``None`` when the provider has no data.

        Raises ``FxFetchError`` when the provider is unreachable or its answer is unusable.
        """
        ...
