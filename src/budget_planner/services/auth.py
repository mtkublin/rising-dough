"""Authentication service: password login, passkey ceremonies, sessions.

Spec: ADR-0033 (as amended by ADR-0061) and ADR-0067. This module is the
only entry point the web layer (T-D02b) needs.

Password login
--------------
``authenticate_password(conn, email, password, *, ip, user_agent,
request_ctx=None) -> Session | None``. The email lookup is case-insensitive
and only matches live users. When the email is unknown, or the user has no
password, a dummy bcrypt verify still runs so response timing does not
reveal which accounts exist. Every outcome is audited. ``None`` means
"generic login failure". The caller must not tell the user why it failed.

Passkey ceremonies (stateless; the caller holds the challenge)
--------------------------------------------------------------
Each ceremony is a ``*_begin`` / ``*_finish`` pair. ``*_begin`` returns a
:class:`PasskeyChallenge`:

* ``options_json`` is sent to the browser for
  ``navigator.credentials.create()`` / ``.get()``;
* ``challenge`` (raw bytes) is **kept by the caller** until the matching
  ``*_finish`` call. The recommended carrier is a short-lived signed cookie
  (``itsdangerous`` + ``settings.cookie_secret``, at most 5 minutes),
  cleared after ``finish`` whatever the outcome. This service never
  persists challenges (ADR-0067 §1).

Registration (the user must already be logged in)::

    ch = register_passkey_begin(conn, user_id, rp)
    # store ch.challenge; send ch.options_json to the browser
    cred = register_passkey_finish(conn, user_id, browser_json,
                                   challenge=stored, rp=rp, label="iPhone",
                                   request_ctx=ctx)
    # raises PasskeyRegistrationError on any failure

Login (usernameless, uses discoverable credentials)::

    ch = authenticate_passkey_begin(rp)
    session = authenticate_passkey_finish(conn, browser_json,
                                          challenge=stored, rp=rp,
                                          ip=ip, user_agent=ua)
    # None means a generic failure

If a response carries a valid signature but its sign count has gone
backwards, the authenticator has probably been cloned. The credential is
auto-revoked and the login fails (ADR-0067 §3).

Sessions
--------
``logout`` revokes the current session. ``revoke_user_session`` revokes one
of the caller's own sessions by id. ``revoke_passkey`` soft-deletes one of
the caller's own passkeys. ``load_session_user`` resolves a cookie value to
``(Session, AuthUser)`` and slides the expiry, which is what the middleware
needs. Audit rows reference sessions by their non-secret
:func:`~budget_planner.repositories.sessions.session_handle`, never the raw
id (ADR-0067 §4).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from typing import Any, Final

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import (
    parse_authentication_credential_json,
    parse_registration_credential_json,
)
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from budget_planner.config import Settings, get_settings
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import (
    auth_users as users_repo,
    sessions as sessions_repo,
    webauthn as webauthn_repo,
)
from budget_planner.repositories._shared import transaction, write_audit
from budget_planner.repositories.auth_users import AuthUser
from budget_planner.repositories.sessions import Session, session_handle
from budget_planner.repositories.webauthn import WebAuthnCredential
from budget_planner.services._passwords import dummy_hash, verify_password

SESSION_ENTITY: Final = "session"
AUTH_EVENT_ENTITY: Final = "auth_event"
UNKNOWN_USER_ENTITY_ID: Final = 0

CredentialPayload = str | dict[str, Any]


@dataclass(frozen=True, slots=True)
class RelyingParty:
    """WebAuthn relying-party identity (ADR-0067 §1)."""

    rp_id: str
    rp_name: str
    origin: str


@dataclass(frozen=True, slots=True)
class PasskeyChallenge:
    """Output of a ``*_begin`` call. The caller stores ``challenge``."""

    options_json: str
    challenge: bytes


class PasskeyRegistrationError(Exception):
    """Passkey registration could not be completed; ``reason`` is a stable code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def relying_party_from_settings(settings: Settings | None = None) -> RelyingParty:
    """Build the :class:`RelyingParty` from ``webauthn_*`` settings."""
    s = get_settings() if settings is None else settings
    return RelyingParty(
        rp_id=s.webauthn_rp_id, rp_name=s.webauthn_rp_name, origin=s.webauthn_origin
    )


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------


def _base_ctx(
    request_ctx: RequestCtx | None, *, ip: str | None, user_agent: str | None
) -> RequestCtx:
    if request_ctx is not None:
        return request_ctx
    return RequestCtx(ip=ip, user_id=None, session_id=None, user_agent=user_agent)


def _audit_login_failure(
    conn: sqlite3.Connection,
    ctx: RequestCtx,
    *,
    method: str,
    reason: str,
    user_id: int | None,
    email: str | None = None,
) -> None:
    payload: dict[str, Any] = {"event": "login_failed", "method": method, "reason": reason}
    if email is not None:
        payload["email"] = email.strip().lower()
    with transaction(conn):
        write_audit(
            conn,
            entity_type=AUTH_EVENT_ENTITY,
            entity_id=UNKNOWN_USER_ENTITY_ID if user_id is None else user_id,
            operation="create",
            prev=None,
            new=payload,
            request_ctx=replace(ctx, user_id=user_id),
        )


