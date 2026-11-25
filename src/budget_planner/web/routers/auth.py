"""Auth routes: login (password + passkey), logout, passkey registration,
session / passkey management (T-D02b; ADR-0033, ADR-0061, ADR-0067, ADR-0070).

Thin layer over :mod:`budget_planner.services.auth`. Cookie plumbing lives in
:mod:`budget_planner.web.auth_cookies`; request/response helpers in
:mod:`budget_planner.web.auth_flow` and rate-limit dependencies in
:mod:`budget_planner.web.auth_deps` (T-Q267). Login failures always yield the same
generic message / JSON body so responses never reveal whether an email is
registered.

Exempt from ``AuthRequiredMiddleware``: ``GET/POST /auth/login``,
``POST /auth/login/begin``, ``POST /auth/login/finish``. Every other route
here requires a session.

T-D09 / ADR-0072: ``POST /auth/login``, ``/auth/login/finish`` and
``/auth/register/finish`` each declare a rate-limit dependency returning a
:class:`~budget_planner.services.rate_limit.RateDecision`; throttled calls
get ``429`` + ``Retry-After`` before any credential is checked. Tests inject
a clock via ``app.state.rate_limit_clock``.
"""

from __future__ import annotations

import logging
import sqlite3
from http import HTTPStatus
from typing import Final

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.ports import PasswordHasher
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.services import auth as auth_service, reauth as reauth_service
from budget_planner.services.rate_limit import RateDecision
from budget_planner.web import revoke_flow
from budget_planner.web.auth_cookies import (
    DEFAULT_LANDING,
    LOGIN_PATH,
    clear_challenge_cookie,
    clear_session_cookie,
    safe_next,
)
from budget_planner.web.auth_deps import (
    login_rate_limit,
    passkey_login_rate_limit,
    reauth_rate_limit,
    register_rate_limit,
    throttled_json,
)
from budget_planner.web.auth_flow import (
    begin_response,
    challenge_for,
    dev_host_is_ip,
    json_body,
    login_page,
    passkey_host_error,
    reauth_attempts_left,
    reauth_page,
    reauth_success,
    reauth_target,
    redirect,
    relying_party,
    start_session,
    throttled_login,
)
from budget_planner.web.deps import (
    client_ip,
    current_user,
    get_db,
    get_password_hasher,
    get_request_ctx,
    get_settings_dep,
    is_recently_authenticated,
    reauth_required_response,
    request_user_agent,
    require_recent_auth,
)
from budget_planner.web.htmx import wants_json
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.middleware.csrf import EXPIRED_STATE_KEY
from budget_planner.web.rendering import is_hx_request

_LOG = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

PAGE_EXPIRED_NOTICE: Final = "This page expired, please try again."
GENERIC_LOGIN_ERROR: Final = "That email and password combination didn't work."
PASSKEY_LOGIN_FAILED: Final = "login_failed"
SECURITY_SESSIONS_URL: Final = "/settings/security#sessions"
SECURITY_PASSKEYS_URL: Final = "/settings/security#passkeys"
#: ADR-0078 §2: wipe cache + storage on sign-out. "cookies" is omitted on
#: purpose (the session cookie is already expired; the CSRF cookie must survive).
_CLEAR_SITE_DATA: Final = '"cache", "storage"'
REAUTH_FAILED: Final = "reauth_failed"
GENERIC_REAUTH_ERROR: Final = "That password didn't work."
RATE_LIMITED_REAUTH_ERROR: Final = "Too many attempts. Please wait a few minutes and try again."


# ---------------------------------------------------------------------------
# Password login
# ---------------------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse, response_model=None)
def login_form(
    request: Request, next_path: str | None = Query(default=None, alias="next")
) -> HTMLResponse | RedirectResponse:
    """Render the login page; an already-signed-in user goes straight to ``next``."""
    target = safe_next(next_path)
    if getattr(request.state, "user", None) is not None:
        return redirect(target)
    if getattr(request.state, EXPIRED_STATE_KEY, False):
        # T-Q312: the CSRF middleware rerouted an expired login POST here with a fresh token.
        return login_page(
            request, next_path=target, error=PAGE_EXPIRED_NOTICE, status_code=HTTPStatus.FORBIDDEN
        )
    return login_page(request, next_path=target)


