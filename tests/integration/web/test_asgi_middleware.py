"""T-Q274 (ADR-0144) — behaviour of the pure-ASGI middleware functions."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

import pytest
from fastapi import Form, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.testclient import TestClient
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from budget_planner.config import Settings
from budget_planner.web.app import create_app
from budget_planner.web.middleware.admin import admin_required_middleware
from budget_planner.web.middleware.auth import auth_required_middleware
from budget_planner.web.middleware.cache_control import cache_control_middleware
from budget_planner.web.middleware.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_FORM_FIELD,
    csrf_middleware,
)
from budget_planner.web.middleware.must_change_password import must_change_password_middleware
from budget_planner.web.middleware.request_id import request_id_middleware

pytestmark = pytest.mark.integration

_FACTORIES: list[Callable[[ASGIApp], ASGIApp]] = [
    admin_required_middleware,
    auth_required_middleware,
    cache_control_middleware,
    csrf_middleware,
    must_change_password_middleware,
    request_id_middleware,
]


@pytest.mark.parametrize("factory", _FACTORIES)
def test_non_http_scopes_pass_through_untouched(factory: Callable[[ASGIApp], ASGIApp]) -> None:
    seen: list[Scope] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope)

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(_message: Message) -> None:
        return None

    scope: Scope = {"type": "lifespan"}

    async def _drive() -> None:
        await factory(inner)(scope, receive, send)

    # A worker thread has no running loop even if an earlier e2e test left one here.
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(lambda: asyncio.run(_drive())).result()
    assert seen == [{"type": "lifespan"}]


@pytest.fixture
def raw_client(_migrated: Settings, session_cookie: tuple[str, str]) -> TestClient:
    app = create_app(settings=_migrated)

    @app.get("/_t274/rid")
    def _rid(request: Request) -> JSONResponse:
        return JSONResponse({"rid": request.state.request_id, "token": request.state.csrf_token})

    @app.post("/_t274/form")
    def _form(note: Annotated[str, Form()]) -> PlainTextResponse:
        return PlainTextResponse(note)

    client = TestClient(app, base_url="https://testserver")
    client.cookies.set(*session_cookie)
    return client


def test_request_id_generated_and_visible_to_handler(raw_client: TestClient) -> None:
    r = raw_client.get("/_t274/rid")
    rid = r.json()["rid"]
    assert len(rid) == 12
    assert r.headers["x-request-id"] == rid


def test_request_id_supplied_by_client_is_echoed(raw_client: TestClient) -> None:
    r = raw_client.get("/_t274/rid", headers={"X-Request-Id": "trace-abc"})
    assert r.json()["rid"] == "trace-abc"
    assert r.headers["x-request-id"] == "trace-abc"


def test_csrf_token_state_matches_cookie_and_form_body_reaches_handler(
    raw_client: TestClient,
) -> None:
    token = raw_client.get("/_t274/rid").json()["token"]
    assert raw_client.cookies[CSRF_COOKIE_NAME] == token
    r = raw_client.post("/_t274/form", data={CSRF_FORM_FIELD: token, "note": "kept"})
    assert (r.status_code, r.text) == (200, "kept")


def test_form_post_with_wrong_token_is_403_and_never_reaches_handler(
    raw_client: TestClient,
) -> None:
    raw_client.get("/_t274/rid")
    r = raw_client.post("/_t274/form", data={CSRF_FORM_FIELD: "nope", "note": "x"})
    assert (r.status_code, r.json()) == (403, {"detail": "invalid_csrf"})


def test_malformed_multipart_is_400(raw_client: TestClient) -> None:
    raw_client.get("/_t274/rid")
    r = raw_client.post(
        "/_t274/form",
        content=b"--b\r\ngarbage",
        headers={"content-type": "multipart/form-data"},
    )
    assert (r.status_code, r.json()) == (400, {"detail": "malformed_form"})


def test_csrf_cookie_not_reissued_when_present(raw_client: TestClient) -> None:
    raw_client.get("/_t274/rid")
    r = raw_client.get("/_t274/rid")
    assert CSRF_COOKIE_NAME not in r.headers.get("set-cookie", "")


def test_non_admin_gets_404_on_admin_subtree_before_csrf(raw_client: TestClient) -> None:
    r = raw_client.post("/settings/users/anything")
    assert r.status_code == 404


def test_anonymous_htmx_request_gets_401_with_request_id(_migrated: Settings) -> None:
    app = create_app(settings=_migrated)
    with TestClient(app, base_url="https://testserver") as c:
        r = c.get(
            "/ledger",
            headers={"HX-Request": "true", "HX-Current-URL": "https://testserver/ledger"},
        )
    assert r.status_code == 401
    assert r.headers["hx-redirect"] == "/auth/login?next=%2Fledger"
    assert r.headers["x-request-id"]


def test_authenticated_get_slides_session_cookie(
    _migrated: Settings, session_cookie: tuple[str, str]
) -> None:
    name, value = session_cookie
    app = create_app(settings=_migrated)
    with TestClient(app, base_url="https://testserver") as c:
        c.cookies.set(name, value)
        r = c.get("/today", follow_redirects=False)
    cookies = [v for k, v in r.headers.multi_items() if k.lower() == "set-cookie"]
    assert any(v.startswith(f"{name}=") and "HttpOnly" in v for v in cookies)
