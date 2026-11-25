"""Forecast router: the old ``/forecast`` pages are retired (T-UR15a, ADR-0107).

The forecast lives on the Plan hub (``/plan?tab=forecast``, T-UR12). The old URLs stay as
redirects so bookmarks and the palette keep working; ``horizon_months`` becomes ``horizon``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from budget_planner.web import plan_redirects

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.get("")
def index(request: Request) -> RedirectResponse:
    return plan_redirects.to_plan(request, "forecast", {"horizon_months": "horizon"})


@router.get("/view")
def view_fragment(request: Request) -> RedirectResponse:
    return plan_redirects.to_plan(request, "forecast", {"horizon_months": "horizon"})
