"""T-UR34l (ADR-0147 §3, ADR-0148, gap G11): the 422 context carries a count and human labels."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from fastapi import Request
from fastapi.responses import HTMLResponse

from budget_planner.domain.errors import ValidationError
from budget_planner.web import errors
from budget_planner.web.field_labels import FIELD_LABELS, field_label, field_summary


class _PlainRequest:
    """Request double: a browser navigation (no HX-Request header)."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}


def _render_context(monkeypatch: pytest.MonkeyPatch, fields: dict[str, str]) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def fake_render(_request: Request, template: str, status: int, **context: Any) -> HTMLResponse:
        seen.update(context, template=template, status=status)
        return HTMLResponse("", status_code=status)

    monkeypatch.setattr(errors, "_render", fake_render)
    request = cast(Request, _PlainRequest())
    asyncio.run(errors.handle_validation(request, ValidationError(fields=fields)))
    return seen


def test_two_field_error_has_count_and_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    fields = {"amount": "Amount is required", "operation_date": "Pick a date"}
    ctx = _render_context(monkeypatch, fields)
    assert ctx["template"] == "errors/422.html"
    assert ctx["status"] == 422
    assert ctx["fields"] == fields
    assert ctx["field_count"] == 2
    assert ctx["field_errors"] == (
        ("amount", "Amount", "Amount is required"),
        ("operation_date", "Date", "Pick a date"),
    )


def test_one_field_error(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _render_context(monkeypatch, {"category_id": "Pick a category"})
    assert ctx["field_count"] == 1
    assert ctx["field_errors"] == (("category_id", "Category", "Pick a category"),)


def test_no_fields_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _render_context(monkeypatch, {})
    assert (ctx["field_count"], ctx["field_errors"]) == (0, ())


def test_unknown_field_falls_back_to_title_case() -> None:
    assert field_label("due_day_of_month") == "Due Day Of Month"
    assert field_summary({"foo_bar": "bad"}) == (("foo_bar", "Foo Bar", "bad"),)


def test_label_mapping_is_read_only() -> None:
    mapping = cast(dict[str, str], FIELD_LABELS)
    with pytest.raises(TypeError):
        mapping["x"] = "y"
