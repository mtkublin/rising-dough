"""Request/response plumbing for the auth routes (T-Q267; ADR-0033, ADR-0067, ADR-0070, ADR-0075).

Relying-party resolution, session start, WebAuthn challenge carriage, and the login / re-auth
page renderers. Moved out of ``web/routers/auth.py`` so the router holds only route handlers;
decisions (who may log in, what a re-auth proves) stay in ``services/auth`` and
``services/reauth``.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import sqlite3
from http import HTTPStatus
from typing import Final

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.services import auth as auth_service, reauth as reauth_service
from budget_planner.services.auth import IssuedSession
from budget_planner.services.rate_limit import RateDecision, reauth_rules
from budget_planner.web.auth_cookies import (
    DEFAULT_LANDING,
    Purpose,
    challenge_cookie_name,
    safe_next,
    set_challenge_cookie,
    set_session_cookie,
    sign_challenge,
    verify_challenge,
)
from budget_planner.web.auth_deps import RETRY_AFTER, rate_limit_now, throttled_json
from budget_planner.web.deps import REAUTH_PATH, reauth_now
from budget_planner.web.htmx import wants_json
from budget_planner.web.http_headers import JSON_MEDIA_TYPE
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.rendering import is_hx_request, render

_LOG = logging.getLogger(__name__)
RATE_LIMITED_LOGIN_ERROR: Final = (
    "Too many sign-in attempts. Please wait a few minutes and try again."
)
PASSKEY_HOST_UNSUPPORTED: Final = "passkey_host_unsupported"
_WEBAUTHN_FIELDS: Final = frozenset({"webauthn_rp_id", "webauthn_origin"})


def redirect(url: str) -> RedirectResponse:
    """303 to ``url``."""
    return RedirectResponse(url, status_code=HTTPStatus.SEE_OTHER)


def _is_ip(host: str | None) -> bool:
    try:
        ipaddress.ip_address(host or "")
    except ValueError:
        _LOG.debug("host is not an IP literal: %r", host)
        return False
    return True


def _derives_rp_from_request(settings: Settings) -> bool:
    return settings.env == "dev" and not (_WEBAUTHN_FIELDS & settings.model_fields_set)


def dev_host_is_ip(request: Request) -> bool:
    """True when a dev server is reached by IP literal (never valid as an RP ID)."""
    return _derives_rp_from_request(request.app.state.settings) and _is_ip(request.url.hostname)


def relying_party(settings: Settings, request: Request) -> auth_service.RelyingParty:
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


def passkey_host_error() -> JSONResponse:
    """400 for a dev server reached by IP literal."""
    return JSONResponse({"error": PASSKEY_HOST_UNSUPPORTED}, status_code=HTTPStatus.BAD_REQUEST)


def start_session(
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


async def json_body(request: Request) -> dict[str, object]:
    """Parsed JSON object body; 400 ``invalid_json`` otherwise."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(HTTPStatus.BAD_REQUEST, detail="invalid_json") from exc
    if not isinstance(body, dict):
        raise HTTPException(HTTPStatus.BAD_REQUEST, detail="invalid_json")
    return body


def begin_response(
    settings: Settings,
    challenge: auth_service.PasskeyChallenge,
    purpose: Purpose,
    user_id: int | None,
) -> Response:
    """Options JSON plus the signed challenge cookie."""
    response = Response(content=challenge.options_json, media_type=JSON_MEDIA_TYPE)
    signed = sign_challenge(
        settings, purpose=purpose, user_id=user_id, challenge=challenge.challenge
    )
    set_challenge_cookie(response, settings, signed)
    return response


def challenge_for(
    request: Request, settings: Settings, *, purpose: Purpose, user_id: int | None
) -> bytes | None:
    """Raw WebAuthn challenge from the signed cookie, or ``None`` if missing/invalid/expired."""
    envelope = verify_challenge(
        settings,
        request.cookies.get(challenge_cookie_name(settings)),
        purpose=purpose,
        user_id=user_id,
    )
    return None if envelope is None else envelope.challenge


def login_page(
    request: Request,
    *,
    next_path: str,
    email: str = "",
    error: str | None = None,
    status_code: int | None = None,
    throttled: bool = False,
) -> HTMLResponse:
    """The login form (401 when it carries an error)."""
    default_status = HTTPStatus.UNAUTHORIZED if error else HTTPStatus.OK
    return render(
        request,
        "pages/auth/login.html",
        status_code=default_status if status_code is None else status_code,
        next_path=next_path,
        email=email,
        error=error,
        throttled=throttled,
    )


def throttled_login(
    request: Request, decision: RateDecision, *, next_path: str, email: str
) -> Response:
    """429 for a throttled password login: friendly page for browsers, JSON otherwise."""
    if is_hx_request(request) or wants_json(request):
        return throttled_json(decision)
    response = login_page(
        request,
        next_path=next_path,
        email=email,
        error=RATE_LIMITED_LOGIN_ERROR,
        status_code=HTTPStatus.TOO_MANY_REQUESTS,
        throttled=True,
    )
    response.headers[RETRY_AFTER] = str(decision.retry_after_seconds)
    return response


def reauth_target(next_path: str | None) -> str:
    """Sanitised post-re-auth landing path (never the re-auth page itself)."""
    target = safe_next(next_path)
    path = target.split("?", 1)[0]
    return DEFAULT_LANDING if path == REAUTH_PATH or path.startswith(f"{REAUTH_PATH}/") else target


def reauth_page(
    request: Request,
    conn: sqlite3.Connection,
    user: CurrentUser,
    *,
    next_path: str,
    error: str | None = None,
    status_code: int = HTTPStatus.OK,
    throttled: bool = False,
    attempts_left: int | None = None,
) -> HTMLResponse:
    """The confirm-it's-you page (``attempts_left``: rendered in the field error)."""
    return render(
        request,
        "pages/auth/reauth.html",
        status_code=status_code,
        next_path=next_path,
        error=error,
        throttled=throttled,
        attempts_left=attempts_left,
        has_passkeys=bool(auth_service.list_passkeys(conn, user.id)),
        current_user=user,
    )


def reauth_attempts_left(
    request: Request, conn: sqlite3.Connection, settings: Settings, user: CurrentUser
) -> int | None:
    """Re-auth attempts the signed-in user has left in the current windows (G8)."""
    return reauth_service.attempts_left(
        conn, user.id, reauth_rules(settings), now=rate_limit_now(request)
    )


def reauth_success(
    request: Request,
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    user: CurrentUser,
    ctx: RequestCtx,
    response: Response,
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
