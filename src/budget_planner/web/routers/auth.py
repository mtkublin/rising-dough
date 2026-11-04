"""Auth routes: login (password + passkey), logout, passkey registration,
session / passkey management (T-D02b; ADR-0033, ADR-0061, ADR-0067, ADR-0070).

Thin layer over :mod:`budget_planner.services.auth`. Cookie plumbing lives in
:mod:`budget_planner.web.auth_cookies`. Login failures always yield the same
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

import ipaddress
import json
import logging
import re
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any, Final

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import webauthn as webauthn_repo
from budget_planner.repositories.sessions import IssuedSession, session_handle
from budget_planner.services import auth as auth_service, rate_limit, reauth as reauth_service
from budget_planner.services.rate_limit import RateDecision
from budget_planner.web.auth_cookies import (
    DEFAULT_LANDING,
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
    REAUTH_PATH,
    current_user,
    get_db,
    get_request_ctx,
    get_settings_dep,
    is_recently_authenticated,
    reauth_now,
    reauth_required_response,
    require_recent_auth,
)
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.rendering import is_hx_request, render

_LOG = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_LOGIN_ERROR: Final = "That email and password combination didn't work."
RATE_LIMITED_LOGIN_ERROR: Final = (
    "Too many sign-in attempts. Please wait a few minutes and try again."
)
RATE_LIMITED: Final = "rate_limited"
PASSKEY_LOGIN_FAILED: Final = "login_failed"
SECURITY_SESSIONS_URL: Final = "/settings/security#sessions"
SECURITY_PASSKEYS_URL: Final = "/settings/security#passkeys"
LABEL_MAX_LENGTH: Final = 64
DEFAULT_PASSKEY_LABEL: Final = "Passkey"
_HANDLE_RE: Final = re.compile(r"^[0-9a-f]{16}$")
_SEE_OTHER: Final = HTTPStatus.SEE_OTHER


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ---------------------------------------------------------------------------
# Rate limiting (T-D09, ADR-0072)
# ---------------------------------------------------------------------------


def _rate_limit_now(request: Request) -> datetime:
    clock: Callable[[], datetime] | None = getattr(request.app.state, "rate_limit_clock", None)
    return clock() if clock is not None else datetime.now(UTC)


def _ip_identity(request: Request) -> str:
    return f"ip={_client_ip(request) or 'unknown'}"


def _wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "").lower()
    return "application/json" in accept and "text/html" not in accept


def _throttled_json(decision: RateDecision) -> JSONResponse:
    return JSONResponse(
        {"error": RATE_LIMITED},
        status_code=HTTPStatus.TOO_MANY_REQUESTS,
        headers={"Retry-After": str(decision.retry_after_seconds)},
    )


def login_rate_limit(
    request: Request,
    email: str = Form(default=""),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
) -> RateDecision:
    """Count one password-login attempt per IP+email and per IP."""
    now = _rate_limit_now(request)
    ip = _ip_identity(request)
    normalised = rate_limit.normalise_email(email)
    decision = rate_limit.combine(
        rate_limit.consume(
            conn,
            rate_limit.SCOPE_LOGIN,
            f"{ip}|email={normalised}",
            rate_limit.login_rules(settings),
            now=now,
        ),
        rate_limit.consume(
            conn, rate_limit.SCOPE_LOGIN_IP, ip, rate_limit.login_ip_rules(settings), now=now
        ),
    )
    if not decision.allowed:
        rate_limit.audit_throttled(conn, ctx, scope=decision.scope, email=normalised or None)
    return decision


def passkey_login_rate_limit(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
) -> RateDecision:
    """Count one passkey-login finish per IP."""
    decision = rate_limit.consume(
        conn,
        rate_limit.SCOPE_PASSKEY_LOGIN,
        _ip_identity(request),
        rate_limit.passkey_login_rules(settings),
        now=_rate_limit_now(request),
    )
    if not decision.allowed:
        rate_limit.audit_throttled(conn, ctx, scope=decision.scope)
    return decision


def register_rate_limit(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
) -> RateDecision:
    """Count one passkey-registration finish per signed-in user."""
    decision = rate_limit.consume(
        conn,
        rate_limit.SCOPE_REGISTER,
        f"user={user.id}",
        rate_limit.register_rules(settings),
        now=_rate_limit_now(request),
    )
    if not decision.allowed:
        rate_limit.audit_throttled(conn, ctx, scope=decision.scope, user_id=user.id)
    return decision


def reauth_rate_limit(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
) -> RateDecision:
    """Count one re-auth attempt per signed-in user (T-D53b, ADR-0076 §2)."""
    decision = rate_limit.consume(
        conn,
        rate_limit.SCOPE_REAUTH,
        f"user={user.id}",
        rate_limit.reauth_rules(settings),
        now=_rate_limit_now(request),
    )
    if not decision.allowed:
        rate_limit.audit_throttled(conn, ctx, scope=decision.scope, user_id=user.id)
    return decision


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=_SEE_OTHER)


_WEBAUTHN_FIELDS: Final = frozenset({"webauthn_rp_id", "webauthn_origin"})
PASSKEY_HOST_UNSUPPORTED: Final = "passkey_host_unsupported"


def _dev_host_is_ip(request: Request) -> bool:
    """True when a dev server is reached by IP literal (never valid as an RP ID)."""
    return _derives_rp_from_request(request.app.state.settings) and _is_ip(request.url.hostname)


def _derives_rp_from_request(settings: Settings) -> bool:
    return settings.env == "dev" and not (_WEBAUTHN_FIELDS & settings.model_fields_set)


def _is_ip(host: str | None) -> bool:
    try:
        ipaddress.ip_address(host or "")
    except ValueError:
        return False
    return True


def _rp(settings: Settings, request: Request) -> auth_service.RelyingParty:
    """Relying party from settings; in dev with unset WebAuthn env, from the request.

    ``just dev`` may run on any port (and be opened as localhost), while the
    static defaults pin ``http://localhost:8000``; deriving the origin keeps
    passkeys working there (ADR-0075). Production always uses explicit settings.
    """
    rp = auth_service.relying_party_from_settings(settings)
    if not _derives_rp_from_request(settings):
        return rp
    return auth_service.RelyingParty(
        rp_id=request.url.hostname or rp.rp_id,
        rp_name=rp.rp_name,
        origin=f"{request.url.scheme}://{request.url.netloc}",
    )


def _passkey_host_error() -> JSONResponse:
    return JSONResponse({"error": PASSKEY_HOST_UNSUPPORTED}, status_code=HTTPStatus.BAD_REQUEST)


def _start_session(
    request: Request,
    conn: sqlite3.Connection,
    settings: Settings,
    issued: IssuedSession,
    response: Response,
) -> Response:
    """Revoke any session the browser already held, then set the new cookie."""
    previous = getattr(request.state, "session_id", None)
    if previous and previous != issued.token:
        auth_service.logout(conn, previous)
    set_session_cookie(response, settings, issued.token, expires_at=issued.session.expires_at)
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
    request: Request,
    *,
    next_path: str,
    email: str = "",
    error: str | None = None,
    status_code: int | None = None,
    throttled: bool = False,
) -> HTMLResponse:
    default_status = HTTPStatus.UNAUTHORIZED if error else HTTPStatus.OK
    return render(
        request,
        "auth/login.html",
        status_code=default_status if status_code is None else status_code,
        next_path=next_path,
        email=email,
        error=error,
        throttled=throttled,
    )


def _throttled_login(
    request: Request, decision: RateDecision, *, next_path: str, email: str
) -> Response:
    """429 for a throttled password login: friendly page for browsers, JSON otherwise."""
    if is_hx_request(request) or _wants_json(request):
        return _throttled_json(decision)
    response = _login_page(
        request,
        next_path=next_path,
        email=email,
        error=RATE_LIMITED_LOGIN_ERROR,
        status_code=HTTPStatus.TOO_MANY_REQUESTS,
        throttled=True,
    )
    response.headers["Retry-After"] = str(decision.retry_after_seconds)
    return response


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
    next_path: str = Form(default=DEFAULT_LANDING, alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    limit: RateDecision = Depends(login_rate_limit),
) -> Response:
    """Password login. Any failure re-renders the form with a generic error."""
    target = safe_next(next_path)
    if not limit.allowed:
        return _throttled_login(request, limit, next_path=target, email=email.strip())
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
def login_passkey_begin(
    request: Request, settings: Settings = Depends(get_settings_dep)
) -> Response:
    """Issue WebAuthn assertion options + the signed challenge cookie."""
    if _dev_host_is_ip(request):
        return _passkey_host_error()
    challenge = auth_service.authenticate_passkey_begin(_rp(settings, request))
    return _begin_response(settings, challenge, "login", None)


@router.post("/login/finish")
async def login_passkey_finish(  # noqa: PLR0917
    request: Request,
    next_path: str | None = Query(default=None, alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    limit: RateDecision = Depends(passkey_login_rate_limit),
) -> Response:
    """Verify the assertion; on success set the session cookie and return ``redirect``."""
    if not limit.allowed:
        return _throttled_json(limit)
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
            rp=_rp(settings, request),
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
def register_form(_user: CurrentUser = Depends(current_user)) -> RedirectResponse:
    """Legacy URL: passkey registration lives in Settings -> Security (ADR-0075)."""
    return _redirect(SECURITY_PASSKEYS_URL)


@router.post("/register/begin", dependencies=[Depends(require_recent_auth)])
def register_passkey_begin(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user: CurrentUser = Depends(current_user),
) -> Response:
    """Issue WebAuthn creation options for the signed-in user."""
    if _dev_host_is_ip(request):
        return _passkey_host_error()
    try:
        challenge = auth_service.register_passkey_begin(conn, user.id, _rp(settings, request))
    except auth_service.PasskeyRegistrationError as exc:  # pragma: no cover — user is live
        raise HTTPException(HTTPStatus.BAD_REQUEST, detail=exc.reason) from exc
    return _begin_response(settings, challenge, "register", user.id)


def _clean_label(raw: object) -> str:
    label = raw.strip() if isinstance(raw, str) else ""
    return (label or DEFAULT_PASSKEY_LABEL)[:LABEL_MAX_LENGTH]


@router.post("/register/finish", dependencies=[Depends(require_recent_auth)])
async def register_passkey_finish(  # noqa: PLR0917
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
    limit: RateDecision = Depends(register_rate_limit),
) -> Response:
    """Verify the attestation and store the passkey. Body: ``{label, credential}``."""
    if not limit.allowed:
        return _throttled_json(limit)
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
                rp=_rp(settings, request),
                label=_clean_label(body.get("label")),
                request_ctx=ctx,
            )
        except auth_service.PasskeyRegistrationError as exc:
            _LOG.warning(
                "passkey_register_failed reason=%s rp_id=%s origin=%s",
                exc.reason,
                _rp(settings, request).rp_id,
                _rp(settings, request).origin,
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
    return _redirect(SECURITY_SESSIONS_URL)


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
    current = getattr(request.state, "session_id", None)
    is_current = current is not None and session_handle(current) == handle
    # Signing out *this* device is logout; revoking another one needs a fresh login (ADR-0076 §2).
    if not is_current and not is_recently_authenticated(request, conn):
        return reauth_required_response(request)
    if not auth_service.revoke_user_session(conn, user.id, handle, request_ctx=ctx):
        raise HTTPException(HTTPStatus.NOT_FOUND, detail="not_found")
    if is_current:
        response = _redirect(LOGIN_PATH)
        clear_session_cookie(response, settings)
        return response
    return _redirect(SECURITY_SESSIONS_URL)


@router.post("/passkeys/{credential_id}/revoke", dependencies=[Depends(require_recent_auth)])
def revoke_passkey(
    credential_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
) -> Response:
    """Soft-delete one of the caller's own passkeys."""
    if not auth_service.revoke_passkey(conn, user.id, credential_id, request_ctx=ctx):
        raise HTTPException(HTTPStatus.NOT_FOUND, detail="not_found")
    return _redirect(SECURITY_PASSKEYS_URL)


