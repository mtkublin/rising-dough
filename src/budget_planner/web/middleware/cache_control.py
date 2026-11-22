"""``Cache-Control: no-store`` on authenticated responses (T-D55, ADR-0078 §2).

Pure-ASGI middleware. When ``request.state.user`` is populated (by
:func:`~budget_planner.web.middleware.auth.auth_required_middleware`) and the
path is not under ``/static/``, the response gets ``Cache-Control: no-store``,
replacing any weaker value a route set. Anonymous responses (login page,
``/health``, ``/ready``) and static assets are left untouched.

Position: inside ``AuthRequired`` (so the user is hydrated) and outside
``MustChangePassword`` / ``AdminRequired`` / CSRF so their redirects and 404s
are covered too.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from budget_planner.web.middleware.asgi import (
    CACHE_CONTROL_HEADER,
    NO_STORE,
    RESPONSE_START,
    http_only,
    set_header,
)

_STATIC_PREFIX = "/static/"


def _is_authenticated(scope: Scope) -> bool:
    state = scope.get("state") or {}
    return state.get("user") is not None


async def _mark_no_store(app: ASGIApp, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["path"].startswith(_STATIC_PREFIX):
        await app(scope, receive, send)
        return

    async def send_wrapper(message: Message) -> None:
        if message["type"] == RESPONSE_START and _is_authenticated(scope):
            set_header(message, CACHE_CONTROL_HEADER, NO_STORE)
        await send(message)

    await app(scope, receive, send_wrapper)


def cache_control_middleware(app: ASGIApp) -> ASGIApp:
    """Mark every authenticated, non-static response ``no-store``."""
    return http_only(app, _mark_no_store)
