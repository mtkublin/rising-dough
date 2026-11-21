"""Ports for effects the pure layers must not perform themselves (ADR-0021 amendment).

Entropy comes in through :class:`TokenSource`; the adapter over the stdlib CSPRNG lives in
``adapters/entropy.py`` and is injected at the web edge. Tests inject a deterministic fake.
"""

from __future__ import annotations

from typing import Protocol


class TokenSource(Protocol):
    """A source of URL-safe random tokens."""

    def new_token(self, nbytes: int) -> str:
        """Return a URL-safe text token built from ``nbytes`` random bytes."""
        ...
