"""T-Q233 (Q-023): malformed or out-of-range request input is a 4xx, never a 500.

The TestClient re-raises unhandled server errors, so reaching an assertion already means no crash.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from budget_planner.domain.money import MAX_MINOR, parse_amount_minor
from budget_planner.web.params import parse_int, parse_year_month
from tests.ui_map import _html

BAD_GETS = [
    "/budget?year=abc",
    "/budget?year=99999&month=1",
    "/budget?month=13",
    "/budget?month=0",
    "/budget?year=0",
    "/budget/yearly?year=abc",
    "/plan?year=99999",
    "/plan?year=abc",
    "/ledger?account_id=99999999999999999999999",
    "/ledger?date_from=2026-02-30",
    "/today/afford?amount=nan",
    "/today/afford?amount=inf",
    "/today/afford?amount=1e999",
    "/today/afford?amount=1e300",
]


@pytest.mark.parametrize("url", BAD_GETS)
def test_bad_query_is_422_with_message(client: TestClient, url: str) -> None:
    resp = client.get(url)
    assert resp.status_code == 422
    assert resp.text.strip()


@pytest.mark.parametrize(
    "url",
    [
        "/forecast?horizon_months=abc",
        "/forecast?horizon_months=100000",
        "/ledger?page_size=1000000",
        "/ledger?page=-1",
    ],
)
def test_out_of_range_but_well_formed_query_is_clamped(client: TestClient, url: str) -> None:
    assert client.get(url).status_code == 200


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "1e400", "1e30", "99999999999999999999"])
def test_reconcile_rejects_bad_amount(client: TestClient, raw: str) -> None:
    resp = client.post("/accounts/1/reconcile", data={"actual_balance": raw})
    assert resp.status_code in {404, 422}


@pytest.mark.parametrize("raw", ["NaN", "1e30", "99999999999999999999"])
def test_create_account_rejects_bad_opening_balance(client: TestClient, raw: str) -> None:
    resp = client.post("/accounts", data={"name": "x", "currency": "PLN", "opening_balance": raw})
    assert resp.status_code == 422
    assert _html.error_lines(resp.text) == {
        "field-opening_balance-error": "▲ invalid number",
    }


@pytest.mark.parametrize("raw", ["NaN", "1e400", "99999999999999999999"])
def test_set_default_rejects_bad_amount(client: TestClient, raw: str) -> None:
    resp = client.post("/budget/defaults/1", data={"amount": raw})
    assert resp.status_code in {404, 422}


def test_csrf_pre_auth_parser_failures_are_4xx(anon_client: TestClient) -> None:
    token = anon_client.cookies.get("__Host-csrf") or ""
    cases: list[dict[str, Any]] = [
        {"data": {"email": "a", "password": "b", "_csrf_token": "café"}},
        {
            "content": b"x",
            "headers": {"Content-Type": "multipart/form-data", "X-CSRF-Token": token},
        },
        {
            "content": "&".join(f"f{i}=1" for i in range(1500)).encode()
            + b"&_csrf_token="
            + token.encode(),
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        },
    ]
    for kwargs in cases:
        resp = anon_client.post("/auth/login", **kwargs)
        assert 400 <= resp.status_code < 500


def test_parse_amount_minor_is_bounded() -> None:
    assert parse_amount_minor("12,34", "PLN") == 1234
    assert parse_amount_minor(str(MAX_MINOR // 100), "PLN") == MAX_MINOR
    assert parse_amount_minor(str(MAX_MINOR // 100 + 1), "PLN") is None
    assert parse_amount_minor("1e3", "PLN") is None


def test_parse_int_bounds() -> None:
    assert parse_int("7") == 7
    assert parse_int(str(2**63)) is None
    assert parse_int("\u0661") is None
    assert parse_int("5", minimum=6) is None


def test_parse_year_month_defaults_to_fallback() -> None:
    assert parse_year_month(None, None, (2026, 11)) == (2026, 11)
    assert parse_year_month("2025", None, (2026, 11)) == (2025, 11)
