"""``positive_amount``: the dialog copy for a non-positive amount (PAR-C, handoff parity)."""

from __future__ import annotations

import pytest

from budget_planner.web.params import positive_amount


@pytest.mark.parametrize(
    ("raw", "currency", "expected"),
    [
        ("0", "PLN", (None, "Enter an amount above 0.00")),
        ("-1", "PLN", (None, "Enter an amount above 0.00")),
        ("0", "JPY", (None, "Enter an amount above 0")),
        ("-5", "JPY", (None, "Enter an amount above 0")),
        ("12.34", "PLN", (1234, None)),
        ("500", "JPY", (500, None)),
        ("abc", "PLN", (None, "Enter an amount above 0.00")),
    ],
)
def test_positive_amount(raw: str, currency: str, expected: tuple[int | None, str | None]) -> None:
    assert positive_amount(raw, currency) == expected
