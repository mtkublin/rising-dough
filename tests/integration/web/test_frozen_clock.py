"""T-Q311: the suite-wide frozen clock reaches code run by Starlette's ``TestClient``.

``TestClient`` runs the ASGI app in an anyio portal thread; the app's sync endpoints
then run in a worker thread. The ``ContextVar`` override of ``budget_planner.clock``
must reach both, otherwise a route would read the real clock inside a test.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from budget_planner import clock
from tests.conftest import suite_now


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/sync")
    def sync_route() -> dict[str, str]:
        return {"now": clock.utc_now_iso()}

    @app.get("/async")
    async def async_route() -> dict[str, str]:
        return {"now": clock.utc_now_iso()}

    return app


@pytest.mark.parametrize("path", ["/sync", "/async"])
def test_route_sees_the_suite_frozen_instant(path: str) -> None:
    with TestClient(_app()) as client:
        body = client.get(path).json()

    assert body == {"now": clock.iso_utc(suite_now())}


def test_route_follows_a_nested_freeze() -> None:
    pinned = datetime(2030, 2, 28, 23, 59, tzinfo=UTC)
    with clock.frozen(pinned), TestClient(_app()) as client:
        body = client.get("/sync").json()

    assert body == {"now": "2030-02-28T23:59:00.000Z"}


def test_default_instant_is_the_documented_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUDGET_TEST_NOW", raising=False)

    assert suite_now() == datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


@pytest.mark.real_clock
def test_real_clock_marker_opts_out_of_the_freeze() -> None:
    assert clock.utc_now() != suite_now()
