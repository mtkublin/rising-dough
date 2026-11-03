"""Admin-only diagnostics (T-D43). ``GET /debug/audit-tail?n=20`` returns JSON.

Used by the post-deploy smoke journey to confirm audit rows are written.
Anonymous requests are redirected by ``AuthRequiredMiddleware``; non-admins
get 404 (never 403) via :func:`current_admin`. ``n`` is capped at 100.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from budget_planner.services import audit_tail as audit_tail_service
from budget_planner.web.deps import get_db
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.routers.settings_users import current_admin

router = APIRouter(prefix="/debug", tags=["debug"], include_in_schema=False)


@router.get("/audit-tail")
def audit_tail(
    n: int = Query(default=audit_tail_service.DEFAULT_TAIL),
    conn: sqlite3.Connection = Depends(get_db),
    _admin: CurrentUser = Depends(current_admin),
) -> JSONResponse:
    """Latest audit rows, newest first, secrets redacted."""
    rows = audit_tail_service.audit_tail(conn, n)
    return JSONResponse(
        {"count": len(rows), "entries": rows}, headers={"Cache-Control": "no-store"}
    )
