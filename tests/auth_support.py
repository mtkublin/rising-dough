"""Shared login helpers for web / e2e / visual tests (T-D02b, ADR-0070).

Every protected route now needs a live session. These helpers seed a
password on a user row and mint a real server-side session in the given
(scratch) DB so tests can attach the session cookie without driving the
login form each time. Never point them at ``data/budget.sqlite``.
"""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Final

from budget_planner.adapters.bcrypt_hasher import BcryptHasher
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.ports import MailMessage, MailSendError, PasswordHasher
from budget_planner.repositories import sessions as sessions_repo
from budget_planner.web.auth_cookies import session_cookie_name

TEST_EMAIL: Final = "owner@example.test"
TEST_PASSWORD: Final = "correct-horse-battery"  # noqa: S105  # pragma: allowlist secret
FAST_ROUNDS: Final = 4
#: Real bcrypt at the minimum cost (web-edge tests); services use ``FakePasswordHasher``.
FAST_HASHER: Final = BcryptHasher(rounds=FAST_ROUNDS)


def seed_login_user(
    conn: sqlite3.Connection,
    *,
    user_id: int = 1,
    email: str = TEST_EMAIL,
    password: str = TEST_PASSWORD,
    hasher: PasswordHasher = FAST_HASHER,
) -> int:
    """Give ``user_id`` an email + bcrypt (cost 4) password; insert it if missing."""
    password_hash = hasher.hash(password)
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
    return sessions_repo.create_session(conn, user_id, ip="127.0.0.1", user_agent="pytest").token


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
    "FAKE_HASHER",
    "FAST_HASHER",
    "FAST_ROUNDS",
    "TEST_EMAIL",
    "TEST_PASSWORD",
    "issue_session",
    "login_cookie",
    "seed_login_user",
]


class FakeTokenSource:
    """Deterministic ``TokenSource`` fake: ``tok-<n>-<nbytes>`` (T-Q264)."""

    def __init__(self) -> None:
        self.calls: list[int] = []

    def new_token(self, nbytes: int) -> str:
        self.calls.append(nbytes)
        return f"tok-{len(self.calls)}-{nbytes}"


class FakeMailSender:
    """Recording ``MailSender`` fake (T-UR31); ``fail=True`` raises ``MailSendError``."""

    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[MailMessage] = []
        self.fail = fail

    def send(self, message: MailMessage) -> None:
        if self.fail:
            raise MailSendError("fake mail failure")
        self.sent.append(message)


class FakePasswordHasher:
    """Instant deterministic ``PasswordHasher`` fake: ``fake$<sha256 prefix>`` (T-Q291).

    The digest keeps the plaintext out of the stored value, so "plaintext never persisted"
    assertions stay meaningful.
    """

    PREFIX: Final = "fake$"

    def __init__(self) -> None:
        self.dummy_verifies: list[str] = []

    def hash(self, password: str) -> str:
        if not password:
            raise ValueError("password must not be empty")
        return self._digest(password)

    @classmethod
    def _digest(cls, password: str) -> str:
        return cls.PREFIX + hashlib.sha256(password.encode()).hexdigest()[:24]

    def verify(self, password: str, hashed: str | None) -> bool:
        return bool(password) and hashed == self._digest(password)

    def needs_rehash(self, hashed: str | None) -> bool:
        return bool(hashed) and not str(hashed).startswith(self.PREFIX)

    def verify_dummy(self, password: str) -> None:
        self.dummy_verifies.append(password)


FAKE_HASHER: Final = FakePasswordHasher()
