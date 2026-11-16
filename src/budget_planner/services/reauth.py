"""Step-up re-authentication (T-D53b, ADR-0076 §2 and §4).

A signed-in user proves a credential again (current password, or a passkey
they own) before an account-takeover action. On success the session's
``authenticated_at`` is refreshed and its token is rotated in place
(``created_at`` is kept, so the absolute cap cannot be reset).

Every outcome is audited as an ``auth_event`` row (``reauth`` /
``reauth_failed`` with ``method`` and, on failure, ``reason``).
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime
from typing import Any, Final

from webauthn import (
    generate_authentication_options,
    options_to_json,
    verify_authentication_response,
)
from webauthn.helpers import parse_authentication_credential_json
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import (
    auth_users as users_repo,
    sessions as sessions_repo,
    webauthn as webauthn_repo,
)
from budget_planner.repositories._shared import transaction, write_audit
from budget_planner.repositories.sessions import IssuedSession
from budget_planner.services._passwords import dummy_hash, verify_password
from budget_planner.services.auth import (
    AUTH_EVENT_ENTITY,
    CredentialPayload,
    PasskeyChallenge,
    RelyingParty,
    sign_count_regressed,
)

METHOD_PASSWORD: Final = "password"  # noqa: S105  # method name, not a secret
METHOD_PASSKEY: Final = "passkey"


def _audit(
    conn: sqlite3.Connection,
    ctx: RequestCtx,
    user_id: int,
    payload: dict[str, Any],
) -> None:
    with transaction(conn):
        write_audit(
            conn,
            entity_type=AUTH_EVENT_ENTITY,
            entity_id=user_id,
            operation="create",
            prev=None,
            new=payload,
            request_ctx=replace(ctx, user_id=user_id),
        )


def _fail(
    conn: sqlite3.Connection, ctx: RequestCtx, user_id: int, method: str, reason: str
) -> None:
    _audit(conn, ctx, user_id, {"event": "reauth_failed", "method": method, "reason": reason})


def verify_password_reauth(
    conn: sqlite3.Connection, user_id: int, password: str, *, ctx: RequestCtx
) -> bool:
    """Check ``password`` against the user's current hash; audit failures."""
    user = users_repo.get_live_by_id(conn, user_id)
    if user is None or not user.password_hash:
        verify_password(password, dummy_hash())  # equalize timing
        _fail(conn, ctx, user_id, METHOD_PASSWORD, "no_password")
        return False
    if not password or not verify_password(password, user.password_hash):
        _fail(conn, ctx, user_id, METHOD_PASSWORD, "bad_password")
        return False
    return True


def passkey_reauth_begin(
    conn: sqlite3.Connection, user_id: int, rp: RelyingParty
) -> PasskeyChallenge | None:
    """Assertion options limited to the user's own credentials; ``None`` if they have none."""
    credentials = webauthn_repo.list_credentials(conn, user_id)
    if not credentials:
        return None
    options = generate_authentication_options(
        rp_id=rp.rp_id,
        allow_credentials=[PublicKeyCredentialDescriptor(id=c.credential_id) for c in credentials],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return PasskeyChallenge(options_json=options_to_json(options), challenge=options.challenge)


def verify_passkey_reauth(
    conn: sqlite3.Connection,
    user_id: int,
    credential: CredentialPayload,
    *,
    challenge: bytes,
    rp: RelyingParty,
    ctx: RequestCtx,
) -> bool:
    """Verify an assertion made with one of ``user_id``'s own passkeys."""
    try:
        parsed = parse_authentication_credential_json(credential)
    except WebAuthnException:
        _fail(conn, ctx, user_id, METHOD_PASSKEY, "malformed")
        return False
    stored = webauthn_repo.get_by_credential_id(conn, parsed.raw_id)
    if stored is None or stored.user_id != user_id:
        _fail(conn, ctx, user_id, METHOD_PASSKEY, "unknown_credential")
        return False
    try:
        verified = verify_authentication_response(
            credential=parsed,
            expected_challenge=challenge,
            expected_rp_id=rp.rp_id,
            expected_origin=rp.origin,
            credential_public_key=stored.public_key,
            credential_current_sign_count=0,
            require_user_verification=True,
        )
    except WebAuthnException:
        _fail(conn, ctx, user_id, METHOD_PASSKEY, "verification_failed")
        return False
    if sign_count_regressed(stored.sign_count, verified.new_sign_count):
        webauthn_repo.revoke_credential(
            conn,
            user_id,
            stored.id,
            reason="sign_count_regression",
            request_ctx=replace(ctx, user_id=user_id),
        )
        _fail(conn, ctx, user_id, METHOD_PASSKEY, "sign_count_regression")
        return False
    webauthn_repo.update_sign_count(conn, user_id, stored.id, verified.new_sign_count)
    return True


def complete_reauth(
    conn: sqlite3.Connection,
    token: str,
    user_id: int,
    *,
    method: str,
    ctx: RequestCtx,
    now: datetime | None = None,
) -> IssuedSession | None:
    """Refresh ``authenticated_at``, rotate the token, audit. ``None`` if not live."""
    with transaction(conn):
        if not sessions_repo.mark_authenticated(conn, token, now=now):
            return None
        issued = sessions_repo.rotate_session_token(conn, token)
        if issued is None:  # pragma: no cover — raced with a revoke
            return None
        _audit(conn, ctx, user_id, {"event": "reauth", "method": method})
    return issued


__all__ = [
    "METHOD_PASSKEY",
    "METHOD_PASSWORD",
    "complete_reauth",
    "passkey_reauth_begin",
    "verify_passkey_reauth",
    "verify_password_reauth",
]
