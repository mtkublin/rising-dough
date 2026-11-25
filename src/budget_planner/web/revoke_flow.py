"""Responses of the session and passkey revoke buttons on Settings -> Security (T-UR14, ADR-0152).

The buttons are ``hx-post`` forms: on success the row swaps out and the success flash shows; a stale
id answers 404 with the shell's error flash (HTML, not JSON). Without HTMX the plain POST keeps its
redirect / 404 behaviour unchanged.
"""

from __future__ import annotations

import sqlite3
from http import HTTPStatus
from typing import NoReturn

from fastapi import HTTPException, Request
from fastapi.responses import Response

from budget_planner.domain.user_agent import device_label
from budget_planner.services import auth as auth_service
from budget_planner.web.dialogs import saved_response
from budget_planner.web.http_headers import HX_REDIRECT
from budget_planner.web.rendering import is_hx_request


def session_device(conn: sqlite3.Connection, user_id: int, handle: str) -> str:
    """Device label of the caller's session ``handle`` (before it is revoked)."""
    return next(
        (
            device_label(s.user_agent)
            for s in auth_service.list_active_sessions(conn, user_id)
            if s.handle == handle
        ),
        "device",
    )


def stale(message: str) -> NoReturn:
    """404 JSON body for an unknown, foreign or already revoked id, whoever the caller is.

    The body is pinned (``tests/contract/test_errors.py``); under HTMX ``app-toast.js`` turns the
    flash-less 404 into the generic "not found" flash.
    """
    raise HTTPException(HTTPStatus.NOT_FOUND, detail=message)


def revoked(request: Request, message: str, fallback: Response) -> Response:
    """The row swaps out and the flash shows (HTMX); otherwise the existing ``fallback``."""
    if is_hx_request(request):
        return saved_response(request, None, {}, message=message)
    return fallback


def signed_out_here(request: Request, response: Response) -> Response:
    """HTMX: the logout redirect as ``HX-Redirect``; the cookie clearing stays on ``response``."""
    if not is_hx_request(request):
        return response
    hx = Response(status_code=HTTPStatus.NO_CONTENT)
    for key, value in response.headers.items():
        if key.lower() not in {"location", "content-length"}:
            hx.headers.append(key, value)
    hx.headers[HX_REDIRECT] = response.headers["location"]
    return hx
