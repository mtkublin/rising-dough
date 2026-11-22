"""Per-request correlation id middleware (pure ASGI, T-Q274).

Attaches a short random id to ``request.state.request_id`` and echoes it
in the ``X-Request-Id`` response header. The id is grep-able in logs and
surfaced on the 500 error page so a user can report it.

T-D06: also binds the id to the structlog contextvar for the duration of
the request. Every log line emitted while the request is in flight
picks it up automatically; the ``finally`` guard clears the contextvar
so the next request does not inherit a stale id.
"""

from __future__ import annotations

from uuid import uuid4

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from budget_planner.logging import bind_request_id, clear_request_id
from budget_planner.web.middleware.asgi import RESPONSE_START, http_only, set_header, set_state

_HEADER = "X-Request-Id"


async def _correlate(app: ASGIApp, scope: Scope, receive: Receive, send: Send) -> None:
    rid = Headers(scope=scope).get(_HEADER) or uuid4().hex[:12]
    set_state(scope, request_id=rid)
    bind_request_id(rid)

    async def send_wrapper(message: Message) -> None:
        if message["type"] == RESPONSE_START:
            set_header(message, _HEADER, rid)
        await send(message)

    try:
        await app(scope, receive, send_wrapper)
    finally:
        clear_request_id()


def request_id_middleware(app: ASGIApp) -> ASGIApp:
    """Generate (or respect) a per-request id and echo it on every response."""
    return http_only(app, _correlate)
