"""HTMX response helpers: dialog, saved row, removed row, 422 dialog (T-UR04b, ADR-0107 3 to 5).

The helpers are exercised through a throwaway app that mounts the real Jinja
environment plus two in-memory templates standing in for the caller's dialog
and row. Headers are asserted exactly; markup through the UI map.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from jinja2 import ChoiceLoader, DictLoader

from budget_planner.config import Settings
from budget_planner.web.dialogs import (
    dialog_response,
    invalid_dialog_response,
    removed_response,
    saved_response,
)
from budget_planner.web.htmx import Event
from budget_planner.web.templating import build_jinja_env
from tests.ui_map import _html
from tests.ui_map.locator import by_id, role

DIALOG = """\
<dialog data-js="modal" aria-label="New thing" open>
{% if field_count is defined and field_count %}
{% include "fragments/forms/error-summary.html" %}
{% endif %}
<input id="field-amount" aria-label="Amount" name="amount" value="{{ amount }}"
  {% if errors is defined and "amount" in errors %}aria-invalid="true"{% endif %}>
<input id="field-name" aria-label="Name" name="name"
  {% if errors is defined and "name" in errors %}aria-invalid="true"{% endif %}>
</dialog>
"""
ROW = '<tr id="row-{{ row_id }}"><td>{{ label }}</td></tr>'


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(_env_file=None)
    env = build_jinja_env(settings)
    assert env.loader is not None
    templates = DictLoader({"t/dialog.html": DIALOG, "t/row.html": ROW})
    env.loader = ChoiceLoader([templates, env.loader])
    app = FastAPI()
    app.state.jinja_env = env
    app.state.settings = settings

    @app.get("/open")
    def open_dialog(request: Request) -> HTMLResponse:
        return dialog_response(request, "t/dialog.html", {"amount": "5.00"})

    @app.get("/saved")
    def saved(request: Request) -> HTMLResponse:
        return saved_response(
            request,
            "t/row.html",
            {"row_id": 7, "label": "Takeaway"},
            message="Saved · Takeaway",
            events=(Event.LEDGER_STALE, Event.BALANCE_STALE),
        )

    @app.get("/removed")
    def removed(request: Request) -> HTMLResponse:
        return removed_response(
            request,
            message="Deleted · Takeaway",
            undo_url="/ledger/7/restore",
            events=(Event.LEDGER_STALE,),
        )

    @app.get("/invalid")
    def invalid(request: Request) -> HTMLResponse:
        return invalid_dialog_response(
            request,
            "t/dialog.html",
            {"amount": ""},
            {"amount": "Amount is required", "name": "Pick a name"},
        )

    with TestClient(app) as test_client:
        yield test_client


def test_dialog_response_retargets_into_modal_root(client: TestClient) -> None:
    resp = client.get("/open")
    assert resp.status_code == 200
    assert resp.headers["HX-Retarget"] == "#modal-root"
    assert resp.headers["HX-Reswap"] == "innerHTML"
    assert _html.exists(resp.text, role("dialog", "New thing"))
    assert _html.resolve_one(resp.text, role("textbox", "Amount")).get("value") == "5.00"


def test_dialog_is_wrapped_so_dialog_js_finds_it(client: TestClient) -> None:
    body = client.get("/open").text.strip()
    assert body.startswith("<div>")
    assert body.endswith("</div>")
    assert body.count("<dialog") == 1
    assert body.index("<dialog") > 0


def test_saved_response_swaps_row_and_flashes_out_of_band(client: TestClient) -> None:
    resp = client.get("/saved")
    assert resp.status_code == 200
    assert json.loads(resp.headers["HX-Trigger"]) == {"ledger-stale": True, "balance-stale": True}
    assert _html.text_of(resp.text, by_id("row-7")) == "Takeaway"
    flash_region = _html.resolve_one(resp.text, by_id("flash-region"))
    assert flash_region.get("hx-swap-oob") == "innerHTML"
    assert _html.text_of(resp.text, role("status")).startswith("● Saved · Takeaway")
    modal_root = _html.resolve_one(resp.text, by_id("modal-root"))
    assert modal_root.get("hx-swap-oob") == "innerHTML"
    assert modal_root.get_text() == ""


def test_removed_response_deletes_row_and_offers_undo_toast(client: TestClient) -> None:
    resp = client.get("/removed")
    assert resp.status_code == 200
    assert resp.headers["HX-Reswap"] == "delete"
    assert json.loads(resp.headers["HX-Trigger"]) == {"ledger-stale": True}
    toast_root = _html.resolve_one(resp.text, by_id("toast-root"))
    assert toast_root.get("hx-swap-oob") == "innerHTML"
    assert _html.text_of(resp.text, role("status")).startswith("Deleted · Takeaway")
    form = _html.form_of(resp.text, role("button", "undo"))
    assert form.get("hx-post") == "/ledger/7/restore"


def test_invalid_dialog_is_422_with_summary_and_aria_invalid(client: TestClient) -> None:
    resp = client.get("/invalid")
    assert resp.status_code == 422
    assert resp.headers["HX-Retarget"] == "#modal-root"
    assert resp.headers["HX-Reswap"] == "innerHTML"
    summary = _html.text_of(resp.text, role("alert"))
    assert "2 fields need attention" in summary
    assert "Amount : Amount is required" in summary
    assert "Name : Pick a name" in summary
    link = _html.resolve_one(resp.text, role("link", "Amount"))
    assert link.get("href") == "#field-amount"
    for label in ("Amount", "Name"):
        assert _html.resolve_one(resp.text, role("textbox", label)).get("aria-invalid") == "true"


def test_error_summary_singular_wording() -> None:
    env = build_jinja_env(Settings(_env_file=None))
    html = env.get_template("fragments/forms/error-summary.html").render(
        field_count=1, field_errors=(("category_id", "Category", "Pick a category"),)
    )
    assert "1 field needs attention" in _html.text_of(html, role("alert"))
    assert _html.resolve_one(html, role("link", "Category")).get("href") == "#field-category_id"
