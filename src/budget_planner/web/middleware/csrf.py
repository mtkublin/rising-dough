"""CSRF protection middleware.

T-D08 — Double-submit CSRF defence (ADR-0033 §4).

Flow:

1.  Every incoming request is inspected for the CSRF cookie
    (``__Host-csrf``, or ``csrf`` under ``env=dev`` — ADR-0065). If
    the cookie is missing a new URL-safe token is minted via
    :func:`secrets.token_urlsafe` and attached to the outgoing response.
    The cookie is scoped to ``Path=/`` with ``SameSite=Lax``. The HTMX
    extension reads the token from ``<meta name="csrf-token">`` rendered
    by ``base.html`` (ADR-0065), so the JS never needs the cookie name.
    The ``__Host-`` prefix enforces ``Secure`` + host-only semantics by
    browser contract; under ``settings.env == "dev"`` both the prefix
    and ``Secure`` are dropped so raw-HTTP dev still stores the cookie.
2.  ``request.state.csrf_token`` is populated with whichever token wins
    (incoming cookie value or freshly minted) so Jinja templates can embed
    it in forms and HTMX requests can echo it as the ``X-CSRF-Token``
    header.
3.  For state-changing methods (``POST``/``PUT``/``PATCH``/``DELETE``) the
    middleware enforces that *either* the ``X-CSRF-Token`` header *or* the
    ``_csrf_token`` form field equals the cookie value. Missing or
    mismatched tokens are rejected with ``403 {"detail": "invalid_csrf"}``
    before the request reaches the router.

Exempt paths — infrastructure liveness probes that cannot carry a cookie
on first request (``/health``, ``/ready``) and the FastAPI health shim
(``/healthz``). To extend the exemption list add entries to
:data:`_EXEMPT_PATHS`; keep the set small and prefer per-route decorators
once auth lands.

Ordering (ADR-0033 §5): the middleware sits after
``SecurityHeadersMiddleware`` and before the future auth / rate-limit
layers so that:

* request-id and security headers run on every response (including the
  403 we emit here);
* the token is minted *before* any auth decision, so the login form it
  renders can embed a valid ``_csrf_token``.
"""

from __future__ import annotations

import secrets
from http import HTTPStatus
from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from budget_planner.config import Settings

#: Cookie name — the ``__Host-`` prefix is a browser-enforced invariant
#: that pins the cookie to the exact origin and requires ``Secure`` +
#: ``Path=/``. See https://developer.mozilla.org/docs/Web/HTTP/Cookies.
CSRF_COOKIE_NAME: Final = "__Host-csrf"

#: Dev-only cookie name (ADR-0065). Browsers discard ``__Host-`` cookies
#: that lack ``Secure``, and plain-HTTP dev cannot set ``Secure`` reliably,
#: so dev drops the prefix instead of shipping a cookie that never sticks.
CSRF_DEV_COOKIE_NAME: Final = "csrf"

#: Header name HTMX / JS clients attach on state-changing requests.
CSRF_HEADER_NAME: Final = "X-CSRF-Token"

#: Form field name non-HTMX HTML forms use to submit the token.
CSRF_FORM_FIELD: Final = "_csrf_token"

#: HTTP methods that must carry a matching token.
_UNSAFE_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Paths exempt from token enforcement — liveness probes only. Extend by
#: adding more absolute paths; prefer per-route decorators for auth
#: endpoints once T-D02 lands.
_EXEMPT_PATHS: Final = frozenset({"/health", "/ready", "/healthz"})

#: 32 bytes of entropy — ``token_urlsafe(32)`` yields a 43-char string.
_TOKEN_BYTES: Final = 32


def csrf_cookie_name(settings: Settings) -> str:
    """Return the CSRF cookie name for *settings* (ADR-0065)."""
    return CSRF_DEV_COOKIE_NAME if settings.env == "dev" else CSRF_COOKIE_NAME


def _generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def _attach_cookie(response: Response, name: str, token: str, *, secure: bool) -> None:
    """Set the CSRF cookie *name* on *response*.

    The ``__Host-`` prefix mandates ``Secure`` + ``Path=/`` + no ``Domain``
    attribute. ``HttpOnly`` is **off**; the token is only a CSRF defence —
    a nonce, not a session credential — so the double-submit pattern is
    unaffected by JS readability. The HTMX extension takes the token from
    the ``<meta name="csrf-token">`` tag rather than the cookie (ADR-0065). ``SameSite=Lax``
    plus the eventual signed ``__Host-session`` cookie carry the auth
    boundary (ADR-0033 §3).
    """
    response.set_cookie(
        key=name,
        value=token,
        path="/",
        httponly=False,
        secure=secure,
        samesite="lax",
    )


async def _read_form_token(request: Request) -> str | None:
    """Return the ``_csrf_token`` form field if the body is a form payload.

    Starlette's :meth:`Request.form` consumes the underlying receive stream,
    which breaks downstream FastAPI handlers that re-parse the form. To
    stay compatible we buffer the body first, cache it on
    ``request._body``, and replace ``request._receive`` with an async
    generator that re-plays the buffered body. Starlette itself uses the
    same pattern — see ``starlette.requests.Request._receive``.
    """
    content_type = request.headers.get("content-type", "").lower()
    if not (
        content_type.startswith("application/x-www-form-urlencoded")
        or content_type.startswith("multipart/form-data")
    ):
        return None

    body = await request.body()

    async def _replay() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    # ``_receive`` is private but is the canonical ASGI replay hook used by
    # Starlette's own form parsing; this mirrors the recipe from
    # https://github.com/encode/starlette/discussions/1933.
    request._receive = _replay

    form = await request.form()
    try:
        value = form.get(CSRF_FORM_FIELD)
        if isinstance(value, str):
            return value
        return None
    finally:
        await form.close()
        # Reset again so FastAPI's own form parsing sees the full body.
        request._receive = _replay


class CSRFMiddleware(BaseHTTPMiddleware):
    """Mint, surface, and enforce the double-submit CSRF token."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings: Settings = request.app.state.settings
        # ``__Host-`` cookies require ``Secure`` to be honoured by browsers.
        # Dev runs over plain HTTP, so it uses the un-prefixed
        # ``CSRF_DEV_COOKIE_NAME`` without ``Secure`` (ADR-0065). Tests pin
        # ``env=test`` so they get ``__Host-csrf`` + ``Secure=True`` and the
        # TestClient fixture pins ``base_url=https://`` to match.
        secure_cookie = settings.env != "dev"
        cookie_name = csrf_cookie_name(settings)

        existing = request.cookies.get(cookie_name)
        token = existing if existing else _generate_token()
        request.state.csrf_token = token

        if request.method in _UNSAFE_METHODS and request.url.path not in _EXEMPT_PATHS:
            if existing is None:
                return _reject("missing_cookie")
            header_token = request.headers.get(CSRF_HEADER_NAME)
            form_token = await _read_form_token(request)
            submitted = header_token or form_token
            if submitted is None or not secrets.compare_digest(submitted, existing):
                return _reject("invalid_csrf")

        response = await call_next(request)

        if existing is None:
            _attach_cookie(response, cookie_name, token, secure=secure_cookie)

        return response


def _reject(detail: str) -> JSONResponse:
    """Build the canonical 403 response. Detail string is machine-readable."""
    return JSONResponse(
        status_code=HTTPStatus.FORBIDDEN,
        content={"detail": detail},
    )
