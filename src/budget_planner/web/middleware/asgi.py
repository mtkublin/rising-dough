"""Shared ASGI protocol constants and the helpers the pure-ASGI middlewares share.

T-Q254 introduced the pattern (a function that takes the next app and returns an
ASGI app); T-Q274 (ADR-0144) converted the remaining ``BaseHTTPMiddleware``
subclasses to it. Everything that mutates the ASGI scope or a response-start
message is funnelled through the helpers here, so the framework-imposed
mutation lives in one reviewed place (``[[framework]]`` entry, ADR-0144).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: ``message["type"]`` of the ASGI event that carries status and headers.
RESPONSE_START = "http.response.start"
CACHE_CONTROL_HEADER = "Cache-Control"
NO_STORE = "no-store"
SET_COOKIE = "set-cookie"

#: ``handler(app, scope, receive, send)`` for one HTTP request.
HttpHandler = Callable[[ASGIApp, Scope, Receive, Send], Awaitable[None]]


def http_only(app: ASGIApp, handler: HttpHandler) -> ASGIApp:
    """Return an ASGI app that runs *handler* for HTTP and passes everything else through."""

    async def middleware(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        await handler(app, scope, receive, send)

    return middleware


def set_state(scope: Scope, **values: object) -> None:
    """Publish *values* on ``request.state`` (Starlette reads ``scope["state"]``)."""
    state = scope.setdefault("state", {})
    state.update(values)


def reroute(scope: Scope, *, method: str, path: str) -> Scope:
    """A copy of *scope* aimed at *method* *path* (the original scope is left untouched)."""
    return {
        **scope,
        "method": method,
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
    }


def set_header(message: Message, name: str, value: str) -> None:
    """Set (replace) header *name* on a ``http.response.start`` *message*."""
    headers = MutableHeaders(scope=message)
    headers[name] = value


def add_cookie(message: Message, apply: Callable[[Response], None]) -> None:
    """Append the ``Set-Cookie`` headers *apply* writes onto a throwaway response.

    Reuses the one cookie-attribute implementation (``auth_cookies``, CSRF) that
    works on a ``Response`` instead of re-serialising cookies by hand.
    """
    carrier = Response()
    apply(carrier)
    headers = MutableHeaders(scope=message)
    for key, value in carrier.raw_headers:
        if key == SET_COOKIE.encode("latin-1"):
            headers.append(SET_COOKIE, value.decode("latin-1"))


def sets_cookie(message: Message, name: str) -> bool:
    """True when the response-start *message* already carries ``Set-Cookie`` for *name*."""
    prefix = f"{name}="
    return any(value.startswith(prefix) for value in Headers(scope=message).getlist(SET_COOKIE))
