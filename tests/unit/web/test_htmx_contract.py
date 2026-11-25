"""T-Q236: one event vocabulary and one toast payload for every HX-Trigger emitter (Q-038)."""

from __future__ import annotations

import json

from fastapi.responses import Response

from budget_planner.web.htmx import Event, toast_payload, trigger


def _header(resp: Response) -> dict[str, object]:
    parsed: dict[str, object] = json.loads(resp.headers["HX-Trigger"])
    return parsed


def test_event_values_are_the_wire_names_templates_listen_for() -> None:
    assert {e.name: e.value for e in Event} == {
        "BALANCE_STALE": "balance-stale",
        "BUDGET_STALE": "budget-stale",
        "DIALOG_CLOSE": "dialog-close",
        "FORECAST_STALE": "forecast-stale",
        "LEDGER_STALE": "ledger-stale",
        "TODAY_STALE": "today-stale",
        "SETTINGS_CATEGORIES_STALE": "settings-categories-stale",
        "TOAST": "toast",
    }


def test_trigger_packs_events_as_json_object() -> None:
    resp = Response()
    trigger(resp, Event.LEDGER_STALE, Event.BALANCE_STALE)
    assert _header(resp) == {"ledger-stale": True, "balance-stale": True}


def test_trigger_without_events_or_toast_sets_no_header() -> None:
    resp = Response()
    trigger(resp)
    assert "HX-Trigger" not in resp.headers


def test_toast_payload_uses_variant_never_kind() -> None:
    assert toast_payload("success", "Saved") == {"variant": "success", "message": "Saved"}


def test_toast_payload_carries_undo_fields_only_when_given() -> None:
    payload = toast_payload("info", "Done", undo_url="/x/undo", undo_payload={"ids": [1, 2]})
    assert payload == {
        "variant": "info",
        "message": "Done",
        "undo_url": "/x/undo",
        "undo_payload": {"ids": [1, 2]},
    }


def test_trigger_with_toast_emits_toast_event_beside_stale_events() -> None:
    resp = Response()
    trigger(resp, Event.BUDGET_STALE, toast=toast_payload("success", "Account deleted"))
    assert _header(resp) == {
        "budget-stale": True,
        "toast": {"variant": "success", "message": "Account deleted"},
    }


def test_trigger_with_toast_only() -> None:
    resp = Response()
    trigger(resp, toast=toast_payload("error", "No"))
    assert _header(resp) == {"toast": {"variant": "error", "message": "No"}}
