"""T-Q203 / Q-027: proxy-set client identity, bounded audit text, no cross-IP lockout.

ADR-0133 (amends ADR-0072 §4). Mirrors repro/H3/h3_rate_limit.py (R3-R5, R8)
and repro/H2/h2_07_login_lockout_and_audit_tail.py.
"""

from __future__ import annotations

import importlib
import json
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.web.app import create_app
from tests.auth_support import TEST_EMAIL, TEST_PASSWORD, seed_login_user
from tests.integration.web.conftest import _CSRFAwareTestClient

pytestmark = pytest.mark.integration

LIMIT_PER_MINUTE = 2
ROOT = Path(__file__).resolve().parents[3]
PROD_COMPOSE = ROOT / "terraform/cloud-init/compose/docker-compose.yml.tpl"
# uvicorn's own middleware (what the Dockerfile CMD runs); imported dynamically because
# the mypy hook environment has no uvicorn.
ProxyHeadersMiddleware: Any = importlib.import_module(
    "uvicorn.middleware.proxy_headers"
).ProxyHeadersMiddleware
EMAIL_MAX = 254
USER_AGENT_MAX = 256
AUDIT_JSON_MAX = 600


def _pinned_proxy() -> str:
    match = re.search(r'FORWARDED_ALLOW_IPS:\s*"([^"]+)"', PROD_COMPOSE.read_text())
    assert match is not None, "compose template must pin FORWARDED_ALLOW_IPS"
    return match.group(1)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'web.sqlite').as_posix()}",
        rate_limit_login_per_minute=LIMIT_PER_MINUTE,
        rate_limit_login_per_hour=50,
        rate_limit_login_ip_per_hour=500,
    )


@pytest.fixture
def seeded(conn: sqlite3.Connection) -> int:
    return seed_login_user(conn)


def _client(app: Any, peer: str) -> Iterator[TestClient]:
    with _CSRFAwareTestClient(app, client=(peer, 50000)) as c:
        yield c


def _login(client: TestClient, email: str, password: str, **kw: Any) -> Any:
    return client.post(
        "/auth/login",
        data={"email": email, "password": password, "next": "/"},
        follow_redirects=False,
        **kw,
    )


def _login_keys(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT key FROM auth_rate_limit WHERE key LIKE 'login:60s:%'").fetchall()
    return sorted(r[0] for r in rows)


def test_spoofed_forwarded_for_from_untrusted_peer_does_not_change_bucket(
    _migrated: Settings, conn: sqlite3.Connection, seeded: int
) -> None:
    app = ProxyHeadersMiddleware(create_app(settings=_migrated), trusted_hosts=_pinned_proxy())
    with _CSRFAwareTestClient(
        app, client=("203.0.113.9", 50000), base_url="https://testserver"
    ) as c:
        codes = [
            _login(c, TEST_EMAIL, "wrong", headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code
            for i in range(LIMIT_PER_MINUTE + 1)
        ]
    assert codes == [401, 401, 429]
    assert _login_keys(conn) == [f"login:60s:ip=203.0.113.9|email={TEST_EMAIL}"]


def test_trusted_proxy_supplies_the_client_address(
    _migrated: Settings, conn: sqlite3.Connection, seeded: int
) -> None:
    app = ProxyHeadersMiddleware(create_app(settings=_migrated), trusted_hosts=_pinned_proxy())
    with _CSRFAwareTestClient(app, client=(_pinned_proxy(), 50000)) as c:
        _login(c, TEST_EMAIL, "wrong", headers={"X-Forwarded-For": "198.51.100.7"})
    assert _login_keys(conn) == [f"login:60s:ip=198.51.100.7|email={TEST_EMAIL}"]
    ips = conn.execute("SELECT ip FROM audit_log WHERE entity_type = 'auth_event'").fetchall()
    assert ips and all(r[0] == "198.51.100.7" for r in ips)


def test_non_address_client_host_is_never_stored(
    _migrated: Settings, conn: sqlite3.Connection, seeded: int
) -> None:
    payload = "<img src=x onerror=alert(1)>"
    with _CSRFAwareTestClient(create_app(settings=_migrated), client=(payload, 1)) as c:
        _login(c, TEST_EMAIL, "wrong")
    assert _login_keys(conn) == [f"login:60s:ip=unknown|email={TEST_EMAIL}"]
    audit_ips = conn.execute("SELECT ip FROM audit_log WHERE entity_type = 'auth_event'").fetchall()
    assert audit_ips and all(r[0] is None for r in audit_ips)


def test_other_address_cannot_lock_out_the_owner(_migrated: Settings, seeded: int) -> None:
    app = create_app(settings=_migrated)
    with (
        _CSRFAwareTestClient(app, client=("203.0.113.10", 1)) as attacker,
        _CSRFAwareTestClient(app, client=("198.51.100.20", 1)) as owner,
    ):
        codes = [_login(attacker, TEST_EMAIL, "wrong").status_code for _ in range(5)]
        assert codes[-1] == 429
        assert _login(owner, TEST_EMAIL, TEST_PASSWORD).status_code == 303


def test_attacker_text_in_audit_rows_is_bounded(
    _migrated: Settings, conn: sqlite3.Connection, seeded: int
) -> None:
    huge_email = "x" * 200_000 + "@example.test"
    with _CSRFAwareTestClient(create_app(settings=_migrated), client=("203.0.113.9", 1)) as c:
        for _ in range(LIMIT_PER_MINUTE + 1):
            _login(c, huge_email, "wrong", headers={"User-Agent": "u" * 10_000})
    rows = conn.execute(
        "SELECT new_json, user_agent FROM audit_log WHERE entity_type = 'auth_event'"
    ).fetchall()
    assert len(rows) >= LIMIT_PER_MINUTE + 1
    for new_json, user_agent in rows:
        assert len(new_json) <= AUDIT_JSON_MAX
        assert len(user_agent) == USER_AGENT_MAX
        email = json.loads(new_json).get("email")
        assert email is None or len(email) <= EMAIL_MAX
    assert all(len(k) <= AUDIT_JSON_MAX for k in _login_keys(conn))
