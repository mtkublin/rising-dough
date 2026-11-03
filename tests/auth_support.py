"""Shared login helpers for web / e2e / visual tests (T-D02b, ADR-0070).

Every protected route now needs a live session. These helpers seed a
password on a user row and mint a real server-side session in the given
(scratch) DB so tests can attach the session cookie without driving the
login form each time. Never point them at ``data/budget.sqlite``.
"""

from __future__ import annotations

import sqlite3
from typing import Final

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.repositories import sessions as sessions_repo
from budget_planner.services import _passwords
from budget_planner.web.auth_cookies import session_cookie_name

TEST_EMAIL: Final = "owner@example.test"
TEST_PASSWORD: Final = "correct-horse-battery"  # noqa: S105  # pragma: allowlist secret
FAST_ROUNDS: Final = 4


def seed_login_user(
    conn: sqlite3.Connection,
    *,
    user_id: int = 1,
    email: str = TEST_EMAIL,
    password: str = TEST_PASSWORD,
) -> int:
    """Give ``user_id`` an email + bcrypt (cost 4) password; insert it if missing."""
    password_hash = _passwords.hash_password(password, rounds=FAST_ROUNDS)
    exists = conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone()
    if exists:
        conn.execute(
            "UPDATE users SET email = ?, password_hash = ? WHERE id = ?",
            (email, password_hash, user_id),
        )
    else:
        conn.execute(
            "INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)",
            (user_id, email.split("@", 1)[0], email, password_hash),
        )
    conn.commit()
    return user_id


def issue_session(conn: sqlite3.Connection, *, user_id: int = 1) -> str:
    """Create a live session for ``user_id`` and return its raw id (cookie value)."""
    return sessions_repo.create_session(conn, user_id, ip="127.0.0.1", user_agent="pytest").id


def login_cookie(
    settings: Settings, *, user_id: int = 1, email: str = TEST_EMAIL
) -> tuple[str, str]:
    """Seed the user + a session in ``settings``' DB; return ``(cookie name, value)``."""
    conn = get_connection(settings)
    try:
        seed_login_user(conn, user_id=user_id, email=email)
        session_id = issue_session(conn, user_id=user_id)
    finally:
        conn.close()
    return session_cookie_name(settings), session_id


__all__ = [
    "FAST_ROUNDS",
    "TEST_EMAIL",
    "TEST_PASSWORD",
    "issue_session",
    "login_cookie",
    "seed_login_user",
]