# ---------------------------------------------------------------------------
# Step-up re-authentication (T-D53b, ADR-0076 §2 / §4)
# ---------------------------------------------------------------------------

REAUTH_FAILED: Final = "reauth_failed"
GENERIC_REAUTH_ERROR: Final = "That password didn't work."
RATE_LIMITED_REAUTH_ERROR: Final = "Too many attempts. Please wait a few minutes and try again."


def _reauth_target(next_path: str | None) -> str:
    target = safe_next(next_path)
    path = target.split("?", 1)[0]
    return DEFAULT_LANDING if path == REAUTH_PATH or path.startswith(f"{REAUTH_PATH}/") else target


def _reauth_page(
    request: Request,
    conn: sqlite3.Connection,
    user: CurrentUser,
    *,
    next_path: str,
    error: str | None = None,
    status_code: int = HTTPStatus.OK,
    throttled: bool = False,
) -> HTMLResponse:
    return render(
        request,
        "auth/reauth.html",
        status_code=status_code,
        next_path=next_path,
        error=error,
        throttled=throttled,
        has_passkeys=bool(webauthn_repo.list_credentials(conn, user.id)),
        current_user=user,
    )


def _reauth_success(  # noqa: PLR0917
    request: Request,
    conn: sqlite3.Connection,
    settings: Settings,
    user: CurrentUser,
    ctx: RequestCtx,
    response: Response,
    *,
    method: str,
) -> Response | None:
    """Refresh + rotate the session and attach the new cookie; ``None`` if it vanished."""
    token = getattr(request.state, "session_id", None)
    issued = (
        reauth_service.complete_reauth(
            conn, token, user.id, method=method, ctx=ctx, now=reauth_now(request)
        )
        if token
        else None
    )
    if issued is None:
        return None
    set_session_cookie(response, settings, issued.token, expires_at=issued.session.expires_at)
    return response


