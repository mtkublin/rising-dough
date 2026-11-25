"""T-D59 — a ledger search term must never appear in any log line."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest
import structlog
from fastapi.testclient import TestClient

from budget_planner.logging import get_logger, redact_sensitive, strip_access_query

SENTINEL = "ZZ_SENTINEL_42"


@pytest.fixture
def log_stream() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    # The TestClient's own httpx request log is a client-side artifact, not app output.
    handler.addFilter(lambda r: not r.name.startswith(("httpx", "httpcore")))
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=[strip_access_query, redact_sensitive],
            processor=structlog.processors.JSONRenderer(),
        )
    )
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield stream
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


def test_setup_token_absent_from_access_log(log_stream: io.StringIO) -> None:
    """Q28 (ADR-0134 §9): the `/setup` path is logged, its query string never is."""
    sentinel = "SECRET123"
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d', "127.0.0.1", "GET", f"/setup?token={sentinel}", "1.1", 404
    )
    out = log_stream.getvalue()
    assert "/setup" in out
    assert sentinel not in out
    assert "token=" not in out
    assert json.loads(out)["event"] == '127.0.0.1 - "GET /setup HTTP/1.1" 404'


def test_invite_token_absent_from_access_log(log_stream: io.StringIO) -> None:
    """T-UR20a: the invite token (a path segment) never reaches the access log, GET or POST."""
    sentinel = "INVITETOKEN123"
    for method in ("GET", "POST"):
        logging.getLogger("uvicorn.access").info(
            '%s - "%s %s HTTP/%s" %d', "127.0.0.1", method, f"/invite/{sentinel}", "1.1", 200
        )
    lines = log_stream.getvalue().splitlines()
    assert sentinel not in log_stream.getvalue()
    assert [json.loads(line)["event"] for line in lines] == [
        '127.0.0.1 - "GET /invite/[redacted] HTTP/1.1" 200',
        '127.0.0.1 - "POST /invite/[redacted] HTTP/1.1" 200',
    ]


def test_ledger_search_sentinel_absent_from_logs(
    client: TestClient, log_stream: io.StringIO, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        resp = client.get("/ledger", params={"q": SENTINEL})
        get_logger("test").info("search", q=SENTINEL, filters={"description": SENTINEL})
        logging.getLogger("uvicorn.access").info(
            '%s - "%s %s HTTP/%s" %d',
            "127.0.0.1",
            "GET",
            f"/ledger?q={SENTINEL}",
            "1.1",
            200,
        )

    assert resp.status_code == 200
    assert "search" in log_stream.getvalue()
    assert SENTINEL not in log_stream.getvalue()
    app_lines = [
        r.getMessage()
        for r in caplog.records
        if r.name != "uvicorn.access" and not r.name.startswith("httpx")
    ]
    assert not any(SENTINEL in line for line in app_lines)
