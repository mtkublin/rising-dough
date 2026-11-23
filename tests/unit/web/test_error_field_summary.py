"""T-UR34l / T-UR35b (ADR-0147 §3, ADR-0148, gap G11): the 422 summary is a pure function."""

from __future__ import annotations

from typing import cast

import pytest

from budget_planner.web.errors import validation_summary
from budget_planner.web.field_labels import FIELD_LABELS, field_label, field_summary


def test_two_field_error_has_count_and_labels() -> None:
    fields = {"amount": "Amount is required", "operation_date": "Pick a date"}
    count, rows = validation_summary(fields)
    assert count == 2
    assert rows == (
        ("amount", "Amount", "Amount is required"),
        ("operation_date", "Date", "Pick a date"),
    )


def test_one_field_error() -> None:
    count, rows = validation_summary({"category_id": "Pick a category"})
    assert count == 1
    assert rows == (("category_id", "Category", "Pick a category"),)


def test_no_fields_is_zero() -> None:
    assert validation_summary({}) == (0, ())


def test_unknown_field_falls_back_to_title_case() -> None:
    assert field_label("due_day_of_month") == "Due Day Of Month"
    assert field_summary({"foo_bar": "bad"}) == (("foo_bar", "Foo Bar", "bad"),)


def test_label_mapping_is_read_only() -> None:
    mapping = cast(dict[str, str], FIELD_LABELS)
    with pytest.raises(TypeError):
        mapping["x"] = "y"
