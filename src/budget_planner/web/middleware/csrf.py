"""CSRF protection middleware.

T-D08 — Double-submit CSRF defence (ADR-0033 §4).

Flow:

1.  Every incoming request is inspected for the ``__Host-csrf`` cookie. If
    the cookie is missing a new URL-safe token is minted via
    :func:`secrets.token_urlsafe` and attached to the outgoing response.
    The cookie is scoped to ``Path=/`` with ``SameSite=Lax``. ``HttpOnly``
    is deliberately off so the HTMX extension can read the token from
    ``document.cookie``; the double-submit pattern makes JS readability
    safe. The ``__Host-`` prefix enforces ``Secure`` + host-only semantics
    by browser contract; ``Secure`` is suppressed only when
    ``settings.env == "dev"`` so raw-HTTP dev (non-localhost) still
    receives the cookie.
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


def _generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def _attach_cookie(response: Response, token: str, *, secure: bool) -> None:
    """Set the ``__Host-csrf`` cookie on *response*.

    The ``__Host-`` prefix mandates ``Secure`` + ``Path=/`` + no ``Domain``
    attribute. ``HttpOnly`` is deliberately **off**: the HTMX extension
    (``static/htmx-csrf.js``) reads this cookie from ``document.cookie`` to
    attach the ``X-CSRF-Token`` header on every HTMX request. The token is
    only a CSRF defence — it is a nonce, not a session credential, so the
    double-submit pattern is unaffected by JS readability. ``SameSite=Lax``
    plus the eventual signed ``__Host-session`` cookie carry the auth
    boundary (ADR-0033 §3).
    """
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
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
        # Chrome and Firefox treat ``http://localhost`` / ``http://127.0.0.1``
        # as a secure context, so the attribute is harmless on dev HTTP. The
        # dev / HTTP-over-non-localhost compromise is explicit:
        # ``settings.env == "dev"`` suppresses ``Secure`` for raw HTTP dev
        # that is not aliased to localhost. Tests pin ``env=test`` so they
        # get ``Secure=True`` and the TestClient fixture pins
        # ``base_url=https://`` to match.
        secure_cookie = settings.env != "dev"

        existing = request.cookies.get(CSRF_COOKIE_NAME)
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
            _attach_cookie(response, token, secure=secure_cookie)

        return response


def _reject(detail: str) -> JSONResponse:
    """Build the canonical 403 response. Detail string is machine-readable."""
    return JSONResponse(
        status_code=HTTPStatus.FORBIDDEN,
        content={"detail": detail},
    )
