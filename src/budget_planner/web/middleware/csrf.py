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
from dataclasses import dataclass
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from typing import Final

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from budget_planner.adapters.entropy import SecretsTokenSource
from budget_planner.config import Settings
from budget_planner.web.auth_cookies import session_cookie_name
from budget_planner.web.csrf_token import mint_token, verify_token
from budget_planner.web.middleware.asgi import (
    RESPONSE_START,
    SET_COOKIE,
    add_cookie,
    http_only,
    set_header,
    set_state,
)
from budget_planner.web.middleware.auth import STATIC_PREFIX

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

#: CSPRNG adapter for the nonce (stateless; ADR-0021 amendment).
_TOKENS: Final = SecretsTokenSource()

#: Template value on static paths (no token is minted there).
NO_TOKEN: Final = ""

#: HTTP methods that must carry a matching token.
_UNSAFE_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Paths exempt from token enforcement — liveness probes only. Extend by
#: adding more absolute paths; prefer per-route decorators for auth
#: endpoints once T-D02 lands.
_EXEMPT_PATHS: Final = frozenset({"/health", "/ready", "/healthz"})


def csrf_cookie_name(settings: Settings) -> str:
    """Return the CSRF cookie name for *settings* (ADR-0065)."""
    return CSRF_DEV_COOKIE_NAME if settings.env == "dev" else CSRF_COOKIE_NAME


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


class MalformedFormError(Exception):
    """The request body could not be parsed as the form its content type claims."""


def _is_form(request: Request) -> bool:
    content_type = request.headers.get("content-type", "").lower()
    return content_type.startswith(("application/x-www-form-urlencoded", "multipart/form-data"))


def _replaying(body: bytes, receive: Receive) -> Receive:
    """A ``receive`` that yields *body* once, then defers to the real channel.

    Deferring (instead of replaying forever) keeps ``http.disconnect`` visible to
    downstream streaming responses.
    """
    sent = False

    async def replay() -> Message:
        nonlocal sent
        if sent:
            return await receive()
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return replay


async def _form_token(scope: Scope, body: bytes, receive: Receive) -> str | None:
    """Return the ``_csrf_token`` form field parsed from the buffered *body*."""
    request = Request(scope, _replaying(body, receive))
    try:
        form = await request.form()
    except (HTTPException, MultiPartException):
        # Malformed multipart or too many fields: a client error, not a 500 (T-Q233).
        raise MalformedFormError from None
    try:
        value = form.get(CSRF_FORM_FIELD)
        return value if isinstance(value, str) else None
    finally:
        await form.close()


async def _check(
    scope: Scope, receive: Receive, existing: str | None, *, bound: bool
) -> tuple[JSONResponse | None, Receive]:
    """Enforce the double-submit token; return a rejection or the receive to pass on.

    *bound* says the cookie token verifies for the request's session context
    (T-Q289); a stale or foreign token is refused even when the header echoes it.
    """
    if not existing:
        return csrf_rejection("missing_cookie"), receive
    request = Request(scope, receive)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    form_token: str | None = None
    downstream = receive
    if _is_form(request):
        body = await request.body()
        downstream = _replaying(body, receive)
        try:
            form_token = await _form_token(scope, body, receive)
        except MalformedFormError:
            return csrf_rejection("malformed_form", status=HTTPStatus.BAD_REQUEST), downstream
    submitted = header_token or form_token
    matches = submitted is not None and secrets.compare_digest(
        submitted.encode(), existing.encode()
    )
    if not (bound and matches):
        return csrf_rejection("invalid_csrf"), downstream
    return None, downstream


def _rotated_session(
    message: Message, cookie_name: str, current: str | None
) -> tuple[bool, str | None]:
    """Return ``(rotated, new_session_id)`` from the session cookie the app set (login/logout)."""
    for raw in Headers(scope=message).getlist(SET_COOKIE):
        if not raw.startswith(f"{cookie_name}="):
            continue
        jar: SimpleCookie = SimpleCookie()
        try:
            jar.load(raw)
        except CookieError:
            return False, current
        value = jar[cookie_name].value or None
        return value != current, value
    return False, current


@dataclass(frozen=True, slots=True)
class _Context:
    """Per-request CSRF inputs derived from settings, session and cookie."""

    secret: str
    cookie_name: str
    session_name: str
    secure: bool
    session_id: str | None
    existing: str | None
    bound: bool


def _request_context(request: Request) -> _Context:
    settings: Settings = request.app.state.settings
    secret = settings.resolve().cookie_secret
    # ``session_id`` is set by the auth layer only for a live session (T-Q289).
    session_id: str | None = request.scope.get("state", {}).get("session_id")
    existing = request.cookies.get(csrf_cookie_name(settings))
    return _Context(
        secret=secret,
        cookie_name=csrf_cookie_name(settings),
        session_name=session_cookie_name(settings),
        # ``__Host-`` cookies require ``Secure``; dev (plain HTTP) drops both (ADR-0065).
        secure=settings.env != "dev",
        session_id=session_id,
        existing=existing,
        bound=verify_token(secret, existing, session_id),
    )


def _cookie_to_set(ctx: _Context, token: str, message: Message) -> str | None:
    """The CSRF cookie value this response must set, or ``None`` to leave it alone."""
    rotated, new_session = _rotated_session(message, ctx.session_name, ctx.session_id)
    if rotated:
        return mint_token(ctx.secret, new_session, _TOKENS)
    return None if ctx.bound else token


async def _protect_csrf(app: ASGIApp, scope: Scope, receive: Receive, send: Send) -> None:
    request = Request(scope, receive)
    if request.url.path.startswith(STATIC_PREFIX) and request.method not in _UNSAFE_METHODS:
        # The auth layer never hydrates the session for static assets, so the
        # session-bound token cannot be judged here; never mint or rotate on them.
        set_state(scope, csrf_token=NO_TOKEN)
        await app(scope, receive, send)
        return
    ctx = _request_context(request)
    token = (
        ctx.existing
        if ctx.bound and ctx.existing
        else mint_token(ctx.secret, ctx.session_id, _TOKENS)
    )
    set_state(scope, csrf_token=token)

    downstream = receive
    if request.method in _UNSAFE_METHODS and request.url.path not in _EXEMPT_PATHS:
        rejection, downstream = await _check(scope, receive, ctx.existing, bound=ctx.bound)
        if rejection is not None:
            await rejection(scope, receive, send)
            return

    async def send_wrapper(message: Message) -> None:
        if message["type"] == RESPONSE_START:
            fresh = _cookie_to_set(ctx, token, message)
            if fresh is not None:
                # HTMX re-reads this and refreshes the meta tag, so an open tab survives
                # a session rotation (password change) without a reload (T-Q289).
                set_header(message, CSRF_HEADER_NAME, fresh)
                add_cookie(
                    message,
                    lambda r: _attach_cookie(r, ctx.cookie_name, fresh, secure=ctx.secure),
                )
        await send(message)

    await app(scope, downstream, send_wrapper)


def csrf_middleware(app: ASGIApp) -> ASGIApp:
    """Mint, surface, and enforce the double-submit CSRF token."""
    return http_only(app, _protect_csrf)


def csrf_rejection(detail: str, *, status: HTTPStatus = HTTPStatus.FORBIDDEN) -> JSONResponse:
    """Canonical 403 (400 for a malformed body); ``detail`` is machine-readable."""
    return JSONResponse(
        status_code=status,
        content={"detail": detail},
    )