@router.get("/reauth", response_class=HTMLResponse)
def reauth_form(
    request: Request,
    next_path: str | None = Query(default=None, alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    user: CurrentUser = Depends(current_user),
) -> HTMLResponse:
    """Confirm-it's-you page (passkey and/or current password)."""
    return _reauth_page(request, conn, user, next_path=_reauth_target(next_path))


@router.post("/reauth", response_model=None)
def reauth_password(  # noqa: PLR0917
    request: Request,
    password: str = Form(default=""),
    next_path: str = Form(default=DEFAULT_LANDING, alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
    limit: RateDecision = Depends(reauth_rate_limit),
) -> Response:
    """Re-authenticate with the current password."""
    target = _reauth_target(next_path)
    if not limit.allowed:
        if _wants_json(request) or is_hx_request(request):
            return _throttled_json(limit)
        page = _reauth_page(
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
    if reauth_service.verify_password_reauth(conn, user.id, password, ctx=ctx):
        done = _reauth_success(
            request, conn, settings, user, ctx, _redirect(target),
            method=reauth_service.METHOD_PASSWORD,
        )  # fmt: skip
        if done is not None:
            return done
    return _reauth_page(
        request,
        conn,
        user,
        next_path=target,
        error=GENERIC_REAUTH_ERROR,
        status_code=HTTPStatus.UNAUTHORIZED,
    )


@router.post("/reauth/begin")
def reauth_passkey_begin(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user: CurrentUser = Depends(current_user),
) -> Response:
    """Assertion options restricted to the signed-in user's own passkeys."""
    if _dev_host_is_ip(request):
        return _passkey_host_error()
    challenge = reauth_service.passkey_reauth_begin(conn, user.id, _rp(settings, request))
    if challenge is None:
        return JSONResponse({"error": "no_passkeys"}, status_code=HTTPStatus.BAD_REQUEST)
    return _begin_response(settings, challenge, "reauth", user.id)


@router.post("/reauth/finish")
async def reauth_passkey_finish(  # noqa: PLR0917
    request: Request,
    next_path: str | None = Query(default=None, alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
    limit: RateDecision = Depends(reauth_rate_limit),
) -> Response:
    """Verify the assertion; on success rotate the session and return ``redirect``."""
    if not limit.allowed:
        return _throttled_json(limit)
    body = await _json_body(request)
    envelope = verify_challenge(
        settings,
        request.cookies.get(challenge_cookie_name(settings)),
        purpose="reauth",
        user_id=user.id,
    )
    response: Response = JSONResponse({"error": REAUTH_FAILED}, status_code=HTTPStatus.UNAUTHORIZED)
    if envelope is not None and reauth_service.verify_passkey_reauth(
        conn, user.id, body, challenge=envelope.challenge, rp=_rp(settings, request), ctx=ctx
    ):
        success = JSONResponse({"redirect": _reauth_target(next_path)})
        response = (
            _reauth_success(
                request, conn, settings, user, ctx, success, method=reauth_service.METHOD_PASSKEY
            )
            or response
        )
    clear_challenge_cookie(response, settings)
    return response
