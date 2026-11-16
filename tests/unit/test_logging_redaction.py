"""T-D59 — structlog redaction processor and uvicorn query stripping."""

from __future__ import annotations

import logging

import pytest

from budget_planner.logging import REDACTED, _StripQueryFilter, redact_sensitive


def test_denied_keys_are_redacted_case_insensitively() -> None:
    event = {"event": "x", "Description": "rent", "NAME": "Bob", "q": "ZZ", "request_id": "r1"}
    out = redact_sensitive(None, "info", event)
    assert out["Description"] == REDACTED
    assert out["NAME"] == REDACTED
    assert out["q"] == REDACTED
    assert out["request_id"] == "r1"
    assert out["event"] == "x"


@pytest.mark.parametrize(
    "key",
    [
        "amount",
        "amount_minor",
        "note",
        "notes",
        "password_hash",
        "token",
        "secret_key",
        "rule_json",
    ],
)
def test_prefix_and_suffix_keys_are_redacted(key: str) -> None:
    assert redact_sensitive(None, "info", {key: "v"})[key] == REDACTED


def test_recurses_into_dicts_and_lists_without_mutating_input() -> None:
    event = {"ctx": {"memo": "m", "ok": 1}, "rows": [{"formula": "a+b"}, "plain"]}
    out = redact_sensitive(None, "info", event)
    assert out["ctx"] == {"memo": REDACTED, "ok": 1}
    assert out["rows"] == [{"formula": REDACTED}, "plain"]
    assert event["ctx"] == {"memo": "m", "ok": 1}


def test_uvicorn_access_filter_strips_query_string() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4", "GET", "/ledger?q=ZZ_SENTINEL_42", "1.1", 200),
        None,
    )
    assert _StripQueryFilter().filter(record)
    assert "ZZ_SENTINEL_42" not in record.getMessage()
    assert "/ledger HTTP" in record.getMessage()
