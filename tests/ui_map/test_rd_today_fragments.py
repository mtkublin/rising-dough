"""Today fragments and view values render the handoff's figures (T-UR07)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from jinja2 import Environment

from budget_planner.config import Settings
from budget_planner.domain.accounts import Account
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.services.today import AffordResult
from budget_planner.web import today_data
from budget_planner.web.templating import build_jinja_env
from tests.ui_map import _html
from tests.ui_map.locator import by_id

_NOW = datetime(2026, 11, 1, tzinfo=UTC)
_TODAY = date(2026, 10, 31)
_CCY = "PLN"
MINUS = chr(0x2212)  # handoff negative sign


def _env() -> Environment:
    return build_jinja_env(Settings(_env_file=None))


def _render(fragment: str, /, **context: object) -> str:
    return _env().get_template(f"fragments/{fragment}.html").render(csp_nonce="", **context)


def _state(amount_minor: int, result: AffordResult) -> today_data.AffordState:
    return today_data.AffordState(typed=True, amount_minor=amount_minor, result=result)


def test_afford_result_shows_per_day_and_arrowed_delta() -> None:
    result = AffordResult(
        per_day_minor=16_428, delta_minor=-3_571, pace_tag="on_track", days_left=7
    )
    html = _render(
        "today/afford-result", afford=today_data.afford_panel(_state(25_000, result), _CCY)
    )
    assert _html.text_of(html, by_id("afford-result")).startswith(
        "→ per day becomes 164.28 (↓ 35.71"
    )


def test_afford_result_over_shows_unclamped_per_day_and_the_over_amount() -> None:
    result = AffordResult(
        per_day_minor=0,
        delta_minor=-19_999,
        pace_tag="over_limit",
        days_left=7,
        unclamped_per_day_minor=-1_420,
        over_minor=11_420,
    )
    html = _render(
        "today/afford-result", afford=today_data.afford_panel(_state(180_000, result), _CCY)
    )
    assert (
        _html.text_of(html, by_id("afford-result"))
        == f"▲ per day becomes {MINUS}14.20 · 114.20 over"
    )


def test_afford_panel_invalid_state_has_message_and_no_result() -> None:
    state = today_data.AffordState(typed=True, amount_minor=None, result=None)
    panel = today_data.afford_panel(state, _CCY)
    assert (panel.invalid, panel.message, panel.input_text) == (
        True,
        "Enter an amount, like 250.00",
        "",
    )
    assert _html.text_of(_render("today/afford-result", afford=panel), by_id("afford-result")) == ""


def test_afford_panel_groups_the_typed_amount_like_the_handoff() -> None:
    result = AffordResult(per_day_minor=0, delta_minor=0, pace_tag="on_track", days_left=7)
    assert today_data.afford_panel(_state(180_000, result), _CCY).input_text == "1,800.00"


def _cat(cat_id: int, name: str, direction: Direction, color: str | None) -> Category:
    return Category(
        id=cat_id,
        user_id=1,
        name=name,
        direction=direction,
        is_system=False,
        color=color,
        created_at=_NOW,
        updated_at=_NOW,
        deleted_at=None,
    )


def _upcoming_row(
    planned_id: int, day: date, name: str, amount: int, cat_id: int
) -> today_data.UpcomingRow:
    return today_data.UpcomingRow(
        operation_date=day,
        description=name,
        amount_minor=amount,
        is_overdue=day < _TODAY,
        kind="planned",
        planned_id=planned_id,
        rule_id=None,
        override_present=False,
        is_formula=False,
        category_id=cat_id,
        account_id=1,
        dest_account_id=None,
    )


def test_upcoming_list_groups_rows_with_flag_sign_and_menu_text() -> None:
    account = Account(
        id=1,
        user_id=1,
        name="Checking",
        currency=_CCY,
        opening_balance=0,
        type=None,
        is_liability=False,
        credit_limit_minor=None,
        created_at=_NOW,
        updated_at=_NOW,
        deleted_at=None,
    )
    rows = (
        _upcoming_row(1, date(2026, 10, 28), "Annual insurance", 41_200, 1),
        _upcoming_row(2, _TODAY, "Tax refund", 112_045, 2),
        _upcoming_row(3, date(2026, 11, 1), "Fixed Costs", 27_794, 1),
    )
    view = today_data.today_upcoming(
        rows,
        _TODAY,
        {
            1: _cat(1, "Other", Direction.EXPENSE, "#ff8a8a"),
            2: _cat(2, "VAT Refund", Direction.INCOME, "#86efac"),
        },
        {1: account},
        base_currency=_CCY,
        window_label="30",
    )
    html = _render("today/upcoming-list", upcoming=view, window_label="30")
    assert [g.heading for g in view.groups] == ["▲ OVERDUE · 1", "● DUE TODAY · 1", "NEXT 30 DAYS"]
    overdue = _html.text_of(html, by_id("upcoming-planned-1"))
    assert "28 OCT" in overdue
    assert "▲ overdue 3 days" in overdue
    assert f"{MINUS}412.00 PLN" in overdue
    first = view.groups[0].rows[0]
    assert (first.menu_title, first.menu_sub) == (
        f"Annual insurance · {MINUS}412.00 PLN",
        "28 OCT · Checking",
    )
    refund = by_id("upcoming-planned-2")
    assert "+1,120.45 PLN" in _html.text_of(html, refund)
    assert _html.resolve_one(html, refund)["data-status"] == "due"
    assert view.has_due is True


def test_upcoming_cap_applies_to_next_days_rows_not_to_flagged_rows() -> None:
    """Overdue and due-today rows are always listed; only the next-N-days rows stop at 6."""
    rows = (
        _upcoming_row(1, date(2026, 10, 28), "Annual insurance", 41_200, 1),
        _upcoming_row(2, _TODAY, "Tax refund", 112_045, 2),
        *(_upcoming_row(10 + n, date(2026, 11, n), f"Later {n}", 1_000, 1) for n in range(1, 9)),
    )
    categories = {
        1: _cat(1, "Other", Direction.EXPENSE, None),
        2: _cat(2, "VAT Refund", Direction.INCOME, None),
    }
    view = today_data.today_upcoming(
        rows, _TODAY, categories, {}, base_currency=_CCY, window_label="30"
    )
    assert [(g.key, len(g.rows)) for g in view.groups] == [
        ("overdue", 1),
        ("due", 1),
        ("upcoming", 6),
    ]
    assert (view.shown_count, view.total_count, view.has_more) == (6, 10, True)
