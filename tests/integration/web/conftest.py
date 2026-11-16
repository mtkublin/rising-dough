"""Shared fixtures for web integration tests (TestClient on a temp DB).

T-D08: ``CSRFMiddleware`` enforces a double-submit token on every
POST/PUT/PATCH/DELETE. To keep the suite from having to prime the cookie
in each test, the ``client`` fixture wraps :class:`TestClient` in a thin
subclass that:

1. Performs a priming GET on first construction so the server mints a
   ``__Host-csrf`` cookie and TestClient stores it in its cookie jar.
2. Overrides ``request`` so every mutating call automatically attaches
   the current cookie value as the ``X-CSRF-Token`` header.

Tests that need to assert on CSRF behaviour directly (see
``test_csrf.py``) build their own ``TestClient`` instance to bypass the
auto-prime path.

T-D02b: ``AuthRequiredMiddleware`` gates every non-exempt route, so
``client`` is **authenticated** — user 1 gets an email + bcrypt (cost 4)
password and a real server-side session whose id is placed in the
client's cookie jar. ``anon_client`` is the same CSRF-aware client with
no session, for auth tests. bcrypt is pinned to cost 4 for the whole web
suite (``_fast_bcrypt``).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.services import _passwords
from budget_planner.web.app import create_app
from budget_planner.web.middleware.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from tests.auth_support import FAST_ROUNDS, login_cookie

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class _CSRFAwareTestClient(TestClient):
    """TestClient that auto-primes + auto-attaches the CSRF token.

    The CSRF cookie is minted with ``Secure`` under ``env=test`` to mirror
    production. httpx's cookie jar refuses to send ``Secure`` cookies over
    plain HTTP, so we pin ``base_url`` to ``https://testserver`` — the
    ASGI protocol field is driven by that URL and Starlette treats the
    connection as TLS-terminated.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("base_url", "https://testserver")
        super().__init__(*args, **kwargs)
        # Priming GET — any safe route works; ``/healthz`` is cheap and
        # always registered. The response-cookie goes into the client's
        # jar via httpx's standard behaviour.
        self.get("/healthz")

    def request(self, method: str, url: Any, *args: Any, **kwargs: Any) -> Any:
        if method.upper() in _UNSAFE_METHODS:
            token = self.cookies.get(CSRF_COOKIE_NAME)
            if token:
                headers = dict(kwargs.get("headers") or {})
                headers.setdefault(CSRF_HEADER_NAME, token)
                kwargs["headers"] = headers
        return super().request(method, url, *args, **kwargs)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    db_url = f"sqlite:///{(tmp_path / 'web.sqlite').as_posix()}"
    return Settings(_env_file=None, database_url=db_url)


@pytest.fixture
def _migrated(settings: Settings) -> Iterator[Settings]:
    conn = get_connection(settings)
    try:
        apply_migrations(conn)
    finally:
        conn.close()
    yield settings


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep bcrypt cheap in web tests; production cost stays 12."""
    monkeypatch.setattr(_passwords, "DEFAULT_ROUNDS", FAST_ROUNDS)


@pytest.fixture
def session_cookie(_migrated: Settings) -> tuple[str, str]:
    """Seed user 1 with a password + live session; return ``(name, value)``."""
    return login_cookie(_migrated)


@pytest.fixture
def anon_client(_migrated: Settings) -> Iterator[TestClient]:
    """CSRF-aware client with **no** session cookie."""
    app = create_app(settings=_migrated)
    with _CSRFAwareTestClient(app) as c:
        yield c


@pytest.fixture
def client(_migrated: Settings, session_cookie: tuple[str, str]) -> Iterator[TestClient]:
    """CSRF-aware client signed in as user 1 (T-D02b)."""
    app = create_app(settings=_migrated)
    with _CSRFAwareTestClient(app) as c:
        name, value = session_cookie
        c.cookies.set(name, value)
        yield c


@pytest.fixture
def admin_client(_migrated: Settings, session_cookie: tuple[str, str]) -> Iterator[TestClient]:
    """CSRF-aware client signed in as user 1 promoted to admin (T-D17)."""
    conn = get_connection(_migrated)
    try:
        conn.execute("UPDATE users SET is_admin = 1 WHERE id = 1")
        conn.commit()
    finally:
        conn.close()
    app = create_app(settings=_migrated)
    with _CSRFAwareTestClient(app) as c:
        name, value = session_cookie
        c.cookies.set(name, value)
        yield c
