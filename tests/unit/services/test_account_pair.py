"""Same-account rule for planned / transaction source and destination (T-D153)."""

from __future__ import annotations

import pytest

from budget_planner.services.account_pair import SAME_ACCOUNT_MESSAGE, validate_distinct_accounts


def test_same_account_returns_message() -> None:
    assert validate_distinct_accounts(3, 3) == SAME_ACCOUNT_MESSAGE


@pytest.mark.parametrize(("source", "dest"), [(1, 2), (1, None)])
def test_distinct_or_missing_dest_is_valid(source: int, dest: int | None) -> None:
    assert validate_distinct_accounts(source, dest) is None
