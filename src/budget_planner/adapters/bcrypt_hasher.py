"""bcrypt adapter for the :class:`~budget_planner.domain.ports.PasswordHasher` port (T-Q291).

- :meth:`BcryptHasher.hash` uses bcrypt at :attr:`BcryptHasher.rounds` (production default 12).
- :meth:`BcryptHasher.verify` is a constant-time check that **never raises** on bad input
  (malformed hash, ``None``, over-long password); it returns ``False`` instead.
- :meth:`BcryptHasher.verify_dummy` verifies against a precomputed hash of a discarded secret at
  the same cost, closing the user-enumeration timing oracle.
- :meth:`BcryptHasher.needs_rehash` reports a stored hash made at another cost (T-Q313).

bcrypt ignores everything past 72 bytes; rather than silently truncating, such passwords are
rejected (``ValueError`` on hash, ``False`` on verify).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

import bcrypt

from budget_planner.domain.ports import MAX_PASSWORD_BYTES

DEFAULT_ROUNDS: Final = 12
MIN_ROUNDS: Final = 4
MAX_ROUNDS: Final = 31

_LOG = logging.getLogger(__name__)

# Precomputed bcrypt hashes of random, discarded secrets, keyed by cost. Costs outside the table
# (never used by the app) are derived per call.
_DUMMY_HASHES: Final[Mapping[int, str]] = MappingProxyType(
    {
        4: "$2b$04$g75.0jLY6jrCTFTLTqRQNOGShNJeoNoIg7MyrZ6jWLrate3MzUOsu",
        12: "$2b$12$9fyBN20Uq9OnIZV2HfQivuWqvBdA08Vh8.DBes5U4PrBHd7ELkQTe",
    }
)


_COST_PREFIX: Final = re.compile(r"^\$2[abxy]\$(\d{2})\$")


def _encode(plain: str) -> bytes:
    raw = plain.encode()
    if len(raw) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password exceeds {MAX_PASSWORD_BYTES} bytes (bcrypt limit)")
    return raw


@dataclass(frozen=True, slots=True)
class BcryptHasher:
    """The only production ``PasswordHasher``; ``rounds`` is the bcrypt cost."""

    rounds: int = DEFAULT_ROUNDS

    def __post_init__(self) -> None:
        if not MIN_ROUNDS <= self.rounds <= MAX_ROUNDS:
            raise ValueError(
                f"bcrypt rounds must be in {MIN_ROUNDS}..{MAX_ROUNDS}, got {self.rounds}"
            )

    def hash(self, password: str) -> str:
        if not password:
            raise ValueError("password must not be empty")
        salt = bcrypt.gensalt(rounds=self.rounds)
        return bcrypt.hashpw(_encode(password), salt).decode("ascii")

    def verify(self, password: str, hashed: str | None) -> bool:
        if not password or not hashed:
            return False
        try:
            return bcrypt.checkpw(_encode(password), hashed.encode("ascii"))
        except (ValueError, TypeError, UnicodeEncodeError) as exc:
            _LOG.debug("password verify rejected input: %s", type(exc).__name__)
            return False

    def needs_rehash(self, hashed: str | None) -> bool:
        """``True`` iff ``hashed`` is bcrypt at a cost other than :attr:`rounds` (T-Q313)."""
        match = _COST_PREFIX.match(hashed or "")
        return match is not None and int(match.group(1)) != self.rounds

    def verify_dummy(self, password: str) -> None:
        known = _DUMMY_HASHES.get(self.rounds)
        dummy = known if known is not None else self.hash("dummy-timing-secret")
        self.verify(password, dummy)
