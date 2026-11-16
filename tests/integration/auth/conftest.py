"""Fixtures for auth backend integration tests (T-D02a)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

import pytest

from budget_planner.services import _passwords

PASSWORD = "s3cret-passw0rd"  # noqa: S105  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep bcrypt cheap in tests; production cost stays 12."""
    monkeypatch.setattr(_passwords, "DEFAULT_ROUNDS", 4)


@pytest.fixture
def make_user(conn: sqlite3.Connection) -> Callable[..., int]:
    def _make(
        *,
        email: str = "alice@example.test",
        name: str = "Alice",
        password: str | None = PASSWORD,
        deleted: bool = False,
    ) -> int:
        password_hash = None if password is None else _passwords.hash_password(password)
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash, deleted_at) VALUES (?, ?, ?, ?)",
            (name, email, password_hash, "2026-01-01T00:00:00.000Z" if deleted else None),
        )
        return int(cur.lastrowid or 0)

    return _make


@pytest.fixture
def audit_rows(conn: sqlite3.Connection) -> Callable[[str], list[sqlite3.Row]]:
    def _rows(entity_type: str) -> list[sqlite3.Row]:
        return list(
            conn.execute(
                "SELECT * FROM audit_log WHERE entity_type = ? ORDER BY id", (entity_type,)
            )
        )

    return _rows
