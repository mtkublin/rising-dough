"""Dev-only `/dev/components` reference page (ADR-0053).

Gated behind ``settings.env != "production"`` so prod never ships it.
Populated in Phase 2 (T-R23); for Phase 1 we render an empty placeholder
list so the Playwright canary has a stable target.
"""

from __future__ import annotations

from http import HTTPStatus
from types import MappingProxyType
from typing import Final, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.errors import ConflictError
from budget_planner.web.deps import get_settings_dep
from budget_planner.web.dialogs import dialog_response, invalid_dialog_response, saved_response
from budget_planner.web.htmx import toast_payload, trigger
from budget_planner.web.rendering import render

router = APIRouter(tags=["dev"])

DialogVariant = Literal["standard", "confirm", "blocked", "sheet", "reconcile", "invalid"]
_VARIANTS_TEMPLATE: Final = "pages/dev/dialog_variants.html"
_DEV_FIELD_ERRORS: Final = MappingProxyType(
    {
        "amount": "Enter an amount above 0.00",
        "name": "Name is required",
    }
)


@router.get("/dev/components", response_class=HTMLResponse, include_in_schema=False)
def dev_components(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    if getattr(settings, "env", "dev") == "production":
        raise HTTPException(status_code=404)
    return render(request, "pages/dev/components.html")


@router.get("/dev/shell", response_class=HTMLResponse, include_in_schema=False)
def dev_shell(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    """Placeholder page on the new base layout (T-UR02); same gating as above."""
    if getattr(settings, "env", "dev") == "production":
        raise HTTPException(status_code=404)
    return render(request, "pages/dev/shell.html", nav_current="today")


@router.get("/dev/shell/dialog", response_class=HTMLResponse, include_in_schema=False)
def dev_shell_dialog(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    """Dev-only dialog that exercises the offline save-failure state (T-UR25)."""
    if getattr(settings, "env", "dev") == "production":
        raise HTTPException(status_code=404)
    return dialog_response(request, "pages/dev/dialog.html", {})


@router.post("/dev/shell/dialog", response_class=HTMLResponse, include_in_schema=False)
def dev_shell_dialog_save(
    request: Request,
    note: str = Form(...),
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    """Dev-only save: writes nothing, closes the dialog and flashes the note."""
    if getattr(settings, "env", "dev") == "production":
        raise HTTPException(status_code=404)
    return saved_response(request, None, {}, message=f"Saved note: {note}")


@router.get("/dev/shell/dialog/{variant}", response_class=HTMLResponse, include_in_schema=False)
def dev_shell_dialog_variant(
    request: Request,
    variant: DialogVariant,
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    """Dev-only: one variant of the shared dialog shell (T-UR04e); ``invalid`` answers 422."""
    if getattr(settings, "env", "dev") == "production":
        raise HTTPException(status_code=404)
    if variant == "invalid":
        return invalid_dialog_response(
            request, _VARIANTS_TEMPLATE, {"variant": variant}, _DEV_FIELD_ERRORS
        )
    return dialog_response(request, _VARIANTS_TEMPLATE, {"variant": variant})


@router.post("/dev/shell/dialog/{variant}", response_class=HTMLResponse, include_in_schema=False)
def dev_shell_dialog_variant_save(
    request: Request,
    variant: DialogVariant,
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    """Dev-only save: confirm succeeds, every form variant fails with two field errors."""
    if getattr(settings, "env", "dev") == "production":
        raise HTTPException(status_code=404)
    if variant == "confirm":
        return saved_response(request, None, {}, message="Dev account deleted")
    return invalid_dialog_response(
        request, _VARIANTS_TEMPLATE, {"variant": "invalid"}, _DEV_FIELD_ERRORS
    )


@router.post("/dev/shell/toast", include_in_schema=False)
def dev_shell_toast(
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    """Dev-only: answer with an HX-Trigger toast carrying an undo link (T-UR02, ADR-0143)."""
    if getattr(settings, "env", "dev") == "production":
        raise HTTPException(status_code=404)
    response = Response(status_code=204)
    trigger(
        response,
        toast=toast_payload("success", "Dev toast saved", undo_url="/dev/shell/toast/undo"),
    )
    return response


@router.post("/dev/shell/fail/{status}", include_in_schema=False)
def dev_shell_fail(
    status: int,
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    """Dev-only: fail through the real error handlers (409 conflict, 500 unhandled)."""
    if getattr(settings, "env", "dev") == "production":
        raise HTTPException(status_code=404)
    if status == HTTPStatus.CONFLICT:
        raise ConflictError(message="Dev conflict: that row is protected")
    if status == HTTPStatus.INTERNAL_SERVER_ERROR:
        raise RuntimeError("dev failure")
    if status == HTTPStatus.NOT_FOUND:
        return Response(status_code=HTTPStatus.NOT_FOUND, content="not found")
    raise HTTPException(status_code=404)
