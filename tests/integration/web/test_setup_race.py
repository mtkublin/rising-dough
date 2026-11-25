"""UR21b - first-run setup completes exactly once (ADR-0134 section 9, ADR-0137).

Two simultaneous completions with the valid token (service level, separate
connections to one file DB) and a replayed POST /setup (HTTP level).
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.services.setup import SetupClosedError, SetupDraft, complete_setup, hash_token
from tests.auth_support import FAKE_HASHER, TEST_PASSWORD
from tests.db_template import sqlite_url

pytestmark = pytest.mark.integration

TOKEN = "-".join(("tok", "race", "setup", "value"))
USERS_WITH_EMAIL = "SELECT COUNT(*) FROM users WHERE email IS NOT NULL"
MARKERS = "SELECT COUNT(*) FROM setup_token_consumed"
AUDIT_MARKER = "SELECT COUNT(*) FROM audit_log WHERE entity_type = 'setup_token'"
LOGIN = "/auth/login"
THREADS = 2


@pytest.fixture
def settings(migrated_db: Path) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        cookie_secret="x" * 32,
        webauthn_rp_id="budget.example.test",
        webauthn_origin="https://budget.example.test",
        database_url=sqlite_url(migrated_db),
        planner_setup_token_hash=hash_token(TOKEN),
    )


def _count(conn: sqlite3.Connection, sql: str) -> int:
    return int(conn.execute(sql).fetchone()[0])


def test_two_simultaneous_completions_create_exactly_one_admin(
    settings: Settings, conn: sqlite3.Connection
) -> None:
    barrier = threading.Barrier(THREADS)
    outcomes: dict[int, str] = {}
    errors: list[BaseException] = []

    def attempt(n: int) -> None:
        c = get_connection(settings)
        try:
            draft = SetupDraft(
                email=f"admin{n}@example.test",
                name=f"Admin {n}",
                password=TEST_PASSWORD,
                password_confirm=TEST_PASSWORD,
            )
            barrier.wait(timeout=10)
            try:
                complete_setup(c, settings, token=TOKEN, draft=draft, hasher=FAKE_HASHER)
                outcomes[n] = "created"
            except SetupClosedError:
                outcomes[n] = "closed"
        except BaseException as exc:  # surfaced to the main thread below
            errors.append(exc)
        finally:
            c.close()

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == []
    assert sorted(outcomes.values()) == ["closed", "created"]
    winner = next(n for n, o in outcomes.items() if o == "created")
    rows = conn.execute("SELECT email, is_admin FROM users WHERE email IS NOT NULL").fetchall()
    assert [(r["email"], r["is_admin"]) for r in rows] == [(f"admin{winner}@example.test", 1)]
    assert _count(conn, MARKERS) == 1
    assert _count(conn, AUDIT_MARKER) == 1


def test_replayed_post_with_the_same_token_and_form_is_closed(
    anon_client: TestClient, conn: sqlite3.Connection
) -> None:
    form = {
        "token": TOKEN,
        "name": "First Admin",
        "email": "first@example.test",
        "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD,
    }
    first = anon_client.post("/setup", data=form, follow_redirects=False)
    assert (first.status_code, first.headers["location"]) == (303, "/today")
    second = anon_client.post("/setup", data=form, follow_redirects=False)
    assert (second.status_code, second.headers["location"]) == (303, LOGIN)
    assert _count(conn, USERS_WITH_EMAIL) == 1
    assert _count(conn, MARKERS) == 1
    assert _count(conn, AUDIT_MARKER) == 1
