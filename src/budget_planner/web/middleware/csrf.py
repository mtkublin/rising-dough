"""CSRF protection middleware.

T-D08 — Double-submit CSRF defence (ADR-0033 §4); T-Q289 session binding and
T-Q312 login-CSRF hardening (ADR-0065 amendments 2026-11-22 and 2026-11-23).

Flow:

1.  Every incoming request is inspected for the CSRF cookie
    (``__Host-csrf``, or ``csrf`` under ``env=dev`` — ADR-0065). If it is
    missing, stale or expired a new token is minted and attached to the outgoing
    response (``SameSite=Lax``, ``Path=/``). The HTMX extension reads the token
    from ``<meta name="csrf-token">`` rendered by ``base.html`` (ADR-0065).
    The ``__Host-`` prefix enforces ``Secure`` + host-only semantics by
    browser contract; under ``settings.env == "dev"`` both the prefix
    and ``Secure`` are dropped so raw-HTTP dev still stores the cookie.
2.  Anonymous tokens are bound to a per-browser id cookie (``__Host-csrf-bid``,
    HttpOnly) and expire after two hours; session tokens are bound to the session.
3.  ``request.state.csrf_token`` is populated with whichever token wins so Jinja
    templates can embed it in forms and HTMX requests can echo it as the
    ``X-CSRF-Token`` header.
4.  For state-changing methods (``POST``/``PUT``/``PATCH``/``DELETE``) the
    middleware first requires a same-origin request (``Sec-Fetch-Site`` or
    ``Origin``, see :mod:`csrf_origin`; 403 ``cross_origin``), then that *either*
    the ``X-CSRF-Token`` header *or* the ``_csrf_token`` form field equals the
    cookie value and that value verifies for the request's binding (403
    ``invalid_csrf``). An expired token on the login form re-renders the login
    page instead (T-Q312).

Exempt paths — infrastructure liveness probes that cannot carry a cookie
on first request (``/health``, ``/ready``) and the FastAPI health shim
(``/healthz``). To extend the exemption list add entries to
:data:`_EXEMPT_PATHS`; keep the set small.

Ordering (ADR-0033 §5): the middleware sits after
``SecurityHeadersMiddleware`` and before the future auth / rate-limit
layers so that request-id and security headers run on every response
(including the 403 we emit here) and the token is minted *before* any auth
decision, so the login form it renders can embed a valid ``_csrf_token``.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from datetime import datetime
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from typing import Final

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from budget_planner import clock
from budget_planner.adapters.entropy import SecretsTokenSource
from budget_planner.config import Settings
from budget_planner.web.auth_cookies import LOGIN_PATH, session_cookie_name
from budget_planner.web.csrf_token import (
    Binding,
    TokenStatus,
    browser_binding,
    check_token,
    mint_token,
    session_binding,
)
from budget_planner.web.htmx import wants_json
from budget_planner.web.middleware.asgi import (
    RESPONSE_START,
    SET_COOKIE,
    add_cookie,
    http_only,
    reroute,
    set_header,
    set_state,
)
from budget_planner.web.middleware.auth import STATIC_PREFIX
from budget_planner.web.middleware.csrf_origin import is_same_origin
from budget_planner.web.rendering import is_hx_request

#: Cookie name — the ``__Host-`` prefix is a browser-enforced invariant
#: that pins the cookie to the exact origin and requires ``Secure`` +
#: ``Path=/``. See https://developer.mozilla.org/docs/Web/HTTP/Cookies.
CSRF_COOKIE_NAME: Final = "__Host-csrf"

#: Dev-only cookie name (ADR-0065). Browsers discard ``__Host-`` cookies
#: that lack ``Secure``, and plain-HTTP dev cannot set ``Secure`` reliably,
#: so dev drops the prefix instead of shipping a cookie that never sticks.
CSRF_DEV_COOKIE_NAME: Final = "csrf"

#: Per-browser id cookie binding pre-session tokens (T-Q312), same naming rule.
BROWSER_COOKIE_NAME: Final = "__Host-csrf-bid"
BROWSER_DEV_COOKIE_NAME: Final = "csrf-bid"

#: ``request.state`` flag: the anonymous login form POST carried an expired token (T-Q312).
EXPIRED_STATE_KEY: Final = "csrf_expired"

#: Bytes of entropy in a browser id.
_BROWSER_ID_BYTES: Final = 16

#: Header name HTMX / JS clients attach on state-changing requests.
CSRF_HEADER_NAME: Final = "X-CSRF-Token"

#: Form field name non-HTMX HTML forms use to submit the token.
CSRF_FORM_FIELD: Final = "_csrf_token"

#: CSPRNG adapter for the nonce and browser id (stateless; ADR-0021 amendment).
_TOKENS: Final = SecretsTokenSource()

#: Template value on static paths (no token is minted there).
NO_TOKEN: Final = ""

#: HTTP methods that must carry a matching token.
_UNSAFE_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Paths exempt from token enforcement — liveness probes only.
_EXEMPT_PATHS: Final = frozenset({"/health", "/ready", "/healthz"})


def csrf_cookie_name(settings: Settings) -> str:
    """Return the CSRF cookie name for *settings* (ADR-0065)."""
    return CSRF_DEV_COOKIE_NAME if settings.env == "dev" else CSRF_COOKIE_NAME


def csrf_browser_cookie_name(settings: Settings) -> str:
    """Return the per-browser id cookie name for *settings* (ADR-0065, T-Q312)."""
    return BROWSER_DEV_COOKIE_NAME if settings.env == "dev" else BROWSER_COOKIE_NAME


def _attach_browser_cookie(response: Response, name: str, value: str, *, secure: bool) -> None:
    """Set the HttpOnly per-browser id cookie (never read by JS)."""
    response.set_cookie(
        key=name, value=value, path="/", httponly=True, secure=secure, samesite="lax"
    )


def _clear_browser_cookie(response: Response, name: str, *, secure: bool) -> None:
    response.delete_cookie(key=name, path="/", httponly=True, secure=secure, samesite="lax")


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

    *bound* says the cookie token verifies for the request's binding (T-Q289, T-Q312);
    a stale, expired or foreign token is refused even when the header echoes it.
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
    """Per-request CSRF inputs derived from settings, session and cookies."""

    secret: str
    cookie_name: str
    browser_name: str
    session_name: str
    secure: bool
    session_id: str | None
    browser_id: str | None  # the id cookie an anonymous request carried
    minted_browser_id: str | None  # a new id this response must set (anonymous, none sent)
    sent_browser_cookie: bool  # the request carried an id cookie (cleared once a session exists)
    existing: str | None
    status: TokenStatus
    now: datetime

    @property
    def bound(self) -> bool:
        return self.status is TokenStatus.VALID

    @property
    def binding(self) -> Binding:
        """Binding new tokens get on this request."""
        if self.session_id is not None:
            return session_binding(self.session_id)
        return browser_binding(self.minted_browser_id or self.browser_id or "")


def _request_context(request: Request) -> _Context:
    settings: Settings = request.app.state.settings
    # ``session_id`` is set by the auth layer only for a live session (T-Q289).
    session_id: str | None = request.scope.get("state", {}).get("session_id")
    browser_name = csrf_browser_cookie_name(settings)
    sent = request.cookies.get(browser_name) or None
    browser_id = None if session_id is not None else sent
    anonymous_without_id = session_id is None and browser_id is None
    ctx = _Context(
        secret=settings.resolve().cookie_secret,
        cookie_name=csrf_cookie_name(settings),
        browser_name=browser_name,
        session_name=session_cookie_name(settings),
        # ``__Host-`` cookies require ``Secure``; dev (plain HTTP) drops both (ADR-0065).
        secure=settings.env != "dev",
        session_id=session_id,
        browser_id=browser_id,
        minted_browser_id=_TOKENS.new_token(_BROWSER_ID_BYTES) if anonymous_without_id else None,
        sent_browser_cookie=sent is not None,
        existing=request.cookies.get(csrf_cookie_name(settings)),
        status=TokenStatus.INVALID,
        now=clock.utc_now(),
    )
    if anonymous_without_id:
        return ctx  # a token cannot verify for a browser we have never seen
    return replace(ctx, status=check_token(ctx.secret, ctx.existing, ctx.binding, ctx.now))


@dataclass(frozen=True, slots=True)
class _Outcome:
    """Cookie changes one response must make (``None``/``False`` leave cookies alone)."""

    csrf: str | None = None
    browser_id: str | None = None
    clear_browser: bool = False


def _outcome(ctx: _Context, token: str, message: Message) -> _Outcome:
    rotated, new_session = _rotated_session(message, ctx.session_name, ctx.session_id)
    if rotated and new_session is not None:
        # Login or session change: session-bound token; the browser id is no longer needed.
        return _Outcome(
            csrf=mint_token(ctx.secret, session_binding(new_session), _TOKENS, ctx.now),
            clear_browser=ctx.sent_browser_cookie,
        )
    if rotated:
        # Logout: a brand new browser id and a token bound to it.
        fresh = _TOKENS.new_token(_BROWSER_ID_BYTES)
        return _Outcome(
            csrf=mint_token(ctx.secret, browser_binding(fresh), _TOKENS, ctx.now),
            browser_id=fresh,
        )
    return _Outcome(
        csrf=None if ctx.bound else token,
        browser_id=ctx.minted_browser_id,
        clear_browser=ctx.session_id is not None and ctx.sent_browser_cookie,
    )


def _apply_outcome(message: Message, ctx: _Context, outcome: _Outcome) -> None:
    if outcome.csrf is not None:
        fresh = outcome.csrf
        # HTMX re-reads this and refreshes the meta tag, so an open tab survives
        # a session rotation (password change) without a reload (T-Q289).
        set_header(message, CSRF_HEADER_NAME, fresh)
        add_cookie(message, lambda r: _attach_cookie(r, ctx.cookie_name, fresh, secure=ctx.secure))
    if outcome.browser_id is not None:
        bid = outcome.browser_id
        add_cookie(
            message,
            lambda r: _attach_browser_cookie(r, ctx.browser_name, bid, secure=ctx.secure),
        )
    elif outcome.clear_browser:
        add_cookie(message, lambda r: _clear_browser_cookie(r, ctx.browser_name, secure=ctx.secure))


def _expired_login_form(request: Request, ctx: _Context) -> bool:
    """An anonymous HTML login form POST whose token only expired (T-Q312)."""
    return (
        ctx.status is TokenStatus.EXPIRED
        and ctx.session_id is None
        and request.method == "POST"
        and request.url.path == LOGIN_PATH
        and _is_form(request)
        and not is_hx_request(request)
        and not wants_json(request)
    )


async def _enforce(
    request: Request, scope: Scope, receive: Receive, ctx: _Context
) -> tuple[JSONResponse | None, Scope, Receive]:
    """Origin, then token, checks for an unsafe request: ``(rejection, scope, receive)``."""
    settings: Settings = request.app.state.settings
    if not is_same_origin(request.headers, settings):
        return csrf_rejection("cross_origin"), scope, receive
    if _expired_login_form(request, ctx):
        # Not a raw 403: show the login page again with the fresh token (T-Q312).
        set_state(scope, **{EXPIRED_STATE_KEY: True})
        return None, reroute(scope, method="GET", path=LOGIN_PATH), receive
    if ctx.existing and ctx.session_id is None and ctx.browser_id is None:
        return csrf_rejection("missing_browser_id"), scope, receive
    rejection, downstream = await _check(scope, receive, ctx.existing, bound=ctx.bound)
    return rejection, scope, downstream


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
        else mint_token(ctx.secret, ctx.binding, _TOKENS, ctx.now)
    )
    set_state(scope, csrf_token=token)

    target, downstream = scope, receive
    if request.method in _UNSAFE_METHODS and request.url.path not in _EXEMPT_PATHS:
        rejection, target, downstream = await _enforce(request, scope, receive, ctx)
        if rejection is not None:
            await rejection(scope, receive, send)
            return

    async def send_wrapper(message: Message) -> None:
        if message["type"] == RESPONSE_START:
            _apply_outcome(message, ctx, _outcome(ctx, token, message))
        await send(message)

    await app(target, downstream, send_wrapper)


def csrf_middleware(app: ASGIApp) -> ASGIApp:
    """Mint, surface, and enforce the double-submit CSRF token."""
    return http_only(app, _protect_csrf)


def csrf_rejection(detail: str, *, status: HTTPStatus = HTTPStatus.FORBIDDEN) -> JSONResponse:
    """Canonical 403 (400 for a malformed body); ``detail`` is machine-readable."""
    return JSONResponse(
        status_code=status,
        content={"detail": detail},
    )
