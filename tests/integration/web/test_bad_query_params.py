"""T-Q282 (ADR-0141 amendment 2026-11-22): every malformed query parameter is a 422.

A present-but-invalid ``year`` / ``month`` / date / integer never falls back to the current
period or to "no filter"; an absent (or empty) one still renders the default.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.ui_map import _html, errors

HX = {"HX-Request": "true"}

# (path, parameter, bad value)
BAD_CASES: tuple[tuple[str, str, str], ...] = (
    ("/plan", "year", "abc"),
    ("/plan", "month", "13"),
    ("/plan?tab=year", "year", "abc"),
    ("/plan?tab=forecast", "horizon", "7"),
    ("/plan?tab=forecast", "horizon", "abc"),
    ("/plan?tab=analytics", "month", "0"),
    ("/budget", "year", "abc"),
    ("/budget", "month", "13"),
    ("/budget/yearly", "year", "abc"),
    ("/budget/rules/1/overrides/new", "month", "13"),
    ("/budget/rules/1/overrides/new", "year", "abc"),
    ("/forecast", "horizon_months", "abc"),
    ("/forecast/view", "horizon_months", "abc"),
    ("/ledger", "date_from", "2026-02-30"),
    ("/ledger", "date_to", "tomorrow"),
    ("/ledger", "account_id", "x"),
    ("/ledger", "category_id", "x"),
    ("/ledger", "page", "x"),
    ("/ledger", "page_size", "x"),
    ("/ledger/table", "date_from", "2026-02-30"),
    ("/ledger/table", "account_id", "x"),
    ("/transactions/export", "date_from", "2026-02-30"),
    ("/transactions/export", "account_id", "x"),
    ("/transactions/export", "min_amount", "x"),
    ("/transactions/export", "max_amount", "x"),
    ("/planned/export", "date_from", "2026-02-30"),
    ("/planned/export", "date_to", "2026-13-01"),
    ("/transactions/_limit_preview", "account_id", "x"),
    ("/transactions/_limit_preview", "category_id", "x"),
)

OK_PATHS: tuple[str, ...] = tuple(sorted({path for path, _, _ in BAD_CASES}))


def _url(path: str, name: str, value: str) -> str:
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}{name}={value}"


@pytest.mark.parametrize(("path", "name", "value"), BAD_CASES)
def test_bad_value_is_422_page_naming_the_parameter(
    client: TestClient, path: str, name: str, value: str
) -> None:
    r = client.get(_url(path, name, value))

    assert r.status_code == 422
    assert "Check the form" in _html.text_of(r.text, errors.heading)
    assert name in _html.text_of(r.text, errors.main)


@pytest.mark.parametrize(("path", "name", "value"), BAD_CASES[:4])
def test_bad_value_on_htmx_request_is_422_error_flash(
    client: TestClient, path: str, name: str, value: str
) -> None:
    r = client.get(_url(path, name, value), headers=HX)

    assert r.status_code == 422
    assert name in _html.text_of(r.text, errors.alert)


@pytest.mark.parametrize("path", OK_PATHS)
def test_absent_or_empty_parameters_render_the_default(client: TestClient, path: str) -> None:
    sep = "&" if "?" in path else "?"
    bare = client.get(path)
    empty = client.get(f"{path}{sep}year=&month=&date_from=&account_id=&horizon_months=")

    assert bare.status_code in (200, 404)
    assert empty.status_code == bare.status_code


def test_valid_month_is_still_honoured(client: TestClient) -> None:
    r = client.get("/budget?year=2026&month=10")

    assert r.status_code == 200
