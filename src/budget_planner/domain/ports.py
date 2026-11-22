"""Ports for effects the pure layers must not perform themselves (ADR-0021 amendment).

Entropy comes in through :class:`TokenSource`; the adapter over the stdlib CSPRNG lives in
``adapters/entropy.py``. Password hashing comes in through :class:`PasswordHasher`; the bcrypt
adapter lives in ``adapters/bcrypt_hasher.py`` (T-Q291). Both are injected at the web edge; tests
inject deterministic fakes.
"""

from __future__ import annotations

from typing import Final, Protocol

#: bcrypt ignores everything past 72 bytes; hashers reject longer passwords instead of truncating.
MAX_PASSWORD_BYTES: Final = 72


class TokenSource(Protocol):
    """A source of URL-safe random tokens."""

    def new_token(self, nbytes: int) -> str:
        """Return a URL-safe text token built from ``nbytes`` random bytes."""
        ...


class PasswordHasher(Protocol):
    """One-way password hashing with a constant-time check (ADR-0033 §2, ADR-0061)."""

    def hash(self, password: str) -> str:
        """Return the stored hash of ``password``.

        Raises ``ValueError`` for an empty password or one over :data:`MAX_PASSWORD_BYTES`.
        """
        ...

    def verify(self, password: str, hashed: str | None) -> bool:
        """Return ``True`` iff ``password`` matches ``hashed``; never raises on bad input."""
        ...

    def verify_dummy(self, password: str) -> None:
        """Burn one verify's worth of CPU (unknown user / no hash) to equalize timing."""
        ...
