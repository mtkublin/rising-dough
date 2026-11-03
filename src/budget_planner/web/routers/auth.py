"""Auth routes: login (password + passkey), logout, passkey registration,
session / passkey management (T-D02b; ADR-0033, ADR-0061, ADR-0067, ADR-0070).

Thin layer over :mod:`budget_planner.services.auth`. Cookie plumbing lives in
:mod:`budget_planner.web.auth_cookies`. Login failures always yield the same
generic message / JSON body so responses never reveal whether an email is
registered.

Exempt from ``AuthRequiredMiddleware``: ``GET/POST /auth/login``,
``POST /auth/login/begin``, ``POST /auth/login/finish``. Every other route
here requires a session.
"""

from __future__ import annotations

import json
import re
import sqlite3
from http import HTTPStatus
from typing import Any, Final

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import (
    sessions as sessions_repo,
    webauthn as webauthn_repo,
)
from budget_planner.repositories.sessions import Session
from budget_planner.services import auth as auth_service
from budget_planner.web.auth_cookies import (
    LOGIN_PATH,
    Purpose,
    challenge_cookie_name,
    clear_challenge_cookie,
    clear_session_cookie,
    safe_next,
    set_challenge_cookie,
    set_session_cookie,
    sign_challenge,
    verify_challenge,
)
from budget_planner.web.deps import (
    current_user,
    get_db,
    get_request_ctx,
    get_settings_dep,
)
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.rendering import render

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_LOGIN_ERROR: Final = "That email and password combination didn't work."
PASSKEY_LOGIN_FAILED: Final = "login_failed"
SESSIONS_PATH: Final = "/auth/sessions"
LABEL_MAX_LENGTH: Final = 64
DEFAULT_PASSKEY_LABEL: Final = "Passkey"
_HANDLE_RE: Final = re.compile(r"^[0-9a-f]{16}$")
_SEE_OTHER: Final = HTTPStatus.SEE_OTHER


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=_SEE_OTHER)


def _rp(settings: Settings) -> auth_service.RelyingParty:
    return auth_service.relying_party_from_settings(settings)


def _start_session(
    request: Request,
    conn: sqlite3.Connection,
    settings: Settings,
    session: Session,
    response: Response,
) -> Response:
    """Revoke any session the browser already held, then set the new cookie."""
    previous = getattr(request.state, "session_id", None)
    if previous and previous != session.id:
        auth_service.logout(conn, previous)
    set_session_cookie(response, settings, session.id)
    return response


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(HTTPStatus.BAD_REQUEST, detail="invalid_json") from exc
    if not isinstance(body, dict):
        raise HTTPException(HTTPStatus.BAD_REQUEST, detail="invalid_json")
    return body


def _begin_response(
    settings: Settings,
    challenge: auth_service.PasskeyChallenge,
    purpose: Purpose,
    user_id: int | None,
) -> Response:
    response = Response(content=challenge.options_json, media_type="application/json")
    signed = sign_challenge(
        settings, purpose=purpose, user_id=user_id, challenge=challenge.challenge
    )
    set_challenge_cookie(response, settings, signed)
    return response


# ---------------------------------------------------------------------------
# Password login
# ---------------------------------------------------------------------------


def _login_page(
    request: Request, *, next_path: str, email: str = "", error: str | None = None
) -> HTMLResponse:
    return render(
        request,
        "auth/login.html",
        status_code=HTTPStatus.UNAUTHORIZED if error else HTTPStatus.OK,
        next_path=next_path,
        email=email,
        error=error,
    )


@router.get("/login", response_class=HTMLResponse, response_model=None)
def login_form(
    request: Request, next_path: str | None = Query(default=None, alias="next")
) -> HTMLResponse | RedirectResponse:
    """Render the login page; an already-signed-in user goes straight to ``next``."""
    target = safe_next(next_path)
    if getattr(request.state, "user", None) is not None:
        return _redirect(target)
    return _login_page(request, next_path=target)


