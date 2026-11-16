"""T-D06 — structured JSON logging bound to request_id.

Uses structlog's ``LogCapture`` processor to run assertions against the
in-memory event dictionaries without touching stdout. The real pipeline
is wired by :func:`budget_planner.logging.configure`; the capture
fixture here swaps the final renderer so we can see the event dict
before it is serialised.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import structlog
from structlog.testing import LogCapture

from budget_planner.logging import bind_request_id, clear_request_id, get_logger


@pytest.fixture
def log_output() -> Iterator[LogCapture]:
    cap = LogCapture()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            cap,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )
    try:
        yield cap
    finally:
        # Make sure nothing leaks across tests.
        clear_request_id()
        structlog.reset_defaults()


def test_event_has_iso_timestamp_and_level(log_output: LogCapture) -> None:
    log = get_logger("test")
    log.info("hello")
    assert len(log_output.entries) == 1
    event = log_output.entries[0]
    assert event["event"] == "hello"
    assert event["log_level"] == "info"
    # ISO-8601 timestamp — crude shape check (YYYY-MM-DDTHH:MM:SS).
    ts = event["timestamp"]
    assert ts[4] == "-" and ts[7] == "-" and ts[10] == "T"


def test_request_id_binds_to_log_event(log_output: LogCapture) -> None:
    bind_request_id("abc123def456")
    try:
        get_logger("test").info("inside request")
    finally:
        clear_request_id()
    get_logger("test").info("after request")

    inside, after = log_output.entries
    assert inside["request_id"] == "abc123def456"
    assert "request_id" not in after


def test_contextvar_cleared_between_requests(log_output: LogCapture) -> None:
    """Simulate two back-to-back requests: the second must not inherit
    the first's id."""
    for rid in ("req-1-aaa", "req-2-bbb"):
        bind_request_id(rid)
        try:
            get_logger("test").info("work")
        finally:
            clear_request_id()

    entries = log_output.entries
    assert len(entries) == 2
    assert entries[0]["request_id"] == "req-1-aaa"
    assert entries[1]["request_id"] == "req-2-bbb"
