"""Auth cookie names, writers, and the signed passkey-challenge carrier.

ADR-0070 §1-§3. Single source of truth for:

* the session cookie name (``__Host-session`` / dev ``session``) and its
  attributes (``HttpOnly``, ``SameSite=Lax``, ``Max-Age`` from settings);
* the passkey challenge cookie (``__Host-passkey-challenge`` / dev
  ``passkey_challenge``) — an HMAC-SHA256-signed, 5-minute, single-purpose
  envelope around the raw WebAuthn challenge (ADR-0067 §1);
* the ``next`` redirect sanitiser shared by middleware and router.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal
from urllib.parse import urlsplit

from starlette.responses import Response

from budget_planner.config import Settings

SESSION_COOKIE_NAME: Final = "__Host-session"
SESSION_DEV_COOKIE_NAME: Final = "session"
CHALLENGE_COOKIE_NAME: Final = "__Host-passkey-challenge"
CHALLENGE_DEV_COOKIE_NAME: Final = "passkey_challenge"
CHALLENGE_TTL_SECONDS: Final = 300
LOGIN_PATH: Final = "/auth/login"
DEFAULT_LANDING: Final = "/today"  # ADR-0077

_FIRST_PRINTABLE: Final = 0x20
_DEL: Final = 0x7F
_CHALLENGE_DOMAIN: Final = b"passkey-challenge|"

Purpose = Literal["register", "login", "reauth"]


def _is_dev(settings: Settings) -> bool:
    return settings.env == "dev"


def session_cookie_name(settings: Settings) -> str:
    """Return the session cookie name for *settings* (ADR-0070 §1)."""
    return SESSION_DEV_COOKIE_NAME if _is_dev(settings) else SESSION_COOKIE_NAME


def challenge_cookie_name(settings: Settings) -> str:
    """Return the passkey challenge cookie name for *settings* (ADR-0070 §1)."""
    return CHALLENGE_DEV_COOKIE_NAME if _is_dev(settings) else CHALLENGE_COOKIE_NAME


def set_session_cookie(
    response: Response,
    settings: Settings,
    token: str,
    *,
    expires_at: datetime,
    now: datetime | None = None,
) -> None:
    """Attach the session cookie; ``Max-Age`` follows the clamped ``expires_at`` (ADR-0076 §1)."""
    remaining = expires_at - (datetime.now(UTC) if now is None else now)
    response.set_cookie(
        key=session_cookie_name(settings),
        value=token,
        max_age=max(0, int(remaining.total_seconds())),
        path="/",
        httponly=True,
        secure=not _is_dev(settings),
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    """Expire the session cookie on the client."""
    response.delete_cookie(
        key=session_cookie_name(settings),
        path="/",
        httponly=True,
        secure=not _is_dev(settings),
        samesite="lax",
    )


def response_sets_cookie(response: Response, name: str) -> bool:
    """True when *response* already carries a ``Set-Cookie`` for *name*."""
    prefix = f"{name}=".encode("latin-1")
    return any(
        key.lower() == b"set-cookie" and value.startswith(prefix)
        for key, value in response.raw_headers
    )


# ---------------------------------------------------------------------------
# Passkey challenge cookie
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ChallengeEnvelope:
    """Decoded, verified contents of the challenge cookie."""

    purpose: Purpose
    user_id: int | None
    challenge: bytes


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(secret: str, payload: bytes) -> bytes:
    return hmac.new(secret.encode("utf-8"), _CHALLENGE_DOMAIN + payload, hashlib.sha256).digest()


def sign_challenge(
    settings: Settings,
    *,
    purpose: Purpose,
    user_id: int | None,
    challenge: bytes,
    now: float | None = None,
) -> str:
    """Return the signed cookie value wrapping *challenge* for *purpose*."""
    payload = json.dumps(
        {
            "p": purpose,
            "u": user_id,
            "c": _b64e(challenge),
            "t": int(time.time() if now is None else now),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"{_b64e(payload)}.{_b64e(_mac(settings.cookie_secret, payload))}"


def _decode_envelope(secret: str, value: str | None) -> dict[str, object] | None:
    """Return the authentic JSON payload of *value*, or ``None``."""
    if not value or "." not in value:
        return None
    body, _, sig = value.partition(".")
    try:
        payload = _b64d(body)
        signature = _b64d(sig)
    except (binascii.Error, ValueError):
        return None
    if not hmac.compare_digest(signature, _mac(secret, payload)):
        return None
    try:
        data = json.loads(payload)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def verify_challenge(
    settings: Settings,
    value: str | None,
    *,
    purpose: Purpose,
    user_id: int | None,
    now: float | None = None,
) -> ChallengeEnvelope | None:
    """Return the envelope iff *value* is authentic, fresh, and matches purpose/user."""
    data = _decode_envelope(settings.cookie_secret, value)
    if data is None or data.get("p") != purpose or data.get("u") != user_id:
        return None
    try:
        challenge = _b64d(str(data["c"]))
        issued = int(str(data["t"]))
    except (KeyError, ValueError, binascii.Error):
        return None
    current = time.time() if now is None else now
    if not issued <= current < issued + CHALLENGE_TTL_SECONDS:
        return None
    return ChallengeEnvelope(purpose=purpose, user_id=user_id, challenge=challenge)


def set_challenge_cookie(response: Response, settings: Settings, value: str) -> None:
    """Attach the short-lived challenge cookie (``SameSite=Strict``)."""
    response.set_cookie(
        key=challenge_cookie_name(settings),
        value=value,
        max_age=CHALLENGE_TTL_SECONDS,
        path="/",
        httponly=True,
        secure=not _is_dev(settings),
        samesite="strict",
    )


def clear_challenge_cookie(response: Response, settings: Settings) -> None:
    """Expire the challenge cookie (always called after ``*_finish``)."""
    response.delete_cookie(
        key=challenge_cookie_name(settings),
        path="/",
        httponly=True,
        secure=not _is_dev(settings),
        samesite="strict",
    )


# ---------------------------------------------------------------------------
# ``next`` sanitiser
# ---------------------------------------------------------------------------


def safe_next(value: str | None) -> str:
    """Return *value* iff it is a same-site path, else ``DEFAULT_LANDING`` (``/`` too; ADR-0077)."""
    if not value or value == "/" or not value.startswith("/") or value.startswith(("//", "/\\")):
        return DEFAULT_LANDING
    if "\\" in value or any(ord(ch) < _FIRST_PRINTABLE or ord(ch) == _DEL for ch in value):
        return DEFAULT_LANDING
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return DEFAULT_LANDING
    if parts.path == LOGIN_PATH or parts.path.startswith(f"{LOGIN_PATH}/"):
        return DEFAULT_LANDING
    return value


__all__ = [
    "CHALLENGE_COOKIE_NAME",
    "CHALLENGE_DEV_COOKIE_NAME",
    "CHALLENGE_TTL_SECONDS",
    "DEFAULT_LANDING",
    "LOGIN_PATH",
    "SESSION_COOKIE_NAME",
    "SESSION_DEV_COOKIE_NAME",
    "ChallengeEnvelope",
    "challenge_cookie_name",
    "clear_challenge_cookie",
    "clear_session_cookie",
    "response_sets_cookie",
    "safe_next",
    "session_cookie_name",
    "set_challenge_cookie",
    "set_session_cookie",
    "sign_challenge",
    "verify_challenge",
]
