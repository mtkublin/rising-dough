"""Centralised exception → HTTP response mapping.

Routers raise `domain.errors.*` or let unhandled errors propagate; handlers
here map them to either a full-page template (browser nav) or a flash /
form-errors fragment (HTMX swap).

Pure functions — no business logic. Handlers inspect `HX-Request` to pick a
branch and reach for the Jinja env on `app.state`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.domain.errors import (
    ConflictError,
    InvariantError,
    NotFoundError,
    ServiceError,
    ValidationError,
)
from budget_planner.services.fx import FxUnavailableError
from budget_planner.web.deps import ReauthRequired
from budget_planner.web.field_labels import field_summary
from budget_planner.web.http_headers import HX_REQUEST
from budget_planner.web.params import ParamError

logger = logging.getLogger("budget_planner.web")


def _is_htmx(request: Request) -> bool:
    return request.headers.get(HX_REQUEST) == "true"


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _render(request: Request, template: str, status: int, **context: Any) -> HTMLResponse:
    env = request.app.state.jinja_env
    settings = request.app.state.settings
    rid = _request_id(request)
    ctx: dict[str, Any] = {
        "request": request,
        "settings": settings,
        "url_for": request.url_for,
        "request_id": rid,
        "csrf_token": getattr(request.state, "csrf_token", ""),
    }
    ctx.update(context)
    html: str = env.get_template(template).render(**ctx)
    headers = {"X-Request-Id": rid} if rid else None
    return HTMLResponse(html, status_code=status, headers=headers)


def _back_url(request: Request) -> str:
    """Where "back to the form" goes: the same-origin Referer path, else Today.

    A browser reads ``/\\evil`` as ``//evil``, so a backslash (raw or ``%5C``) in the
    path is refused as well as ``//``; a control character anywhere in the Referer is
    refused too (``isprintable`` is False for those).
    """
    raw = request.headers.get("referer", "")
    referer = urlsplit(raw)
    path = referer.path
    same_origin = referer.netloc == request.url.netloc
    safe_path = (
        path.startswith("/")
        and not path.startswith("//")
        and "\\" not in path
        and "%5c" not in path.lower()
    )
    if same_origin and safe_path and raw.isprintable():
        return f"{path}?{referer.query}" if referer.query else path
    return "/today"


def _flash_fragment(request: Request, kind: str, message: str, status: int) -> HTMLResponse:
    """Render the flash partial as an OOB swap, suitable for HTMX responses.

    The partial carries `hx-swap-oob="true"` + the live-region target, so the
    body is otherwise empty and HTMX will not clobber the originating target.
    """
    return _render(
        request,
        "partials/_flash.html",
        status,
        level=kind,
        message=message,
    )


async def handle_not_found(request: Request, exc: Exception) -> HTMLResponse:
    nf = exc if isinstance(exc, NotFoundError) else NotFoundError(entity="page", entity_id=0)
    if _is_htmx(request):
        return _flash_fragment(
            request,
            "error",
            f"{nf.entity.capitalize()} not found",
            status=404,
        )
    return _render(
        request,
        "pages/errors/404.html",
        status=404,
        entity=nf.entity,
        entity_id=nf.entity_id,
    )


async def handle_conflict(request: Request, exc: Exception) -> HTMLResponse:
    cf = exc if isinstance(exc, ConflictError) else ConflictError(message="conflict")
    if _is_htmx(request):
        return _flash_fragment(request, "warning", cf.message, status=409)
    return _render(
        request,
        "pages/errors/409.html",
        status=409,
        message=cf.message,
    )


def validation_summary(
    fields: Mapping[str, str],
) -> tuple[int, tuple[tuple[str, str, str], ...]]:
    """Pure 422 summary values: the field count and the (name, label, message) rows."""
    return len(fields), field_summary(fields)


async def handle_validation(request: Request, exc: Exception) -> HTMLResponse:
    v = exc if isinstance(exc, ValidationError) else ValidationError(fields={})
    # No form context here (handler cannot know which form was in flight); send
    # a flash plus a 422 so client code / tests can detect the shape, and let
    # routers short-circuit with a fully populated form partial before raising.
    message = next(iter(v.fields.values()), "validation failed")
    if _is_htmx(request):
        return _flash_fragment(request, "error", message, status=422)
    field_count, field_errors = validation_summary(v.fields)
    return _render(
        request,
        "pages/errors/422.html",
        status=422,
        fields=v.fields,
        field_count=field_count,
        field_errors=field_errors,
        back_url=_back_url(request),
    )


async def handle_param_error(request: Request, exc: Exception) -> HTMLResponse:
    fields = exc.fields if isinstance(exc, ParamError) else {}
    return await handle_validation(request, ValidationError(fields=fields))


async def handle_server_error(request: Request, exc: Exception) -> HTMLResponse:
    rid = _request_id(request)
    logger.error(
        "unhandled %s on %s %s",
        type(exc).__name__,
        request.method,
        request.url.path,
        extra={"request_id": rid},
        exc_info=exc,
    )
    message = exc.message if isinstance(exc, ServiceError) else "Something went wrong on our side."
    if _is_htmx(request):
        reference = f"{message} Reference: {rid}" if rid else message
        return _flash_fragment(request, "error", reference, status=500)
    return _render(
        request,
        "pages/errors/500.html",
        status=500,
        status_code=500,
        message=message,
    )


async def handle_missing_quote(request: Request, exc: Exception) -> HTMLResponse:
    """ADR-0139: a missing FX rate is a visible 503, never a substituted number."""
    logger.warning("fx rate unavailable on %s %s: %s", request.method, request.url.path, exc)
    message = f"Exchange rate unavailable: {exc}"
    if _is_htmx(request):
        return _flash_fragment(request, "error", message, status=503)
    return _render(request, "pages/errors/500.html", status=503, status_code=503, message=message)


def handle_reauth_required(_request: Request, exc: Exception) -> Response:
    """Return the stale-session response built by ``require_recent_auth``."""
    if not isinstance(exc, ReauthRequired):  # registered for ReauthRequired only
        raise InvariantError(f"unexpected exception type {type(exc).__name__}")
    return exc.response


def register_exception_handlers(app: FastAPI) -> None:
    """Bind handlers for the four domain errors + a catch-all Exception.

    Starlette's catch-all `Exception` handler also catches 500s generated by
    unhandled errors inside sync endpoints, so we don't need a try/except in
    every router.
    """
    app.add_exception_handler(ReauthRequired, handle_reauth_required)
    app.add_exception_handler(NotFoundError, handle_not_found)
    app.add_exception_handler(ConflictError, handle_conflict)
    app.add_exception_handler(ValidationError, handle_validation)
    app.add_exception_handler(ParamError, handle_param_error)
    app.add_exception_handler(FxUnavailableError, handle_missing_quote)
    app.add_exception_handler(ServiceError, handle_server_error)
    app.add_exception_handler(Exception, handle_server_error)
