"""Constants and pure helpers for bounded attacker text (T-Q203, ADR-0133).

IP-literal validation (``ipaddress`` raises) lives in ``web.deps.parse_client_ip``.

The client address comes from the proxy hop (ADR-0133 §1) but is still
request-derived text: only a valid IP literal may become a rate-limit key or
an audit/session column. Text the requester controls (email, user agent) is
truncated before it is persisted.
"""

from __future__ import annotations

from typing import Final

UNKNOWN_IP: Final = "unknown"
EMAIL_MAX_LENGTH: Final = 254
USER_AGENT_MAX_LENGTH: Final = 256


def bound_text(text: str | None, limit: int) -> str | None:
    """Truncate ``text`` to at most ``limit`` characters (``None`` stays ``None``)."""
    if text is None:
        return None
    return text[:limit]
