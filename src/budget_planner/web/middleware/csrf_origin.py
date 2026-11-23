"""Origin check for state-changing requests (T-Q312, ADR-0065 amendment 2026-11-23).

Defence in depth against login CSRF: a cross-site request is refused before any
token is looked at. The public origin comes from configuration
(``Settings.webauthn_origin``, pinned to ``https://<hostname>`` in production),
never from the ``Host`` header, because production runs behind a reverse proxy.
"""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import Final
from urllib.parse import SplitResult, urlsplit

from starlette.datastructures import Headers

from budget_planner.config import Settings

_LOG = logging.getLogger(__name__)

SEC_FETCH_SITE: Final = "sec-fetch-site"
ORIGIN: Final = "origin"
SAME_ORIGIN: Final = "same-origin"
_LOOPBACK_HOSTS: Final = frozenset({"localhost", "127.0.0.1", "::1"})
_DEFAULT_PORT_SUFFIX: Final = MappingProxyType({"http": ":80", "https": ":443"})


def _normalise(origin: str) -> tuple[str, str, str] | None:
    """``(scheme, host, authority)`` of a bare origin, or ``None`` when it is not one.

    The authority has a default port stripped, so ``https://x:443`` equals ``https://x``.
    """
    try:
        parts = urlsplit(origin.strip().lower())
    except ValueError:
        _LOG.info("csrf_origin_unparseable")  # attacker-controlled header: refuse, never 500
        return None
    if not _is_bare_origin(parts) or not parts.hostname:
        return None
    return parts.scheme, parts.hostname, _strip_default_port(parts.scheme, parts.netloc)


def _is_bare_origin(parts: SplitResult) -> bool:
    """http(s) with no userinfo, path, query or fragment."""
    return (
        parts.scheme in _DEFAULT_PORT_SUFFIX
        and parts.path in {"", "/"}
        and not (parts.query or parts.fragment or "@" in parts.netloc)
    )


def _strip_default_port(scheme: str, authority: str) -> str:
    return authority.removesuffix(_DEFAULT_PORT_SUFFIX[scheme])


def origin_matches(origin: str, settings: Settings) -> bool:
    """True when *origin* is the app's public origin (any loopback host under ``env=dev``)."""
    candidate = _normalise(origin)
    public = _normalise(settings.webauthn_origin)
    if candidate is None or public is None:
        return False
    if candidate == public:
        return True
    # Dev binds 127.0.0.1 while the default origin names localhost: same scheme, loopback host.
    return (
        settings.env == "dev"
        and candidate[0] == public[0]
        and candidate[1] in _LOOPBACK_HOSTS
        and public[1] in _LOOPBACK_HOSTS
    )


def is_same_origin(headers: Headers, settings: Settings) -> bool:
    """Judge an unsafe request: ``Sec-Fetch-Site`` first, then ``Origin``; neither means no."""
    site = headers.get(SEC_FETCH_SITE)
    if site is not None:
        return site.strip().lower() == SAME_ORIGIN
    origin = headers.get(ORIGIN)
    return origin is not None and origin_matches(origin, settings)
