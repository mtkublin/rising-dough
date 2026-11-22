"""Shell route contracts: health probes, root, add overlay, dev components, debug (T-UT04a).

Also pins the cross-cutting shell behaviour every page shares: security
headers, cache-control, CSRF cookie and the anonymous redirect shapes
(ADR-0106 section 1, ADR-0070 section 4). Markup is not asserted here.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.services.audit_tail import REDACTED
from budget_planner.web.app import create_app
from budget_planner.web.deps import get_settings_dep
from tests.contract._audit import audit_count
from tests.contract.conftest import covers
from tests.ui_map import _html, errors

pytest_plugins = ["tests.contract._support"]

HX = {"HX-Request": "true", "HX-Current-URL": "https://testserver/ledger?view=planned"}
JSON = {"Accept": "application/json"}
SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def _location(resp: Any) -> str:
    return str(resp.headers["location"])


# ---------------------------------------------------------------------------
# GET /health, GET /ready, GET /health/replication
# ---------------------------------------------------------------------------


@covers("GET /health")
def test_health_is_public_cheap_and_head_capable(
    anon_client: TestClient, db: sqlite3.Connection
) -> None:
    before = audit_count(db, "auth_event")
    r = anon_client.get("/health", follow_redirects=False)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["status"] == "ok"
    assert r.json()["version"]
    assert anon_client.head("/health").status_code == 200
    assert audit_count(db, "auth_event") == before


@covers("GET /ready")
def test_ready_reports_db_integrity_publicly(anon_client: TestClient) -> None:
    r = anon_client.get("/ready", follow_redirects=False)
    assert (r.status_code, r.json()) == (200, {"status": "ready", "db": "ok"})
    assert anon_client.head("/ready").status_code == 200


@covers("GET /ready")
def test_ready_is_503_when_the_database_is_unusable() -> None:
    cfg = Settings(_env_file=None, database_url="sqlite:////dev/null")
    r = TestClient(create_app(settings=cfg)).get("/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "not_ready"
    assert r.json()["detail"]


def _replication_client(tmp_path: Path, settings: Settings, status_file: str) -> TestClient:
    cfg = Settings(
        _env_file=None, database_url=settings.database_url, replication_status_file=status_file
    )
    return TestClient(create_app(settings=cfg))


def _status_file(path: Path, *, newest_age: timedelta, error: str | None = None) -> str:
    now = datetime.now(UTC)
    path.write_text(
        json.dumps(
            {
                "checked_at": now.isoformat(),
                "newest_object_at": (now - newest_age).isoformat(),
                "generation": "abc123",
                "error": error,
            }
        ),
        encoding="utf-8",
    )
    return str(path)


@covers("GET /health/replication")
def test_replication_health_status_codes(tmp_path: Path, _migrated: Settings) -> None:
    def probe(status_file: str) -> tuple[int, str]:
        r = _replication_client(tmp_path, _migrated, status_file).get("/health/replication")
        return r.status_code, r.json()["status"]

    fresh = _status_file(tmp_path / "fresh.json", newest_age=timedelta(hours=1))
    stale = _status_file(tmp_path / "stale.json", newest_age=timedelta(hours=30))
    errored = _status_file(
        tmp_path / "err.json", newest_age=timedelta(minutes=1), error="generations_failed"
    )
    assert probe("") == (200, "disabled")
    assert probe(fresh) == (200, "ok")
    assert probe(stale) == (503, "stale")
    assert probe(errored) == (503, "probe_error")
    assert probe(str(tmp_path / "missing.json")) == (503, "missing")
    assert probe(str(tmp_path)) == (503, "unreadable")


@covers("GET /health/replication")
def test_replication_health_is_public_and_head_capable(anon_client: TestClient) -> None:
    r = anon_client.get("/health/replication", follow_redirects=False)
    assert r.status_code == 200
    assert anon_client.head("/health/replication").status_code == 200


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------


@covers("GET /")
def test_root_redirects_to_today_for_get_and_head(client: TestClient) -> None:
    for method in (client.get, client.head):
        r = method("/", follow_redirects=False)
        assert (r.status_code, _location(r)) == (303, "/today")
    assert client.get("/").status_code == 200  # followed redirect lands on a page


@covers("GET /")
def test_root_requires_a_session_and_keeps_the_target(anon_client: TestClient) -> None:
    r = anon_client.get("/", follow_redirects=False)
    assert (r.status_code, _location(r)) == (
        302,
        "/auth/login?next=%2Ftoday",
    )  # safe_next("/") -> landing page
    hx = anon_client.get("/", headers=HX, follow_redirects=False)
    assert hx.status_code == 401
    assert hx.headers["hx-redirect"] == "/auth/login?next=%2Fledger%3Fview%3Dplanned"
    as_json = anon_client.get("/", headers=JSON, follow_redirects=False)
    assert (as_json.status_code, as_json.json()) == (401, {"error": "unauthorized"})


# ---------------------------------------------------------------------------
# GET /add
# ---------------------------------------------------------------------------


@covers("GET /add")
@pytest.mark.parametrize("when", ["happened", "planned", "repeats", ""])
def test_add_overlay_renders_for_each_tab_without_writing(
    client: TestClient, db: sqlite3.Connection, when: str
) -> None:
    before = db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    r = client.get(f"/add?when={when}", headers=HX)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == before


@covers("GET /add")
def test_add_overlay_unknown_tab_is_422_naming_the_param(client: TestClient) -> None:
    r = client.get("/add?when=unknown-tab", headers=HX)
    assert r.status_code == 422
    assert "when" in _html.text_of(r.text, errors.alert)


@covers("GET /add")
def test_add_overlay_requires_a_session(anon_client: TestClient) -> None:
    r = anon_client.get("/add", follow_redirects=False)
    assert (r.status_code, _location(r)) == (302, "/auth/login?next=%2Fadd")
    hx = anon_client.get("/add", headers=HX, follow_redirects=False)
    assert hx.status_code == 401
    assert hx.headers["hx-redirect"].startswith("/auth/login?next=")


# ---------------------------------------------------------------------------
# GET /dev/components
# ---------------------------------------------------------------------------


@covers("GET /dev/components")
def test_dev_components_is_served_outside_production(client: TestClient) -> None:
    r = client.get("/dev/components")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")


@covers("GET /dev/components")
def test_dev_components_is_404_in_production(client: TestClient, settings: Settings) -> None:
    prod = settings.model_copy(update={"env": "production"})
    client.app.dependency_overrides[get_settings_dep] = lambda: prod  # type: ignore[attr-defined]
    try:
        assert client.get("/dev/components").status_code == 404
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


@covers("GET /dev/components")
def test_dev_components_requires_a_session(anon_client: TestClient) -> None:
    r = anon_client.get("/dev/components", follow_redirects=False)
    assert (r.status_code, _location(r)) == (302, "/auth/login?next=%2Fdev%2Fcomponents")


# ---------------------------------------------------------------------------
# GET /debug/audit-tail
# ---------------------------------------------------------------------------


@covers("GET /debug/audit-tail")
def test_audit_tail_is_admin_only_json_no_store(
    admin_client: TestClient, anon_client: TestClient
) -> None:
    ok = admin_client.get("/debug/audit-tail?n=5")
    assert ok.status_code == 200
    assert ok.headers["cache-control"] == "no-store"
    body = ok.json()
    assert body["count"] == len(body["entries"]) <= 5
    anon = anon_client.get("/debug/audit-tail", follow_redirects=False)
    assert (anon.status_code, _location(anon)) == (302, "/auth/login?next=%2Fdebug%2Faudit-tail")


@covers("GET /debug/audit-tail")
def test_audit_tail_is_404_not_403_for_non_admins(client: TestClient) -> None:
    assert client.get("/debug/audit-tail").status_code == 404


@covers("GET /debug/audit-tail")
def test_audit_tail_caps_n_and_redacts_secrets(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    payload = json.dumps(
        {"email": "a@b.c", "password_hash": "$2b$topsecret"}
    )  # pragma: allowlist secret
    db.execute(
        "INSERT INTO audit_log (entity_type, entity_id, changed_at, operation, new_json, user_id)"
        " VALUES ('thing', 1, '2026-11-03T10:00:00Z', 'create', ?, 1)",
        (payload,),
    )
    db.commit()
    newest = admin_client.get("/debug/audit-tail?n=1").json()["entries"][0]
    assert newest["new"]["password_hash"] == REDACTED
    assert "topsecret" not in json.dumps(newest)
    assert admin_client.get("/debug/audit-tail?n=100000").json()["count"] <= 100
    assert admin_client.get("/debug/audit-tail?n=abc").status_code == 422


# ---------------------------------------------------------------------------
# Cross-cutting shell contract (security headers, cache-control, CSRF cookie)
# ---------------------------------------------------------------------------


@covers("GET /health", "GET /auth/login")
def test_public_routes_carry_security_headers_and_request_id(anon_client: TestClient) -> None:
    for path in ("/health", "/auth/login"):
        r = anon_client.get(path, follow_redirects=False)
        for name, value in SECURITY_HEADERS.items():
            assert r.headers.get(name) == value, (path, name)
        assert r.headers["x-request-id"]
    # The incoming request id is honoured.
    traced = anon_client.get("/health", headers={"X-Request-Id": "trace-1234"})
    assert traced.headers["x-request-id"] == "trace-1234"


@covers("GET /", "GET /add")
def test_authenticated_pages_are_no_store_and_set_the_csrf_cookie(client: TestClient) -> None:
    for path, headers in (("/add", HX), ("/dev/components", {})):
        r = client.get(path, headers=headers)
        assert r.headers["cache-control"] == "no-store", path
    assert client.cookies.get("__Host-csrf")
