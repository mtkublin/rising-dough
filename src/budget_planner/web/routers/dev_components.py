"""Dev-only `/dev/components` reference page (ADR-0053).

Gated behind ``settings.env != "production"`` so prod never ships it.
Populated in Phase 2 (T-R23); for Phase 1 we render an empty placeholder
list so the Playwright canary has a stable target.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from budget_planner.config import Settings
from budget_planner.web.deps import get_settings_dep
from budget_planner.web.rendering import render

router = APIRouter(tags=["dev"])


@router.get("/dev/components", response_class=HTMLResponse, include_in_schema=False)
def dev_components(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    if getattr(settings, "env", "dev") == "production":
        raise HTTPException(status_code=404)
    return render(request, "dev/components.html")


@router.get("/dev/shell", response_class=HTMLResponse, include_in_schema=False)
def dev_shell(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    """Placeholder page on the new base layout (T-UR02); same gating as above."""
    if getattr(settings, "env", "dev") == "production":
        raise HTTPException(status_code=404)
    return render(request, "pages/dev/shell.html", nav_current="today")
