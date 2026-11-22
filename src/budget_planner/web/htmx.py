"""HTMX helpers: request detection + response trigger packing."""

from __future__ import annotations

import json
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import Response

_TRIGGER_HEADER = "HX-Trigger"
_BUDGET_STALE = "budget-stale"
_CATEGORIES_STALE = "settings-categories-stale"


def trigger(response: Response, *events: str) -> None:
    """Set an HX-Trigger header carrying one or more event names.

    HTMX accepts either a bare event name or a JSON object mapping event
    names to payloads. We always emit the JSON form so stacked events
    survive the HTMX parser.
    """
    if not events:
        return
    payload = dict.fromkeys(events, True)
    response.headers["HX-Trigger"] = json.dumps(payload)


def toast_headers(
    *,
    message: str,
    variant: str,
    undo_url: str | None = None,
    stale_event: str = _CATEGORIES_STALE,
) -> dict[str, str]:
    """Response headers: an HX-Trigger carrying a toast plus the stale events a mutation raises."""
    toast: dict[str, str] = {"variant": variant, "message": message}
    if undo_url is not None:
        toast["undo_url"] = undo_url
    payload = {"toast": toast, stale_event: True, _BUDGET_STALE: True}
    return {_TRIGGER_HEADER: json.dumps(payload)}


def refresh_unless_on(request: Request, response: Response, path_prefix: str) -> None:
    """Skip the swap and, off ``path_prefix``, reload the page after a successful post.

    The page a form was submitted from is read from ``HX-Current-URL``. On that
    prefix the caller's ``HX-Trigger`` events refresh the page's own regions; on
    any other page nothing is listening, so the whole page reloads.
    """
    response.headers["HX-Reswap"] = "none"
    current = urlparse(request.headers.get("HX-Current-URL", "")).path
    if not current.startswith(path_prefix):
        response.headers["HX-Refresh"] = "true"
