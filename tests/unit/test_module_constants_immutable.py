"""T-Q263: module-level lookup tables are read-only mappings."""

from __future__ import annotations

import pytest

from budget_planner.db import migrate
from budget_planner.domain import money
from budget_planner.services import audit
from budget_planner.web import recurring_forms, today_data


@pytest.mark.parametrize(
    "table",
    [
        money.CURRENCY_EXPONENTS,
        migrate._POST_APPLY_HOOKS,
        audit._SHAPE_RULES,
        today_data._PACE_LABELS,
        today_data._WINDOWS,
        recurring_forms.EMPTY_TERM_INPUT,
    ],
)
def test_lookup_table_is_a_read_only_mapping(table: object) -> None:
    assert not hasattr(table, "__setitem__")
    assert not hasattr(table, "update")
