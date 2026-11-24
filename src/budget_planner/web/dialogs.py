"""HTMX response helpers for the redesign (T-UR04, ADR-0107 sections 3 to 5).

Four response shapes, one function each. Each sets the HX headers and renders
the fragments the shell already hosts (``#modal-root``, ``#flash-region``,
``#toast-root``); the dialog and row templates stay the caller's. Stale events
and toast payloads go through ``web.htmx.trigger`` (ADR-0143).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from fastapi import Request
from fastapi.responses import HTMLResponse

from budget_planner.web.field_labels import field_summary
from budget_planner.web.htmx import Event, trigger
from budget_planner.web.http_headers import HX_RESWAP, HX_RETARGET

MODAL_ROOT: Final = "#modal-root"
FLASH_SUCCESS: Final = "fragments/flash/success.html"
TOAST_UNDO: Final = "fragments/toast/undo.html"


def _html(request: Request, template: str, context: Mapping[str, object]) -> str:
    env = request.app.state.jinja_env
    ctx: dict[str, Any] = {
        "request": request,
        "settings": request.app.state.settings,
        "url_for": request.url_for,
        "csp_nonce": getattr(request.state, "csp_nonce", ""),
        "csrf_token": getattr(request.state, "csrf_token", ""),
    }
    ctx.update(context)
    rendered: str = env.get_template(template).render(**ctx)
    return rendered


def _oob(target_id: str, inner: str) -> str:
    """Out-of-band swap of ``inner`` into the element with ``target_id``."""
    return f'<div id="{target_id}" hx-swap-oob="innerHTML">{inner}</div>'


def dialog_response(
    request: Request,
    template: str,
    context: Mapping[str, object],
    *,
    status_code: int = 200,
) -> HTMLResponse:
    """Open a dialog: the template lands in ``#modal-root`` whatever the trigger targeted.

    The dialog is wrapped in one bare ``<div>``: the vendored ``dialog.js`` runs
    ``querySelectorAll`` on the swapped root, which never matches the root
    itself, so a root ``<dialog>`` would never open (ADR-0107 section 2: the
    handoff static stays byte-identical). A template that already wraps its
    dialog in a div just gets one harmless extra level.
    """
    body = f"<div>{_html(request, template, context)}</div>"
    response = HTMLResponse(body, status_code=status_code)
    response.headers[HX_RETARGET] = MODAL_ROOT
    response.headers[HX_RESWAP] = "innerHTML"
    return response


def saved_response(
    request: Request,
    row_template: str | None,
    context: Mapping[str, object],
    *,
    message: str,
    events: tuple[Event, ...] = (),
) -> HTMLResponse:
    """A successful POST: swap the row, close the dialog, flash the result out of band.

    The body is the row fragment (swapped into the caller's target), then the
    out-of-band emptying of ``#modal-root`` and the ``flash/success`` message.
    """
    row = _html(request, row_template, context) if row_template else ""
    flash = _html(request, FLASH_SUCCESS, {"message": message})
    body = row + _oob("modal-root", "") + _oob("flash-region", flash)
    response = HTMLResponse(body)
    trigger(response, *events)
    return response


def removed_response(
    request: Request,
    *,
    message: str,
    undo_url: str,
    events: tuple[Event, ...] = (),
) -> HTMLResponse:
    """A delete, skip or restore: remove the target row, offer undo in the toast root."""
    toast = _html(request, TOAST_UNDO, {"message": message, "undo_url": undo_url})
    response = HTMLResponse(_oob("toast-root", toast))
    response.headers[HX_RESWAP] = "delete"
    trigger(response, *events)
    return response


def invalid_dialog_response(
    request: Request,
    template: str,
    context: Mapping[str, object],
    fields: Mapping[str, str],
) -> HTMLResponse:
    """A failed save: 422 with the dialog re-rendered, the summary and per-field errors.

    The dialog template gets ``field_count`` and ``field_errors`` for
    ``forms/error-summary`` plus ``errors`` (name -> message), and sets
    ``aria-invalid="true"`` on every field named in ``errors``.
    """
    rows = field_summary(fields)
    merged: dict[str, object] = {
        **context,
        "errors": dict(fields),
        "field_count": len(rows),
        "field_errors": rows,
    }
    return dialog_response(request, template, merged, status_code=422)