@router.post("/login", response_model=None)
def login_password(  # noqa: PLR0917
    request: Request,
    email: str = Form(default=""),
    password: str = Form(default=""),
    next_path: str = Form(default="/", alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
) -> Response:
    """Password login. Any failure re-renders the form with a generic error."""
    target = safe_next(next_path)
    session = None
    if email.strip() and password:
        session = auth_service.authenticate_password(
            conn,
            email,
            password,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_ctx=ctx,
        )
    if session is None:
        return _login_page(
            request, next_path=target, email=email.strip(), error=GENERIC_LOGIN_ERROR
        )
    return _start_session(request, conn, settings, session, _redirect(target))


# ---------------------------------------------------------------------------
# Passkey login (usernameless)
# ---------------------------------------------------------------------------


@router.post("/login/begin")
def login_passkey_begin(settings: Settings = Depends(get_settings_dep)) -> Response:
    """Issue WebAuthn assertion options + the signed challenge cookie."""
    challenge = auth_service.authenticate_passkey_begin(_rp(settings))
    return _begin_response(settings, challenge, "login", None)


@router.post("/login/finish")
async def login_passkey_finish(
    request: Request,
    next_path: str | None = Query(default=None, alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
) -> Response:
    """Verify the assertion; on success set the session cookie and return ``redirect``."""
    body = await _json_body(request)
    envelope = verify_challenge(
        settings,
        request.cookies.get(challenge_cookie_name(settings)),
        purpose="login",
        user_id=None,
    )
    session = None
    if envelope is not None:
        session = auth_service.authenticate_passkey_finish(
            conn,
            body,
            challenge=envelope.challenge,
            rp=_rp(settings),
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_ctx=ctx,
        )
    if session is None:
        response: Response = JSONResponse(
            {"error": PASSKEY_LOGIN_FAILED}, status_code=HTTPStatus.UNAUTHORIZED
        )
    else:
        response = JSONResponse({"redirect": safe_next(next_path)})
        _start_session(request, conn, settings, session, response)
    clear_challenge_cookie(response, settings)
    return response


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.post("/logout")
def logout(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    _user: CurrentUser = Depends(current_user),
) -> Response:
    """Revoke the current session, clear the cookie, go to the login page."""
    session_id = getattr(request.state, "session_id", None)
    if session_id:
        auth_service.logout(conn, session_id, request_ctx=ctx)
    response = _redirect(LOGIN_PATH)
    clear_session_cookie(response, settings)
    return response


# ---------------------------------------------------------------------------
# Passkey registration (logged-in user)
# ---------------------------------------------------------------------------


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request, user: CurrentUser = Depends(current_user)) -> HTMLResponse:
    """Render the add-a-passkey page."""
    return render(
        request,
        "auth/register.html",
        current_user=user,
        label_max_length=LABEL_MAX_LENGTH,
    )


@router.post("/register/begin")
def register_passkey_begin(
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user: CurrentUser = Depends(current_user),
) -> Response:
    """Issue WebAuthn creation options for the signed-in user."""
    try:
        challenge = auth_service.register_passkey_begin(conn, user.id, _rp(settings))
    except auth_service.PasskeyRegistrationError as exc:  # pragma: no cover — user is live
        raise HTTPException(HTTPStatus.BAD_REQUEST, detail=exc.reason) from exc
    return _begin_response(settings, challenge, "register", user.id)


def _clean_label(raw: object) -> str:
    label = raw.strip() if isinstance(raw, str) else ""
    return (label or DEFAULT_PASSKEY_LABEL)[:LABEL_MAX_LENGTH]


@router.post("/register/finish")
async def register_passkey_finish(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
) -> Response:
    """Verify the attestation and store the passkey. Body: ``{label, credential}``."""
    body = await _json_body(request)
    envelope = verify_challenge(
        settings,
        request.cookies.get(challenge_cookie_name(settings)),
        purpose="register",
        user_id=user.id,
    )
    credential = body.get("credential")
    response: Response
    if envelope is None:
        response = JSONResponse({"error": "challenge_expired"}, status_code=HTTPStatus.BAD_REQUEST)
    elif not isinstance(credential, dict):
        response = JSONResponse({"error": "invalid_response"}, status_code=HTTPStatus.BAD_REQUEST)
    else:
        try:
            auth_service.register_passkey_finish(
                conn,
                user.id,
                credential,
                challenge=envelope.challenge,
                rp=_rp(settings),
                label=_clean_label(body.get("label")),
                request_ctx=ctx,
            )
        except auth_service.PasskeyRegistrationError as exc:
            response = JSONResponse({"error": exc.reason}, status_code=HTTPStatus.BAD_REQUEST)
        else:
            response = JSONResponse({"redirect": SESSIONS_PATH})
    clear_challenge_cookie(response, settings)
    return response


# ---------------------------------------------------------------------------
# Sessions + passkeys management
# ---------------------------------------------------------------------------


@router.get("/sessions", response_class=HTMLResponse)
def sessions_page(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user: CurrentUser = Depends(current_user),
) -> HTMLResponse:
    """List the user's own active sessions (by handle) and passkeys."""
    current_id = getattr(request.state, "session_id", None)
    sessions = sessions_repo.list_active_sessions(conn, user.id)
    rows = [{"session": s, "is_current": s.id == current_id} for s in sessions]
    return render(
        request,
        "auth/sessions.html",
        current_user=user,
        session_rows=rows,
        passkeys=webauthn_repo.list_credentials(conn, user.id),
    )


@router.post("/sessions/{handle}/revoke")
def revoke_session(  # noqa: PLR0917
    request: Request,
    handle: str,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
) -> Response:
    """Revoke one of the caller's own sessions, addressed by its handle."""
    if not _HANDLE_RE.match(handle):
        raise HTTPException(HTTPStatus.NOT_FOUND, detail="not_found")
    target = next(
        (s for s in sessions_repo.list_active_sessions(conn, user.id) if s.handle == handle),
        None,
    )
    if target is None or not auth_service.revoke_user_session(
        conn, user.id, target.id, request_ctx=ctx
    ):
        raise HTTPException(HTTPStatus.NOT_FOUND, detail="not_found")
    if target.id == getattr(request.state, "session_id", None):
        response = _redirect(LOGIN_PATH)
        clear_session_cookie(response, settings)
        return response
    return _redirect(SESSIONS_PATH)


@router.post("/passkeys/{credential_id}/revoke")
def revoke_passkey(
    credential_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
) -> Response:
    """Soft-delete one of the caller's own passkeys."""
    if not auth_service.revoke_passkey(conn, user.id, credential_id, request_ctx=ctx):
        raise HTTPException(HTTPStatus.NOT_FOUND, detail="not_found")
    return _redirect(SESSIONS_PATH)
