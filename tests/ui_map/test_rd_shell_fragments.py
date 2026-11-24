"""Flash, toast and state fragments render through the UI map (T-UR02)."""

from __future__ import annotations

from jinja2 import Environment

from budget_planner.config import Settings
from budget_planner.web.templating import build_jinja_env
from tests.ui_map import _html
from tests.ui_map.locator import role


def _env() -> Environment:
    return build_jinja_env(Settings(_env_file=None))


def _render(name: str, **context: object) -> str:
    return _env().get_template(f"fragments/{name}.html").render(**context)


def test_flash_success_is_a_status_with_message_and_dismiss() -> None:
    html = _render("flash/success", message="Saved · Takeaway")
    assert _html.text_of(html, role("status")).startswith("● Saved · Takeaway")
    assert _html.count(html, role("button", "Dismiss")) == 1


def test_flash_error_is_an_alert_and_retry_is_optional() -> None:
    without = _render("flash/error", message="Could not save.")
    assert _html.text_of(without, role("alert")).startswith("▲ Could not save.")
    assert _html.count(without, role("button", "retry")) == 0
    with_retry = _render("flash/error", message="x", retry_url="/retry")
    assert _html.resolve_one(with_retry, role("button", "retry")).get("hx-post") == "/retry"


def test_toast_undo_posts_to_the_undo_url_with_csrf() -> None:
    context = {"message": "Takeaway deleted", "undo_url": "/undo/5", "csrf_token": "tok"}
    html = _render("toast/undo", **context)
    assert _html.count(html, role("button", "undo")) == 1
    assert 'action="/undo/5"' in html
    assert 'name="_csrf_token" value="tok"' in html
    assert _html.text_of(html, role("status")).startswith("Takeaway deleted")


def test_states_render_their_copy_and_actions() -> None:
    accounts = _render("states/accounts-empty")
    assert _html.count(accounts, role("link", "[ new account ]")) == 1
    assert "No accounts yet." in accounts
    upcoming = _render("states/upcoming-empty")
    assert _html.resolve_one(upcoming, role("link", "show all")).get("href") == "/today?range=all"
    no_matches = _render("states/no-matches", summary="Transport · “pizza”")
    assert "Transport · “pizza”" in no_matches
    assert _html.count(no_matches, role("link", "clear filters")) == 1
    assert "Nothing deleted." in _render("states/empty-inline")
    for name in ("ledger-first-run", "planned-empty", "recurring-empty"):
        assert _html.count(_render(f"states/{name}"), role("link", "[ new entry ]")) == 1, name
    assert "rd-skeleton" in _render("states/loading")
