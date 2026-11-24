"""Accounts row, sparkline and snapshot fragments render exact values (T-UR08, ADR-0107)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from jinja2 import Environment

from budget_planner.config import Settings
from budget_planner.domain.accounts import Account, AccountStats
from budget_planner.domain.snapshots import AccountSnapshot
from budget_planner.services.account_planned import AccountPlanned
from budget_planner.web.accounts_view import (
    account_row,
    accounts_hero,
    credit_utilisation,
    snapshot_line,
    trend_view,
)
from budget_planner.web.templating import build_jinja_env
from tests.ui_map import _html, accounts
from tests.ui_map.locator import role

_MINUS = "\N{MINUS SIGN}"
_NOW = datetime(2026, 11, 1, tzinfo=UTC)
_DAY = date(2026, 11, 1)


def _env() -> Environment:
    return build_jinja_env(Settings(_env_file=None))


_VISA = Account(
    id=9,
    user_id=1,
    name="Visa",
    type="credit card",
    currency="PLN",
    opening_balance=0,
    is_liability=True,
    credit_limit_minor=500_000,
    created_at=_NOW,
    updated_at=_NOW,
    deleted_at=None,
)


def _account(**changes: Any) -> Account:
    return replace(_VISA, **changes)


def _card(acc: Account, balance: int, **kw: object) -> dict[str, object]:
    series = [(_DAY + timedelta(days=i), balance + i * 100) for i in range(90)]
    card: dict[str, object] = {
        "account": acc,
        "balance": balance,
        "stats": AccountStats(
            account_id=acc.id,
            balance=balance,
            base_balance=balance,
            txn_count=468,
            last_txn_date=None,
        ),
        "series": series,
        "snapshots": [
            AccountSnapshot(id=1, account_id=acc.id, taken_at=_NOW, balance=370_244, note="")
        ],
        "planned": AccountPlanned(
            account_id=acc.id, currency="PLN", net_minor=-28_925, projected_minor=-274_499
        ),
        "utilisation": credit_utilisation(acc, balance),
    }
    card.update(kw)
    return card


def _render_row(card: dict[str, object]) -> str:
    row = account_row(card)
    return _env().get_template("fragments/rows/account-row.html").render(row=row)


def test_trend_has_eleven_points_ten_apart_inside_the_plot_height() -> None:
    series = [(_DAY + timedelta(days=i), i * 100) for i in range(90)]
    trend = trend_view(series, 8_900)
    pairs = [p.split(",") for p in trend.points.split(" ")]
    assert [float(x) for x, _ in pairs] == [float(i * 10) for i in range(11)]
    assert float(pairs[0][1]) == 24.0  # lowest balance, bottom of the 24 px plot
    assert float(pairs[-1][1]) == 0.0
    assert trend.negative is False


def test_trend_of_one_point_draws_no_line_and_negative_balance_flags_it() -> None:
    trend = trend_view([(_DAY, -500)], -500)
    assert (trend.points, trend.negative) == ("", True)


def test_row_view_holds_exact_values() -> None:
    row = account_row(_card(_account(), -245_574))
    assert (row.id, row.subtitle, row.checked, row.txn_count) == (
        9,
        "credit card · liability",
        "01 NOV",
        468,
    )
    assert (row.balance_sign, row.balance_minor, row.negative) == (_MINUS, -245_574, True)
    assert (row.after_minor, row.after_sign) == (-274_499, _MINUS)
    assert row.menu_sub == f"liability · {_MINUS}2,455.74 PLN"
    assert row.credit is not None
    assert (row.credit.used_pct, row.credit.available_minor, row.credit.limit_minor) == (
        49,
        254_426,
        500_000,
    )


def test_account_without_snapshot_reads_never_and_zero_planned_hides_the_note() -> None:
    card = _card(_account(is_liability=False, credit_limit_minor=None, type="bank"), 12_345)
    card["snapshots"] = []
    card["planned"] = AccountPlanned(account_id=9, currency="PLN", net_minor=0, projected_minor=0)
    row = account_row(card)
    assert (row.checked, row.after_minor, row.credit, row.subtitle) == ("never", None, None, "bank")


def test_row_fragment_prints_the_handoff_values() -> None:
    html = _render_row(_card(_account(), -245_574))
    text = _html.text_of(html, accounts.row(9))
    assert f"{_MINUS}2,455.74 PLN" in text
    assert f"→ {_MINUS}2,744.99 after planned" in text
    assert "used 49% · available 2,544.26 of 5,000.00" in text
    assert "468" in text
    bar = _html.resolve_one(html, role("img", "percent spent"))
    assert bar["aria-label"] == "49 percent spent, 51 percent left"
    assert "█" * 5 in bar.get_text()
    assert _html.resolve_one(html, accounts.credit_utilisation) is not None


def test_row_fragment_asset_has_no_credit_line_and_links_the_existing_routes() -> None:
    acc = _account(is_liability=False, credit_limit_minor=None, type="bank", name="Checking")
    html = _render_row(_card(acc, 368_581, planned=None))
    assert _html.count(html, accounts.credit_utilisation) == 0
    link = _html.resolve_one(html, accounts.reconcile_button(9))
    assert (link["href"], link["hx-get"], link["hx-target"]) == (
        "/accounts/9/reconcile",
        "/accounts/9/reconcile",
        "#modal-root",
    )
    assert "after planned" not in _html.text_of(html, accounts.row(9))
    assert _html.count(html, accounts.row_menu(9)) == 1


def test_sparkline_fragment_draws_inside_the_margin() -> None:
    html = _render_row(_card(_account(), -245_574))
    line = _html.resolve_one(html, role("img", "Balance trend"))
    assert (line["width"], line["height"], line["viewbox"]) == ("100", "28", "0 0 100 28")
    assert "rd-spark--negative" in line["class"]
    poly = line.find("polyline")
    assert poly is not None
    assert poly["transform"] == "translate(0 2)"


def test_snapshot_fragment_prints_date_and_amount() -> None:
    snap = AccountSnapshot(
        id=2, account_id=9, taken_at=datetime(2026, 4, 1, tzinfo=UTC), balance=370_244, note=""
    )
    html = (
        _env()
        .get_template("fragments/rows/reconcile-snapshot.html")
        .render(snapshot=snapshot_line(snap), currency="PLN")
    )
    assert _html.text_of(html, accounts.snapshot_item) == "01 APR 3,702.44 PLN"


def test_hero_signs_and_fit() -> None:
    hero = accounts_hero(
        count=10,
        net_minor=3_443_969,
        assets_minor=3_689_543,
        liabilities_minor=245_574,
        planned_minor=-31_254,
        currency="PLN",
    )
    assert (hero.net_sign, hero.liabilities_sign, hero.planned_sign) == ("", _MINUS, _MINUS)
    assert (hero.fit.digits, hero.fit.marks, hero.fit.signs) == (7, 2, 0)


def test_checked_cell_keeps_the_handoff_whitespace() -> None:
    """The phone cell is ``white-space: pre``: the text is `` · checked 01 NOV`` with no padding."""
    cells = _html.resolve(_render_row(_card(_account(), -245_574)), role("cell"))
    assert cells[2].get_text() == " · checked 01 NOV"
