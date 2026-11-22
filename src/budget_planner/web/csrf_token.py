"""Session-bound CSRF tokens (T-Q289, ADR-0065 amendment 2026-11-22).

A token is ``nonce || mac`` (both URL-safe base64, fixed widths). The MAC is an
HMAC-SHA256 keyed by the cookie secret over a context plus the nonce:

* authenticated request: the context is the session id, so a token minted for
  one session never verifies for another, and a new session (login) or a
  cleared one (logout) makes every earlier token stale (rotation by binding);
* anonymous request (login and passkey pages): the pre-session context, so a
  session-bound token is refused once the session is gone.

Verification is constant time (``hmac.compare_digest``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Final

from budget_planner.domain.ports import TokenSource

_DOMAIN: Final = b"csrf-v1|"
_NONCE_BYTES: Final = 16
_NONCE_CHARS: Final = 22  # urlsafe base64 of 16 bytes, unpadded
_MAC_CHARS: Final = 43  # urlsafe base64 of 32 bytes, unpadded
_PRE_SESSION: Final = b"pre|"
_SESSION: Final = b"session|"


def _mac_context(session_id: str | None) -> bytes:
    return _PRE_SESSION if session_id is None else _SESSION + session_id.encode()


def _token_mac(secret: str, session_id: str | None, nonce: str) -> str:
    digest = hmac.new(
        secret.encode(), _DOMAIN + _mac_context(session_id) + b"|" + nonce.encode(), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def mint_token(secret: str, session_id: str | None, tokens: TokenSource) -> str:
    """Return a fresh token bound to *session_id* (``None`` = pre-session)."""
    nonce = tokens.new_token(_NONCE_BYTES)
    return nonce + _token_mac(secret, session_id, nonce)


def verify_token(secret: str, token: str | None, session_id: str | None) -> bool:
    """True iff *token* is authentic and bound to exactly *session_id*."""
    if not token or len(token) != _NONCE_CHARS + _MAC_CHARS:
        return False
    nonce, mac = token[:_NONCE_CHARS], token[_NONCE_CHARS:]
    return hmac.compare_digest(mac.encode(), _token_mac(secret, session_id, nonce).encode())
