"""Reject oversized request bodies with 413 (T-Q235, Q-035).

Pure ASGI: checks ``Content-Length`` up front and counts streamed bytes for
chunked uploads, so nothing past ``MAX_BODY_BYTES`` reaches a handler.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

from budget_planner.domain.limits import MAX_BODY_BYTES

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _BodyTooLargeError(Exception):
    """Raised from the wrapped ``receive`` once the streamed body passes the limit."""


async def _send_too_large(scope: Scope, receive: Receive, send: Send) -> None:
    response = JSONResponse(
        status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        content={"detail": f"request body exceeds {MAX_BODY_BYTES} bytes"},
    )
    await response(scope, receive, send)


def body_limit_middleware(app: ASGIApp) -> ASGIApp:
    """Wrap ``app`` so oversized request bodies are answered with 413."""

    async def middleware(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            await _send_too_large(scope, receive, send)
            return

        seen = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > MAX_BODY_BYTES:
                    raise _BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await app(scope, counting_receive, tracking_send)
        except _BodyTooLargeError:
            if started:
                raise
            await _send_too_large(scope, receive, send)

    return middleware
