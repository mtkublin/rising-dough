"""Security-headers middleware + CSP nonce propagation.

T-D07 — Adds the five baseline response headers (HSTS, X-Frame-Options,
X-Content-Type-Options, Referrer-Policy, Permissions-Policy) when they are not
already present on the outgoing response. Caddy (ADR-0036 §1) sets most of
these at the edge in production; the middleware is the single source of truth
for local development, prod-sim stacks, and any direct-to-app request path.

CSP nonce flow (ADR-0036 §3):

- In production, Caddy generates a per-request UUID nonce and forwards it to
  the app as the ``X-CSP-Nonce`` request header. The CSP header itself is
  terminated at Caddy — this middleware only propagates the nonce into
  ``request.state.csp_nonce`` so Jinja templates can embed it on inline
  ``<script>`` / ``<style>`` tags.
- In development (and tests) no proxy is in front of the app. The middleware
  mints a fresh 24-byte base64 nonce per request so templates always see a
  non-empty, URL-safe nonce value. This keeps the Jinja contract identical in
  every environment.

Order per ADR-0033 §5: this middleware sits immediately after
``RequestIdMiddleware`` and before the (future) auth / CSRF / rate-limit
layers. Register with ``app.add_middleware(SecurityHeadersMiddleware)`` *after*
the request-id middleware has been added so the Starlette outer-first stack
runs request-id first, then security headers.
"""

from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_NONCE_HEADER = "X-CSP-Nonce"
_NONCE_BYTES = 24

# Baseline response headers. Caddy may already set some in production; the
# middleware only fills gaps (``setdefault`` semantics via a presence check).
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


def _generate_nonce() -> str:
    """Return a URL-safe base64 nonce (24 bytes of entropy → 32 chars)."""
    return secrets.token_urlsafe(_NONCE_BYTES)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach baseline security headers and propagate the CSP nonce.

    Idempotent: never overwrites a header a downstream layer (Caddy, a route
    handler) has already set. Reads the ``X-CSP-Nonce`` request header set by
    Caddy; falls back to a locally-generated nonce in dev / test.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_nonce = request.headers.get(_NONCE_HEADER)
        nonce = incoming_nonce if incoming_nonce else _generate_nonce()
        request.state.csp_nonce = nonce

        response = await call_next(request)

        for name, value in _DEFAULT_HEADERS:
            if name not in response.headers:
                response.headers[name] = value
        return response