@router.post("/login", response_model=None)
def login_password(
    request: Request,
    *,
    email: str = Form(default=""),
    password: str = Form(default=""),
    next_path: str = Form(default=DEFAULT_LANDING, alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    hasher: PasswordHasher = Depends(get_password_hasher),
    limit: RateDecision = Depends(login_rate_limit),
) -> Response:
    """Password login. Any failure re-renders the form with a generic error."""
    target = safe_next(next_path)
    if not limit.allowed:
        return throttled_login(request, limit, next_path=target, email=email.strip())
    session = None
    if email.strip() and password:
        session = auth_service.authenticate_password(
            conn,
            email,
            password,
            ip=client_ip(request),
            user_agent=request_user_agent(request),
            hasher=hasher,
            request_ctx=ctx,
        )
    if session is None:
        return login_page(request, next_path=target, email=email.strip(), error=GENERIC_LOGIN_ERROR)
    return start_session(request, conn, settings, session, redirect(target))


# ---------------------------------------------------------------------------
# Passkey login (usernameless)
# ---------------------------------------------------------------------------


@router.post("/login/begin")
def login_passkey_begin(
    request: Request, settings: Settings = Depends(get_settings_dep)
) -> Response:
    """Issue WebAuthn assertion options + the signed challenge cookie."""
    if dev_host_is_ip(request):
        return passkey_host_error()
    challenge = auth_service.authenticate_passkey_begin(relying_party(settings, request))
    return begin_response(settings, challenge, "login", None)


@router.post("/login/finish")
async def login_passkey_finish(
    request: Request,
    *,
    next_path: str | None = Query(default=None, alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    limit: RateDecision = Depends(passkey_login_rate_limit),
) -> Response:
    """Verify the assertion; on success set the session cookie and return ``redirect``."""
    if not limit.allowed:
        return throttled_json(limit)
    body = await json_body(request)
    challenge = challenge_for(request, settings, purpose="login", user_id=None)
    session = None
    if challenge is not None:
        session = auth_service.authenticate_passkey_finish(
            conn,
            body,
            challenge=challenge,
            rp=relying_party(settings, request),
            ip=client_ip(request),
            user_agent=request_user_agent(request),
            request_ctx=ctx,
        )
    if session is None:
        response: Response = JSONResponse(
            {"error": PASSKEY_LOGIN_FAILED}, status_code=HTTPStatus.UNAUTHORIZED
        )
    else:
        response = JSONResponse({"redirect": safe_next(next_path)})
        start_session(request, conn, settings, session, response)
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
    response = redirect(LOGIN_PATH)
    clear_session_cookie(response, settings)
    response.headers["Clear-Site-Data"] = _CLEAR_SITE_DATA
    return response


# ---------------------------------------------------------------------------
# Passkey registration (logged-in user)
# ---------------------------------------------------------------------------


@router.get("/register", response_class=HTMLResponse)
def register_form(_user: CurrentUser = Depends(current_user)) -> RedirectResponse:
    """Legacy URL: passkey registration lives in Settings -> Security (ADR-0075)."""
    return redirect(SECURITY_PASSKEYS_URL)


@router.post("/register/begin", dependencies=[Depends(require_recent_auth)])
def register_passkey_begin(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user: CurrentUser = Depends(current_user),
) -> Response:
    """Issue WebAuthn creation options for the signed-in user."""
    if dev_host_is_ip(request):
        return passkey_host_error()
    try:
        challenge = auth_service.register_passkey_begin(
            conn, user.id, relying_party(settings, request)
        )
    except auth_service.PasskeyRegistrationError as exc:  # pragma: no cover — user is live
        raise HTTPException(HTTPStatus.BAD_REQUEST, detail=exc.reason) from exc
    return begin_response(settings, challenge, "register", user.id)


@router.post("/register/finish", dependencies=[Depends(require_recent_auth)])
async def register_passkey_finish(
    request: Request,
    *,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
    limit: RateDecision = Depends(register_rate_limit),
) -> Response:
    """Verify the attestation and store the passkey. Body: ``{label, credential}``."""
    if not limit.allowed:
        return throttled_json(limit)
    body = await json_body(request)
    challenge = challenge_for(request, settings, purpose="register", user_id=user.id)
    credential = body.get("credential")
    rp = relying_party(settings, request)
    response: Response
    if challenge is None:
        response = JSONResponse({"error": "challenge_expired"}, status_code=HTTPStatus.BAD_REQUEST)
    elif not isinstance(credential, dict):
        response = JSONResponse({"error": "invalid_response"}, status_code=HTTPStatus.BAD_REQUEST)
    else:
        try:
            auth_service.register_passkey_finish(
                conn,
                user.id,
                credential,
                challenge=challenge,
                rp=rp,
                label=auth_service.clean_passkey_label(body.get("label")),
                request_ctx=ctx,
            )
        except auth_service.PasskeyRegistrationError as exc:
            _LOG.warning(
                "passkey_register_failed reason=%s rp_id=%s origin=%s",
                exc.reason,
                rp.rp_id,
                rp.origin,
                exc_info=exc.__cause__,
            )
            response = JSONResponse({"error": exc.reason}, status_code=HTTPStatus.BAD_REQUEST)
        else:
            response = JSONResponse({"redirect": SECURITY_PASSKEYS_URL})
    clear_challenge_cookie(response, settings)
    return response


# ---------------------------------------------------------------------------
# Sessions + passkeys management
# ---------------------------------------------------------------------------


@router.get("/sessions", response_class=HTMLResponse)
def sessions_page(_user: CurrentUser = Depends(current_user)) -> RedirectResponse:
    """Legacy URL: sessions live in Settings -> Security (ADR-0075)."""
    return redirect(SECURITY_SESSIONS_URL)


@router.post("/sessions/{handle}/revoke")
def revoke_session(
    request: Request,
    handle: str,
    *,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
) -> Response:
    """Revoke one of the caller's own sessions, addressed by its handle."""
    if not auth_service.is_session_handle(handle):
        raise HTTPException(HTTPStatus.NOT_FOUND, detail="not_found")
    current = getattr(request.state, "session_id", None)
    is_current = current is not None and auth_service.session_handle(current) == handle
    # Signing out *this* device is logout; revoking another one needs a fresh login (ADR-0076 §2).
    if not is_current and not is_recently_authenticated(request, conn):
        return reauth_required_response(request)
    device = revoke_flow.session_device(conn, user.id, handle)
    if not auth_service.revoke_user_session(conn, user.id, handle, request_ctx=ctx):
        return revoke_flow.stale("not_found")
    if is_current:
        response = redirect(LOGIN_PATH)
        clear_session_cookie(response, settings)
        response.headers["Clear-Site-Data"] = _CLEAR_SITE_DATA
        return revoke_flow.signed_out_here(request, response)
    return revoke_flow.revoked(request, f"Signed out {device}", redirect(SECURITY_SESSIONS_URL))


@router.post("/passkeys/{credential_id}/revoke", dependencies=[Depends(require_recent_auth)])
def revoke_passkey(
    request: Request,
    credential_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
) -> Response:
    """Soft-delete one of the caller's own passkeys."""
    if not auth_service.revoke_passkey(conn, user.id, credential_id, request_ctx=ctx):
        return revoke_flow.stale("not_found")
    return revoke_flow.revoked(request, "Passkey removed", redirect(SECURITY_PASSKEYS_URL))


# ---------------------------------------------------------------------------
# Step-up re-authentication (T-D53b, ADR-0076 §2 / §4)
# ---------------------------------------------------------------------------


@router.get("/reauth", response_class=HTMLResponse)
def reauth_form(
    request: Request,
    next_path: str | None = Query(default=None, alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    user: CurrentUser = Depends(current_user),
) -> HTMLResponse:
    """Confirm-it's-you page (passkey and/or current password)."""
    return reauth_page(request, conn, user, next_path=reauth_target(next_path))


@router.post("/reauth", response_model=None)
def reauth_password(
    request: Request,
    *,
    password: str = Form(default=""),
    next_path: str = Form(default=DEFAULT_LANDING, alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
    hasher: PasswordHasher = Depends(get_password_hasher),
    limit: RateDecision = Depends(reauth_rate_limit),
) -> Response:
    """Re-authenticate with the current password."""
    target = reauth_target(next_path)
    if not limit.allowed:
        if wants_json(request) or is_hx_request(request):
            return throttled_json(limit)
        page = reauth_page(
            request,
            conn,
            user,
            next_path=target,
            error=RATE_LIMITED_REAUTH_ERROR,
            status_code=HTTPStatus.TOO_MANY_REQUESTS,
            throttled=True,
        )
        page.headers["Retry-After"] = str(limit.retry_after_seconds)
        return page
    if reauth_service.verify_password_reauth(conn, user.id, password, hasher=hasher, ctx=ctx):
        done = reauth_success(
            request,
            conn,
            settings,
            user=user,
            ctx=ctx,
            response=redirect(target),
            method=reauth_service.METHOD_PASSWORD,
        )
        if done is not None:
            return done
    return reauth_page(
        request,
        conn,
        user,
        next_path=target,
        error=GENERIC_REAUTH_ERROR,
        status_code=HTTPStatus.UNAUTHORIZED,
        attempts_left=reauth_attempts_left(request, conn, settings, user),
    )


@router.post("/reauth/begin")
def reauth_passkey_begin(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user: CurrentUser = Depends(current_user),
) -> Response:
    """Assertion options restricted to the signed-in user's own passkeys."""
    if dev_host_is_ip(request):
        return passkey_host_error()
    challenge = reauth_service.passkey_reauth_begin(conn, user.id, relying_party(settings, request))
    if challenge is None:
        return JSONResponse({"error": "no_passkeys"}, status_code=HTTPStatus.BAD_REQUEST)
    return begin_response(settings, challenge, "reauth", user.id)


@router.post("/reauth/finish")
async def reauth_passkey_finish(
    request: Request,
    *,
    next_path: str | None = Query(default=None, alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
    limit: RateDecision = Depends(reauth_rate_limit),
) -> Response:
    """Verify the assertion; on success rotate the session and return ``redirect``."""
    if not limit.allowed:
        return throttled_json(limit)
    body = await json_body(request)
    challenge = challenge_for(request, settings, purpose="reauth", user_id=user.id)
    response: Response = JSONResponse({"error": REAUTH_FAILED}, status_code=HTTPStatus.UNAUTHORIZED)
    if challenge is not None and reauth_service.verify_passkey_reauth(
        conn,
        user.id,
        body,
        challenge=challenge,
        rp=relying_party(settings, request),
        ctx=ctx,
    ):
        rotated = reauth_success(
            request,
            conn,
            settings,
            user=user,
            ctx=ctx,
            response=JSONResponse({"redirect": reauth_target(next_path)}),
            method=reauth_service.METHOD_PASSKEY,
        )
        response = rotated or response
    clear_challenge_cookie(response, settings)
    return response