def _issue_session(
    conn: sqlite3.Connection,
    user: AuthUser,
    ctx: RequestCtx,
    *,
    method: str,
    ip: str | None,
    user_agent: str | None,
) -> Session:
    with transaction(conn):
        session = sessions_repo.create_session(conn, user.id, ip=ip, user_agent=user_agent)
        write_audit(
            conn,
            entity_type=SESSION_ENTITY,
            entity_id=user.id,
            operation="create",
            prev=None,
            new={
                "event": "login",
                "method": method,
                "session": session.handle,
                "expires_at": session.expires_at.isoformat(),
            },
            request_ctx=replace(ctx, user_id=user.id, session_id=session.handle),
        )
    return session


# ---------------------------------------------------------------------------
# Password login
# ---------------------------------------------------------------------------


def authenticate_password(
    conn: sqlite3.Connection,
    email: str,
    password: str,
    *,
    ip: str | None,
    user_agent: str | None,
    request_ctx: RequestCtx | None = None,
) -> Session | None:
    """Verify ``email`` + ``password`` and open a session; ``None`` on any failure."""
    ctx = _base_ctx(request_ctx, ip=ip, user_agent=user_agent)
    user = users_repo.find_live_by_email(conn, email)
    if user is None or not user.password_hash:
        verify_password(password, dummy_hash())  # equalize timing
        _audit_login_failure(
            conn,
            ctx,
            method="password",
            reason="unknown_email" if user is None else "no_password",
            user_id=None if user is None else user.id,
            email=email,
        )
        return None
    if not verify_password(password, user.password_hash):
        _audit_login_failure(
            conn, ctx, method="password", reason="bad_password", user_id=user.id, email=email
        )
        return None
    return _issue_session(conn, user, ctx, method="password", ip=ip, user_agent=user_agent)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def _revoke(
    conn: sqlite3.Connection, session: Session, *, event: str, request_ctx: RequestCtx | None
) -> bool:
    ctx = request_ctx or RequestCtx(
        ip=None, user_id=session.user_id, session_id=None, user_agent=None
    )
    with transaction(conn):
        if not sessions_repo.revoke_session(conn, session.id):
            return False  # pragma: no cover — raced with another revoke
        write_audit(
            conn,
            entity_type=SESSION_ENTITY,
            entity_id=session.user_id,
            operation="delete",
            prev={"event": event, "session": session.handle},
            new=None,
            request_ctx=ctx,
        )
    return True


def logout(
    conn: sqlite3.Connection, session_id: str, *, request_ctx: RequestCtx | None = None
) -> bool:
    """Revoke the live session ``session_id``. Returns ``False`` if not live."""
    session = sessions_repo.get_session(conn, session_id)
    if session is None:
        return False
    return _revoke(conn, session, event="logout", request_ctx=request_ctx)


def revoke_user_session(
    conn: sqlite3.Connection,
    user_id: int,
    session_id: str,
    *,
    request_ctx: RequestCtx | None = None,
) -> bool:
    """Revoke ``session_id`` only if it is live and owned by ``user_id``."""
    session = sessions_repo.get_session(conn, session_id)
    if session is None or session.user_id != user_id:
        return False
    return _revoke(conn, session, event="session_revoked", request_ctx=request_ctx)


def load_session_user(
    conn: sqlite3.Connection, session_id: str, *, touch: bool = True
) -> tuple[Session, AuthUser] | None:
    """Resolve a cookie value to its live session + user, sliding expiry if ``touch``."""
    session = sessions_repo.get_session(conn, session_id)
    if session is None:
        return None
    user = users_repo.get_live_by_id(conn, session.user_id)
    if user is None:  # pragma: no cover — get_session already joins on live users
        return None
    if touch:
        sessions_repo.touch_session(conn, session.id)
    return session, user


# ---------------------------------------------------------------------------
# Passkey registration
# ---------------------------------------------------------------------------


def register_passkey_begin(
    conn: sqlite3.Connection, user_id: int, rp: RelyingParty
) -> PasskeyChallenge:
    """Start passkey registration for the logged-in ``user_id``."""
    user = users_repo.get_live_by_id(conn, user_id)
    if user is None:
        raise PasskeyRegistrationError("unknown_user")
    existing = webauthn_repo.list_credentials(conn, user_id)
    options = generate_registration_options(
        rp_id=rp.rp_id,
        rp_name=rp.rp_name,
        user_id=str(user.id).encode("ascii"),
        user_name=user.email or user.name,
        user_display_name=user.name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=c.credential_id) for c in existing],
    )
    return PasskeyChallenge(options_json=options_to_json(options), challenge=options.challenge)


