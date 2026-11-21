"""Pure helpers for proxy-set client identity and bounded attacker text (T-Q203, ADR-0133)."""

from __future__ import annotations

import pytest

from budget_planner.domain.client_ip import bound_text
from budget_planner.web.deps import parse_client_ip

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("203.0.113.9", "203.0.113.9"),
        (" 203.0.113.9 ", "203.0.113.9"),
        ("2001:DB8::1", "2001:db8::1"),
        ("100.64.1.2", "100.64.1.2"),
    ],
)
def test_parse_client_ip_returns_canonical_address(raw: str, expected: str) -> None:
    assert parse_client_ip(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [None, "", "testclient", "not-an-ip", "<img src=x onerror=alert(1)>\"'&", "1.2.3.4, 5.6.7.8"],
)
def test_parse_client_ip_rejects_non_addresses(raw: str | None) -> None:
    assert parse_client_ip(raw) is None


def test_bound_text_truncates_to_limit() -> None:
    assert bound_text("a" * 1000, 254) == "a" * 254


def test_bound_text_keeps_short_text_and_none() -> None:
    assert bound_text("short", 254) == "short"
    assert bound_text(None, 254) is None
