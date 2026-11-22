"""Settings -> Security view model (T-Q267): active sessions and passkeys of one user.

Replaces the router-side ``security_context`` arithmetic (absolute session expiry); the web layer
adds the request-bound pieces (current user, template flags).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from budget_planner.repositories.sessions import Session
from budget_planner.repositories.webauthn import WebAuthnCredential
from budget_planner.services import auth as auth_service


@dataclass(frozen=True, slots=True)
class SessionRow:
    """One active session as the Security page shows it."""

    session: Session
    is_current: bool
    absolute_expires_at: datetime


@dataclass(frozen=True, slots=True)
class SecurityView:
    """Sessions and passkeys of the signed-in user."""

    session_rows: tuple[SessionRow, ...]
    passkeys: tuple[WebAuthnCredential, ...]


def security_view(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    session_token: str | None,
    absolute_lifetime_days: int,
) -> SecurityView:
    """Active sessions (current one flagged, absolute expiry added) plus passkeys."""
    current_handle = auth_service.session_handle(session_token) if session_token else None
    absolute = timedelta(days=absolute_lifetime_days)
    rows = tuple(
        SessionRow(
            session=s,
            is_current=s.handle == current_handle,
            absolute_expires_at=s.created_at + absolute,
        )
        for s in auth_service.list_active_sessions(conn, user_id)
    )
    return SecurityView(session_rows=rows, passkeys=auth_service.list_passkeys(conn, user_id))
