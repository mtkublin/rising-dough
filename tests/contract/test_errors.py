"""Error-shape contracts shared by every route (T-UT04a, ADR-0106 section 1).

HTTP-level errors (404, 405, 422, 403 CSRF) answer with a JSON ``detail``
body whatever the caller is (browser, HTMX or JSON); anonymous callers hit
the auth gate first. Domain-error pages and flash fragments are exercised in
``tests/integration/web/test_errors.py`` through the UI map.
"""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from tests.contract._audit import audit_count
from tests.contract.conftest import covers

pytest_plugins = ["tests.contract._support"]

HX = {"HX-Request": "true"}
JSON = {"Accept": "application/json"}
ANY_CALLER: tuple[dict[str, str], ...] = ({}, HX, JSON)


@covers("POST /auth/sessions/{handle}/revoke")
def test_unknown_session_handle_is_404_for_every_caller_shape(
    client: TestClient, db: sqlite3.Connection
) -> None:
    before = audit_count(db, "session", "delete")
    for headers in ANY_CALLER:
        r = client.post("/auth/sessions/" + "0" * 16 + "/revoke", headers=headers)
        assert (r.status_code, r.json()) == (404, {"detail": "not_found"})
        assert r.headers["x-request-id"]
    malformed = client.post("/auth/sessions/zzz/revoke")
    assert (malformed.status_code, malformed.json()) == (404, {"detail": "not_found"})
    assert audit_count(db, "session", "delete") == before


@covers("POST /auth/passkeys/{credential_id}/revoke")
def test_malformed_path_parameter_is_422_with_field_location(client: TestClient) -> None:
    for headers in ANY_CALLER:
        r = client.post("/auth/passkeys/abc/revoke", headers=headers)
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert detail[0]["loc"] == ["path", "credential_id"]


@covers("POST /auth/passkeys/{credential_id}/revoke")
def test_unknown_credential_is_404_not_found(client: TestClient) -> None:
    r = client.post("/auth/passkeys/424242/revoke")
    assert (r.status_code, r.json()) == (404, {"detail": "not_found"})


@covers("GET /auth/login")
def test_unknown_route_is_404_json_for_signed_in_users(client: TestClient) -> None:
    for headers in ANY_CALLER:
        r = client.get("/definitely-not-a-route", headers=headers)
        assert (r.status_code, r.json()) == (404, {"detail": "Not Found"})
        assert r.headers["x-request-id"]


@covers("GET /auth/login")
def test_unknown_route_hits_the_auth_gate_first_for_anonymous_callers(
    anon_client: TestClient,
) -> None:
    r = anon_client.get("/definitely-not-a-route", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login?next=")


@covers("GET /health")
def test_wrong_method_is_405_json(client: TestClient) -> None:
    r = client.post("/health")
    assert (r.status_code, r.json()) == (405, {"detail": "Method Not Allowed"})


@covers("POST /auth/logout")
def test_csrf_rejection_is_403_with_no_state_change(
    client: TestClient, session_cookie: tuple[str, str], db: sqlite3.Connection
) -> None:
    for headers in ({}, HX, JSON):
        r = client.post("/auth/logout", headers={**headers, "X-CSRF-Token": "forged"})
        assert r.status_code == 403
        assert r.headers["x-request-id"]
    assert audit_count(db, "session", "delete") == 0
