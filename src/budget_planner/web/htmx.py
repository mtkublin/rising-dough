"""HTMX helpers: request detection + response trigger packing."""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from typing import Final, Literal
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import Response

from budget_planner.web.http_headers import (
    HTML_MEDIA_TYPE,
    HX_CURRENT_URL,
    HX_RESWAP,
    JSON_MEDIA_TYPE,
)

HX_TRIGGER: Final = "HX-Trigger"
"""Response: the events to fire. Request: the id of the element that fired the request."""


class Event(StrEnum):
    """Every server-emitted HX-Trigger event; the value is the wire name (ADR-0143)."""

    BALANCE_STALE = "balance-stale"
    BUDGET_STALE = "budget-stale"
    DIALOG_CLOSE = "dialog-close"
    FORECAST_STALE = "forecast-stale"
    LEDGER_STALE = "ledger-stale"
    TODAY_STALE = "today-stale"
    SETTINGS_CATEGORIES_STALE = "settings-categories-stale"
    TOAST = "toast"


ToastVariant = Literal["info", "success", "warning", "error"]


def toast_payload(
    variant: ToastVariant,
    message: str,
    *,
    undo_url: str | None = None,
    undo_payload: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the one toast payload shape the client (``app-init.js``) reads."""
    payload: dict[str, object] = {"variant": variant, "message": message}
    if undo_url is not None:
        payload["undo_url"] = undo_url
    if undo_payload is not None:
        payload["undo_payload"] = dict(undo_payload)
    return payload


def trigger(response: Response, *events: Event, toast: Mapping[str, object] | None = None) -> None:
    """Set the HX-Trigger header: stale events plus an optional toast.

    Always the JSON object form so stacked events survive the HTMX parser.
    """
    payload: dict[str, object] = dict.fromkeys((str(e) for e in events), True)
    if toast is not None:
        payload[str(Event.TOAST)] = dict(toast)
    if not payload:
        return
    response.headers[HX_TRIGGER] = json.dumps(payload)


def refresh_unless_on(request: Request, response: Response, path_prefix: str) -> None:
    """Skip the swap; off ``path_prefix`` also fire ``today-stale`` so the open page refetches.

    The page a form was submitted from is read from ``HX-Current-URL``. A full
    ``HX-Refresh`` reload would drop the out-of-band success flash, so no page
    reloads: the caller's events (and ``today-stale`` off the prefix, which the
    Today regions listen to) refresh the page's own regions (ADR-0143).
    """
    response.headers[HX_RESWAP] = "none"
    current = urlparse(request.headers.get(HX_CURRENT_URL, "")).path
    if current.startswith(path_prefix):
        return
    raw = response.headers.get(HX_TRIGGER)
    payload: dict[str, object] = json.loads(raw) if raw else {}
    payload[str(Event.TODAY_STALE)] = True
    response.headers[HX_TRIGGER] = json.dumps(payload)


def wants_json(request: Request) -> bool:
    """True when the client asked for JSON and not HTML (single owner, T-Q262)."""
    accept = request.headers.get("accept", "").lower()
    return JSON_MEDIA_TYPE in accept and HTML_MEDIA_TYPE not in accept