def register_passkey_finish(
    conn: sqlite3.Connection,
    user_id: int,
    credential: CredentialPayload,
    *,
    challenge: bytes,
    rp: RelyingParty,
    label: str,
    request_ctx: RequestCtx | None = None,
) -> WebAuthnCredential:
    """Verify the browser's attestation and persist the new passkey.

    Raises :class:`PasskeyRegistrationError` with reason ``unknown_user``,
    ``invalid_response``, or ``duplicate_credential``.
    """
    if users_repo.get_live_by_id(conn, user_id) is None:
        raise PasskeyRegistrationError("unknown_user")
    try:
        parsed = parse_registration_credential_json(credential)
        verified = verify_registration_response(
            credential=parsed,
            expected_challenge=challenge,
            expected_rp_id=rp.rp_id,
            expected_origin=rp.origin,
            require_user_verification=True,
        )
    except WebAuthnException as exc:
        raise PasskeyRegistrationError("invalid_response") from exc
    transports = tuple(t.value for t in (parsed.response.transports or ()))
    ctx = request_ctx or RequestCtx(ip=None, user_id=user_id, session_id=None, user_agent=None)
    try:
        return webauthn_repo.create_credential(
            conn,
            user_id=user_id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            transports=transports,
            label=label.strip(),
            request_ctx=ctx,
        )
    except sqlite3.IntegrityError as exc:
        raise PasskeyRegistrationError("duplicate_credential") from exc


def revoke_passkey(
    conn: sqlite3.Connection,
    user_id: int,
    credential_row_id: int,
    *,
    request_ctx: RequestCtx | None = None,
) -> bool:
    """Soft-delete one of ``user_id``'s own passkeys."""
    ctx = request_ctx or RequestCtx(ip=None, user_id=user_id, session_id=None, user_agent=None)
    return webauthn_repo.revoke_credential(
        conn, credential_row_id, user_id=user_id, reason="user_request", request_ctx=ctx
    )


# ---------------------------------------------------------------------------
# Passkey login
# ---------------------------------------------------------------------------


def authenticate_passkey_begin(rp: RelyingParty) -> PasskeyChallenge:
    """Start a usernameless passkey login (discoverable credentials)."""
    options = generate_authentication_options(
        rp_id=rp.rp_id,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return PasskeyChallenge(options_json=options_to_json(options), challenge=options.challenge)


def sign_count_regressed(stored: int, new: int) -> bool:
    """WebAuthn §6.1.1: a non-zero counter must strictly increase."""
    return (new > 0 or stored > 0) and new <= stored


def authenticate_passkey_finish(
    conn: sqlite3.Connection,
    credential: CredentialPayload,
    *,
    challenge: bytes,
    rp: RelyingParty,
    ip: str | None,
    user_agent: str | None,
    request_ctx: RequestCtx | None = None,
) -> Session | None:
    """Verify the browser's assertion and open a session; ``None`` on failure."""
    ctx = _base_ctx(request_ctx, ip=ip, user_agent=user_agent)
    try:
        parsed = parse_authentication_credential_json(credential)
    except WebAuthnException:
        _audit_login_failure(conn, ctx, method="passkey", reason="malformed", user_id=None)
        return None
    stored = webauthn_repo.get_by_credential_id(conn, parsed.raw_id)
    user = None if stored is None else users_repo.get_live_by_id(conn, stored.user_id)
    if stored is None or user is None:
        _audit_login_failure(conn, ctx, method="passkey", reason="unknown_credential", user_id=None)
        return None
    try:
        verified = verify_authentication_response(
            credential=parsed,
            expected_challenge=challenge,
            expected_rp_id=rp.rp_id,
            expected_origin=rp.origin,
            credential_public_key=stored.public_key,
            # 0 disables the library's pre-signature counter check; we compare
            # after the signature is proven valid (ADR-0067 §3).
            credential_current_sign_count=0,
            require_user_verification=True,
        )
    except WebAuthnException:
        _audit_login_failure(
            conn, ctx, method="passkey", reason="verification_failed", user_id=user.id
        )
        return None
    if sign_count_regressed(stored.sign_count, verified.new_sign_count):
        webauthn_repo.revoke_credential(
            conn,
            stored.id,
            reason="sign_count_regression",
            request_ctx=replace(ctx, user_id=user.id),
        )
        _audit_login_failure(
            conn, ctx, method="passkey", reason="sign_count_regression", user_id=user.id
        )
        return None
    with transaction(conn):
        webauthn_repo.update_sign_count(conn, stored.id, verified.new_sign_count)
        return _issue_session(conn, user, ctx, method="passkey", ip=ip, user_agent=user_agent)


__all__ = [
    "AUTH_EVENT_ENTITY",
    "SESSION_ENTITY",
    "PasskeyChallenge",
    "PasskeyRegistrationError",
    "RelyingParty",
    "authenticate_passkey_begin",
    "authenticate_passkey_finish",
    "authenticate_password",
    "load_session_user",
    "logout",
    "register_passkey_begin",
    "register_passkey_finish",
    "relying_party_from_settings",
    "revoke_passkey",
    "revoke_user_session",
    "session_handle",
    "sign_count_regressed",
]
