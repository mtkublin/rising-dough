"""Session-bound CSRF tokens (T-Q289, T-Q312; ADR-0065 amendments 2026-11-22 and 2026-11-23).

A token is ``nonce || issued-at || mac`` (fixed widths). The MAC is an HMAC-SHA256
keyed by the cookie secret over a context, the nonce and the issued-at:

* authenticated request: the context is the session id, so a token minted for
  one session never verifies for another, and a new session (login) or a
  cleared one (logout) makes every earlier token stale (rotation by binding);
* anonymous request (login and passkey pages): the context is the per-browser id
  (T-Q312), so a token minted for one browser never verifies for another, and
  it expires after :data:`PRE_SESSION_TOKEN_MAX_AGE`.

Verification is constant time (``hmac.compare_digest``). The module is pure: the
instant comes in as an argument.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Final

from budget_planner.domain.ports import TokenSource

_DOMAIN: Final = b"csrf-v1|"
_NONCE_BYTES: Final = 16
_NONCE_CHARS: Final = 22  # urlsafe base64 of 16 bytes, unpadded
_IAT_CHARS: Final = 8  # issued-at seconds, lower-case hex, zero padded
_MAC_CHARS: Final = 43  # urlsafe base64 of 32 bytes, unpadded
_TOKEN_CHARS: Final = _NONCE_CHARS + _IAT_CHARS + _MAC_CHARS
_PRE_SESSION: Final = b"pre|"
_SESSION: Final = b"session|"

#: A pre-session (login page) token older than this is refused (T-Q312).
PRE_SESSION_TOKEN_MAX_AGE: Final = timedelta(hours=2)
#: Tolerated clock skew for an issued-at in the future.
_FUTURE_SKEW: Final = timedelta(minutes=5)


class TokenStatus(Enum):
    """Verdict of :func:`check_token`."""

    VALID = "valid"
    EXPIRED = "expired"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class Binding:
    """What a token is bound to: a live session or a pre-session browser id."""

    ident: str
    is_session: bool


def session_binding(session_id: str) -> Binding:
    """Binding for an authenticated request."""
    return Binding(ident=session_id, is_session=True)


def browser_binding(browser_id: str) -> Binding:
    """Binding for an anonymous request carrying the per-browser id (T-Q312)."""
    return Binding(ident=browser_id, is_session=False)


def _mac_context(binding: Binding) -> bytes:
    return (_SESSION if binding.is_session else _PRE_SESSION) + binding.ident.encode()


def _token_mac(secret: str, binding: Binding, nonce: str, issued: str) -> str:
    message = _DOMAIN + _mac_context(binding) + b"|" + nonce.encode() + issued.encode()
    digest = hmac.new(secret.encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _seconds(instant: datetime) -> int:
    return int(instant.astimezone(UTC).timestamp())


def mint_token(secret: str, binding: Binding, tokens: TokenSource, now: datetime) -> str:
    """Return a fresh token bound to *binding*, issued at *now*."""
    nonce = tokens.new_token(_NONCE_BYTES)
    issued = f"{_seconds(now):0{_IAT_CHARS}x}"
    return nonce + issued + _token_mac(secret, binding, nonce, issued)


def check_token(secret: str, token: str | None, binding: Binding, now: datetime) -> TokenStatus:
    """Judge *token* for exactly *binding* at *now* (expiry applies to pre-session tokens)."""
    if not token or len(token) != _TOKEN_CHARS:
        return TokenStatus.INVALID
    nonce, issued, mac = (
        token[:_NONCE_CHARS],
        token[_NONCE_CHARS : _NONCE_CHARS + _IAT_CHARS],
        token[_NONCE_CHARS + _IAT_CHARS :],
    )
    expected = _token_mac(secret, binding, nonce, issued)
    if not hmac.compare_digest(mac.encode(), expected.encode()):
        return TokenStatus.INVALID
    age = now - datetime.fromtimestamp(int(issued, 16), UTC)
    if age < -_FUTURE_SKEW:
        return TokenStatus.INVALID
    if not binding.is_session and age > PRE_SESSION_TOKEN_MAX_AGE:
        return TokenStatus.EXPIRED
    return TokenStatus.VALID


def verify_token(secret: str, token: str | None, binding: Binding, now: datetime) -> bool:
    """True iff *token* is authentic, unexpired and bound to exactly *binding*."""
    return check_token(secret, token, binding, now) is TokenStatus.VALID
