"""Health & readiness endpoints (T-D01).

- ``GET /health`` → 200 iff the process is up. No DB, no auth.
- ``GET /ready``  → 200 iff ``PRAGMA integrity_check`` on the configured
  SQLite file returns ``ok``; 503 otherwise.

Both routes stay outside any auth middleware (ADR-0033 §5) so Caddy, the
deploy pipeline, and the external uptime monitor can poll them without
credentials.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from budget_planner.config import Settings

router = APIRouter(tags=["health"])

_logger = logging.getLogger(__name__)


@router.get("/health", include_in_schema=False)
def health(request: Request) -> dict[str, str]:
    """Process liveness. Deliberately cheap — no DB, no logging."""
    return {"status": "ok", "version": request.app.version}


@router.get("/ready", include_in_schema=False)
def ready(request: Request) -> JSONResponse:
    """Readiness probe. 200 iff the DB passes ``PRAGMA integrity_check``.

    Opens a short-lived connection via the project factory so Litestream
    PRAGMAs are honoured. Any sqlite / IO error maps to 503 with the
    failure reason in the body — Caddy, the deploy pipeline, and the
    uptime monitor rely on the shape.
    """
    cfg: Settings = request.app.state.settings
    # Local import — the router is imported during app construction and we
    # want to keep the import graph flat (no circular pull from
    # ``web.app`` through ``db.connection``).
    from budget_planner.db.connection import get_connection  # noqa: PLC0415

    try:
        conn = get_connection(cfg)
    except Exception as exc:  # pragma: no cover — surface via the 503 shape
        _logger.warning("ready_probe_connection_failed", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "detail": f"connect failed: {exc}"},
        )
    try:
        row = conn.execute("PRAGMA integrity_check;").fetchone()
    except Exception as exc:
        _logger.warning("ready_probe_integrity_check_failed", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "detail": f"integrity_check failed: {exc}"},
        )
    finally:
        conn.close()
    first = row[0] if row is not None else None
    if first != "ok":
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "detail": f"integrity_check: {first!r}"},
        )
    return JSONResponse(status_code=200, content={"status": "ready", "db": "ok"})
