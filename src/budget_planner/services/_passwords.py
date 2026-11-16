"""bcrypt password hashing helpers (ADR-0033 §2, ADR-0061, ADR-0067).

Pure functions, no I/O:

- :func:`hash_password` — bcrypt at :data:`DEFAULT_ROUNDS` (12) unless a
  lower ``rounds`` is passed. Tests monkeypatch ``DEFAULT_ROUNDS`` (or pass
  ``rounds=4``) to keep the suite fast.
- :func:`verify_password` — constant-time bcrypt check that **never
  raises** on bad input (malformed hash, ``None``-ish values, over-long
  passwords); it returns ``False`` instead.
- :func:`dummy_hash` — a cached hash of a random secret at the current
  cost, used by the auth service to burn the same CPU time when the email
  is unknown (closes the user-enumeration timing oracle).

bcrypt ignores everything past 72 bytes; rather than silently truncating
we reject such passwords explicitly (``ValueError`` on hash, ``False`` on
verify).
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Final

import bcrypt

DEFAULT_ROUNDS: int = 12
MIN_ROUNDS: Final = 4
MAX_ROUNDS: Final = 31
MAX_PASSWORD_BYTES: Final = 72


def _encode(plain: str) -> bytes:
    raw = plain.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password exceeds {MAX_PASSWORD_BYTES} bytes (bcrypt limit)")
    return raw


def hash_password(plain: str, *, rounds: int | None = None) -> str:
    """Return the bcrypt hash of ``plain`` as an ASCII string.

    Raises ``ValueError`` for an empty password, a password longer than
    72 UTF-8 bytes, or ``rounds`` outside bcrypt's ``4..31`` range.
    """
    if not plain:
        raise ValueError("password must not be empty")
    cost = DEFAULT_ROUNDS if rounds is None else rounds
    if not MIN_ROUNDS <= cost <= MAX_ROUNDS:
        raise ValueError(f"bcrypt rounds must be in {MIN_ROUNDS}..{MAX_ROUNDS}, got {cost}")
    return bcrypt.hashpw(_encode(plain), bcrypt.gensalt(rounds=cost)).decode("ascii")


def verify_password(plain: str, hashed: str | None) -> bool:
    """Return ``True`` iff ``plain`` matches the bcrypt ``hashed`` value.

    Never raises: empty / over-long passwords, missing or malformed hashes
    and non-ASCII hash strings all yield ``False``.
    """
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(_encode(plain), hashed.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError):
        return False


@lru_cache(maxsize=4)
def _dummy_hash_for(rounds: int) -> str:
    return hash_password(secrets.token_urlsafe(16), rounds=rounds)


def dummy_hash() -> str:
    """Return a throwaway hash at the current :data:`DEFAULT_ROUNDS` cost."""
    return _dummy_hash_for(DEFAULT_ROUNDS)


__all__ = [
    "DEFAULT_ROUNDS",
    "MAX_PASSWORD_BYTES",
    "dummy_hash",
    "hash_password",
    "verify_password",
]
