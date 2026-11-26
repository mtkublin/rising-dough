"""Outermost security-headers middleware: baseline headers, app-owned CSP nonce.

T-D07 introduced the baseline headers; T-Q254 (ADR-0036 addendum 2026-11-21)
makes this the outermost layer and the owner of the CSP:

- Pure ASGI, wrapped around the *whole* Starlette stack (see ``create_app``),
  so the 500 page rendered by ``ServerErrorMiddleware`` carries the headers too.
- A fresh 24-byte URL-safe nonce is minted per request. Any client- or
  proxy-supplied ``X-CSP-Nonce`` is ignored. The nonce is exposed to templates
  as ``request.state.csp_nonce`` and put in the CSP of HTML responses.
- 5xx responses are forced ``Cache-Control: no-store``.
- Headers a downstream layer already set are never overwritten.
"""

from __future__ import annotations

import secrets

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from budget_planner.web.middleware.asgi import CACHE_CONTROL_HEADER, NO_STORE, RESPONSE_START

_NONCE_BYTES = 24
_SERVER_ERROR_FLOOR = 500

_DEFAULT_HEADERS: tuple[tuple[str, str], ...] = (
    (
        "Strict-Transport-Security",
        "max-age=31536000; includeSubDomains; preload",
    ),
    ("X-Frame-Options", "DENY"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    (
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), interest-cohort=()",
    ),
)

# ADR-0036 §1 as amended by ADR-0113 (2026-11-26): strict script-src and
# style-src, both 'self' plus the per-request nonce; the unsafe inline keyword is gone.
_CSP_TEMPLATE = (
    "default-src 'self'; script-src 'self' 'nonce-{nonce}'; "
    "style-src 'self' 'nonce-{nonce}'; img-src 'self' data:; font-src 'self'; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
    "object-src 'none'; form-action 'self'"
)


def generate_nonce() -> str:
    """Return a URL-safe base64 nonce (24 bytes of entropy, 32 chars)."""
    return secrets.token_urlsafe(_NONCE_BYTES)


def build_csp(nonce: str) -> str:
    """The application CSP for ``nonce``."""
    return _CSP_TEMPLATE.format(nonce=nonce)


def security_headers_middleware(app: ASGIApp) -> ASGIApp:
    """Wrap ``app`` with baseline headers, the nonce CSP and 5xx ``no-store``."""

    async def middleware(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        nonce = generate_nonce()
        # New scope (no mutation of the caller's): Starlette's ``request.state``
        # reads ``scope["state"]``.
        inner_scope = {**scope, "state": {**scope.get("state", {}), "csp_nonce": nonce}}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == RESPONSE_START:
                headers = MutableHeaders(scope=message)
                for name, value in _DEFAULT_HEADERS:
                    if name not in headers:
                        headers[name] = value
                if "text/html" in headers.get("content-type", "") and (
                    "content-security-policy" not in headers
                ):
                    headers["Content-Security-Policy"] = build_csp(nonce)
                if message["status"] >= _SERVER_ERROR_FLOOR:
                    headers[CACHE_CONTROL_HEADER] = NO_STORE
            await send(message)

        await app(inner_scope, receive, send_wrapper)

    return middleware
