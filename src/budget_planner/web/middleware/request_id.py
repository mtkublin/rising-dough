"""Per-request correlation id middleware.

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

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from budget_planner.logging import bind_request_id, clear_request_id

_HEADER = "X-Request-Id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Generate (or respect) a per-request id. Idempotent — never mutates
    request state once set."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        existing = request.headers.get(_HEADER)
        rid = existing if existing else uuid4().hex[:12]
        request.state.request_id = rid
        bind_request_id(rid)
        try:
            response = await call_next(request)
        finally:
            clear_request_id()
        response.headers[_HEADER] = rid
        return response
