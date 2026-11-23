"""Ports for effects the pure layers must not perform themselves (ADR-0021 amendment).

Entropy comes in through :class:`TokenSource`; the adapter over the stdlib CSPRNG lives in
``adapters/entropy.py``. Password hashing comes in through :class:`PasswordHasher`; the bcrypt
adapter lives in ``adapters/bcrypt_hasher.py`` (T-Q291). Both are injected at the web edge; tests
inject deterministic fakes. Live FX rates come in through :class:`RateSource` (ADR-0145); the NBP
adapter lives in ``adapters/fx/nbp.py``. Outbound mail comes in through :class:`MailSender`
(T-UR31, ADR-0134 section 1); the only adapter today is the no-op in ``adapters/mail/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

from budget_planner.domain.fx import RateTable

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

    def needs_rehash(self, hashed: str | None) -> bool:
        """``True`` iff ``hashed`` was made at a cost other than the configured one (T-Q313)."""
        ...

    def verify_dummy(self, password: str) -> None:
        """Burn one verify's worth of CPU (unknown user / no hash) to equalize timing."""
        ...


class RateSource(Protocol):
    """A provider of the latest published FX rate table (PLN per unit)."""

    def latest_table(self) -> RateTable | None:
        """Return the latest table, or ``None`` when the provider has no data.

        Raises ``FxFetchError`` when the provider is unreachable or its answer is unusable.
        """
        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class MailMessage:
    """One plain-text message. The body may carry a secret link: never log or repr it."""

    to: str
    subject: str
    body: str

    def __repr__(self) -> str:
        return "MailMessage(<redacted>)"


class MailSendError(Exception):
    """The mail provider is unreachable or refused the message."""


class MailSender(Protocol):
    """Sends one message (T-UR31). The default adapter does nothing."""

    def send(self, message: MailMessage) -> None:
        """Deliver ``message``.

        Raises :class:`MailSendError` when delivery fails.
        """
        ...
