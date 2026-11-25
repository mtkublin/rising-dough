"""Shared fragments (fields, popovers, plan, ledger, menus) render through the UI map (T-UR04a)."""

from __future__ import annotations

from datetime import UTC, datetime

from bs4 import BeautifulSoup
from jinja2 import Environment

from budget_planner.config import Settings
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.services.categories import CategoryPicker
from budget_planner.web.templating import build_jinja_env
from tests.ui_map import _html, rd_fragments as f
from tests.ui_map.locator import role

_NOW = datetime(2026, 11, 1, tzinfo=UTC)


def _env() -> Environment:
    return build_jinja_env(Settings(_env_file=None))


def _render(fragment: str, /, **context: object) -> str:
    return _env().get_template(f"fragments/{fragment}.html").render(**context)


def _cat(cat_id: int, name: str, direction: Direction, color: str | None = None) -> Category:
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


_TAKEAWAY = _cat(4, "Takeaway", Direction.EXPENSE, "#ff9f43")
_GROCERIES = _cat(5, "Groceries", Direction.EXPENSE, "#a3e635")
_SALARY = _cat(6, "Salary", Direction.INCOME, "#bef264")
_TRANSIT = _cat(7, "Transit", Direction.TRANSIT)
_PICKER = CategoryPicker(
    recent=(_TAKEAWAY, _GROCERIES),
    searchable=(_GROCERIES, _SALARY, _TAKEAWAY, _TRANSIT),
    total_count=4,
)


def test_category_picker_lists_recent_radios_and_search_count() -> None:
    html = _render("fields/category-picker", field_id="catpick-1", picker=_PICKER, selected_id=4)
    radios = _html.resolve(html, f.category_recent_radios)
    assert [(r.get("value"), r.has_attr("checked")) for r in radios] == [
        ("4", True),
        ("5", False),
    ]
    assert all(r.get("name") == "category" for r in radios)
    button = _html.resolve_one(html, f.category_search_button)
    assert button.get("aria-expanded") == "false"
    assert button.get("aria-controls") == "catpick-1"
    assert "search all 4 categories" in button.get_text()


def test_category_picker_searchable_options_carry_id_direction_and_first_active() -> None:
    html = _render("fields/category-picker", field_id="catpick-1", picker=_PICKER, open=True)
    options = _html.resolve(html, role("option"))
    assert [(o.get("data-value"), o.get("aria-selected")) for o in options] == [
        ("5", "true"),
        ("6", "false"),
        ("4", "false"),
        ("7", "false"),
    ]
    assert _html.text_of(html, f.category_option("Salary")).endswith("\u2191 income")
    assert _html.text_of(html, f.category_option("Transit")).endswith("\u21c4 transit")
    assert _html.text_of(html, f.category_option("Takeaway")).endswith("\u2193 expense")
    chip = _html.resolve_one(html, f.category_option("Takeaway")).select_one(".rd-chip")
    assert chip is not None
    assert chip.get("data-color") == "orange"
    search = _html.resolve_one(html, f.category_search_input)
    assert search.get("aria-activedescendant") == "catpick-1-o0"
    assert search.get("placeholder") == "search all 4 categories"
    assert _html.resolve_one(html, f.category_search_button).get("aria-expanded") == "true"


def test_category_picker_no_match_shows_the_query_and_new_category_link() -> None:
    html = _render(
        "fields/category-picker",
        field_id="catpick-1",
        picker=_PICKER,
        open=True,
        query="zoo",
        no_match=True,
        new_category_url="/settings/categories/new?name=zoo",
    )
    assert _html.resolve_one(html, f.category_search_input).get("value") == "zoo"
    assert (
        _html.resolve_one(html, f.category_search_input).has_attr("aria-activedescendant") is False
    )
    link = _html.resolve_one(html, f.category_new_link)
    assert link.get("href") == "/settings/categories/new?name=zoo"
    assert "No category matches" in _html.page_text(html)
    assert _html.text_of(html, f.category_new_link).endswith("“ zoo ”")


def test_category_picker_closed_panel_is_hidden() -> None:
    html = _render("fields/category-picker", field_id="catpick-1", picker=_PICKER)
    assert _html.count(html, f.category_panel) == 0  # hidden until the button opens it
    assert _html.count(html, f.category_search_input) == 0
    assert _html.resolve_one(html, f.category_search_button).get("aria-controls") == "catpick-1"
    assert (
        _html.count(
            _render("fields/category-picker", field_id="c", picker=_PICKER, open=True),
            f.category_panel,
        )
        == 1
    )


_COMPONENTS = (
    {"sign": "+", "percent": "19", "category_ids": (6,)},
    {"sign": "\u2212", "percent": "5", "category_ids": (5, 4)},
)


def test_formula_renders_each_component_with_indexed_fields() -> None:
    html = _render(
        "fields/formula",
        formula_id="formula-1",
        components=_COMPONENTS,
        options=(_SALARY, _GROCERIES, _TAKEAWAY),
        next_amount="1,836.93 PLN",
    )
    group = _html.resolve_one(html, f.formula)
    assert group.get("aria-labelledby") == "formula-1-label"
    percents = _html.resolve(html, f.component_percents)
    assert [(p.get("name"), p.get("value")) for p in percents] == [
        ("components[0][percent]", "19"),
        ("components[1][percent]", "5"),
    ]
    assert _html.resolve_one(html, f.formula_add).get("data-js") == "formula-add"
    assert _html.text_of(html, f.formula_result) == "→ next amount 1,836.93 PLN"
    assert _html.count(html, f.component_remove(1)) == 1
    assert _html.count(html, f.component_remove(2)) == 1


def test_formula_with_one_component_hides_remove_and_omits_empty_result() -> None:
    html = _render(
        "fields/formula",
        formula_id="formula-1",
        components=_COMPONENTS[:1],
        options=(_SALARY,),
    )
    assert _html.count(html, f.component_remove(1)) == 0  # hidden while it is the only one
    assert _html.text_of(html, f.formula_result) == ""


def test_formula_component_sign_percent_and_selected_categories() -> None:
    html = _render(
        "fields/formula-component",
        index=1,
        number=2,
        comp=_COMPONENTS[1],
        options=(_SALARY, _GROCERIES, _TAKEAWAY),
        list_id="formula-1-1-list",
        single=False,
    )
    add = _html.resolve_one(html, f.component_sign(2, "add"))
    subtract = _html.resolve_one(html, f.component_sign(2, "subtract"))
    assert (add.has_attr("checked"), subtract.has_attr("checked")) == (False, True)
    assert subtract.get("name") == "components[1][sign]"
    assert subtract.get("value") == "\u2212"
    boxes = BeautifulSoup(html, "html.parser").select('input[type="checkbox"]')  # list is hidden
    assert [(b.get("value"), b.has_attr("checked")) for b in boxes] == [
        ("6", False),
        ("5", True),
        ("4", True),
    ]
    assert {b.get("name") for b in boxes} == {"components[1][categories]"}
    trigger = html.split('data-js="multiselect"')[1].split("</button>")[0]
    assert "Groceries" in trigger
    assert "Takeaway" in trigger
    assert "Salary" not in trigger


def test_formula_component_without_categories_shows_placeholder() -> None:
    comp = {"sign": "+", "percent": "", "category_ids": ()}
    html = _render(
        "fields/formula-component",
        index=0,
        number=1,
        comp=comp,
        options=(_SALARY,),
        list_id="x-0-list",
        single=True,
    )
    assert "pick categories" in _html.page_text(html)
    assert _html.count(html, f.component_remove(1)) == 0  # hidden while it is the only one


def test_amount_input_field_variant_has_label_suffix_and_hook() -> None:
    html = _render(
        "fields/amount-input",
        field_id="ne-amount",
        name="amount",
        value="35.50",
        currency="PLN",
        required=True,
    )
    field = _html.resolve_one(html, f.amount_field())
    assert field.get("name") == "amount"
    assert field.get("value") == "35.50"
    assert field.get("inputmode") == "decimal"
    assert field.get("data-js") == "amount-input"
    assert field.has_attr("required")
    assert field.has_attr("aria-invalid") is False
    assert "PLN" in _html.page_text(html)


def test_amount_input_field_variant_error_is_linked_and_announced() -> None:
    html = _render(
        "fields/amount-input",
        field_id="ne-amount",
        name="amount",
        value="0.00",
        currency="EUR",
        error="Enter an amount above 0.00",
    )
    field = _html.resolve_one(html, f.amount_field())
    assert field.get("aria-invalid") == "true"
    assert field.get("aria-describedby") == "ne-amount-error"
    assert _html.text_of(html, role("alert")) == "▲ Enter an amount above 0.00"


def test_amount_input_hero_variant_has_hidden_label_sign_and_currency() -> None:
    html = _render(
        "fields/amount-input",
        field_id="hero-amount",
        name="amount",
        value="0.00",
        currency="PLN",
        variant="hero",
        sign="\u2212",
        error="Enter an amount above 0.00",
    )
    field = _html.resolve_one(html, f.amount_field("Amount"))
    assert field.get("aria-describedby") == "hero-amount-error"
    assert field.get("data-js") == "amount-input"
    assert "\u2212" in _html.page_text(html)
    assert "PLN" in _html.page_text(html)
    assert _html.text_of(html, role("alert")) == "▲ Enter an amount above 0.00"


_MONTH_PICKER = {
    "id": "period-1",
    "is_year": False,
    "year": 2026,
    "prev_year_url": "/plan/budget?period=2025-10",
    "next_year_url": "/plan/budget?period=2027-10",
    "cells": (
        {"label": "Sep", "url": "/plan/budget?period=2026-09", "current": False},
        {"label": "Oct", "url": "/plan/budget?period=2026-10", "current": True},
    ),
    "note": "oct = 7 oct → 7 nov",
}
_YEAR_PICKER = {
    "id": "period-2",
    "is_year": True,
    "cells": (
        {"label": "2025", "url": "/plan/year?year=2025", "current": False},
        {"label": "2026", "url": "/plan/year?year=2026", "current": True},
    ),
}


def test_period_picker_month_marks_the_current_cell_and_links_years() -> None:
    html = _render("popovers/period-picker", picker=_MONTH_PICKER)
    dialog = _html.resolve_one(html, f.period_picker)
    assert dialog.get("id") == "period-1"
    assert dialog.has_attr("popover")
    assert dialog.has_attr("data-open") is False
    assert _html.resolve_one(html, f.period_cell("Oct")).get("aria-current") == "true"
    assert _html.resolve_one(html, f.period_cell("Sep")).has_attr("aria-current") is False
    assert (
        _html.resolve_one(html, f.period_cell("Oct")).get("href") == "/plan/budget?period=2026-10"
    )
    assert _html.resolve_one(html, f.period_prev_year).get("href") == "/plan/budget?period=2025-10"
    assert _html.resolve_one(html, f.period_next_year).get("href") == "/plan/budget?period=2027-10"
    assert "oct = 7 oct → 7 nov" in _html.page_text(html)


def test_period_picker_year_kind_lists_years_only() -> None:
    html = _render("popovers/period-picker", picker={**_YEAR_PICKER, "open": True})
    assert _html.resolve_one(html, f.period_picker).has_attr("data-open")
    assert _html.resolve_one(html, f.period_cell("2026")).get("aria-current") == "true"
    assert _html.count(html, f.period_prev_year) == 0
    assert _html.count(html, role("link")) == 2


def test_period_nav_links_label_trigger_and_embeds_the_picker() -> None:
    html = _render(
        "plan/period-nav",
        label="October 2026",
        prev_url="/plan/budget?period=2026-09",
        next_url="/plan/budget?period=2026-11",
        picker=_MONTH_PICKER,
    )
    assert _html.resolve_one(html, f.period_prev).get("href") == "/plan/budget?period=2026-09"
    assert _html.resolve_one(html, f.period_next).get("href") == "/plan/budget?period=2026-11"
    assert _html.resolve_one(html, f.period_prev).get("aria-keyshortcuts") == "ArrowLeft"
    trigger = _html.resolve_one(html, f.period_trigger)
    assert trigger.get("popovertarget") == "period-1"
    assert trigger.get_text().strip().startswith("October 2026")
    assert _html.resolve_one(html, f.period_picker).get("id") == "period-1"


def test_period_nav_year_view_uses_year_labels() -> None:
    html = _render(
        "plan/period-nav",
        label="2026",
        prev_url="/plan/year?year=2025",
        next_url="/plan/year?year=2027",
        prev_label="Previous year",
        next_label="Next year",
        picker=_YEAR_PICKER,
    )
    nav = _html.resolve_one(html, f.period_nav)
    assert [a.get("aria-label") for a in nav.find_all("a", attrs={"aria-keyshortcuts": True})] == [
        "Previous year",
        "Next year",
    ]


def test_row_menu_has_button_menu_items_and_cancel() -> None:
    html = _render(
        "menus/row-menu",
        menu_id="menu-9",
        title="Takeaway · \u221235.50 PLN",
        sub="31 OCT · Credit Card",
        items=(
            {"label": "edit", "href": "/transactions/9/edit"},
            {
                "label": "delete",
                "hx_post": "/transactions/9/delete",
                "hx_target": "#tx-9",
                "hx_swap": "outerHTML",
                "danger": True,
            },
        ),
    )
    button = _html.resolve_one(html, f.row_menu_button)
    assert button.get("popovertarget") == "menu-9"
    assert button.get("aria-haspopup") == "menu"
    menu = _html.resolve_one(html, f.row_menu)
    assert menu.get("id") == "menu-9"
    assert menu.has_attr("popover")
    assert "Takeaway · \u221235.50 PLN" in menu.get_text()
    assert "31 OCT · Credit Card" in menu.get_text()
    assert _html.resolve_one(html, f.row_menu_item("edit")).get("href") == "/transactions/9/edit"
    delete = _html.resolve_one(html, f.row_menu_item("delete"))
    assert delete.get("hx-post") == "/transactions/9/delete"
    assert delete.get("hx-target") == "#tx-9"
    assert delete.get("hx-swap") == "outerHTML"
    assert "rd-menu__item--danger" in (delete.get("class") or [])
    cancel = _html.resolve_one(html, f.row_menu_item("cancel"))
    assert cancel.get("popovertargetaction") == "hide"
    assert len(_html.resolve(html, role("menuitem"))) == 3


def test_row_menu_item_kinds_get_post_confirm_phone_and_danger() -> None:
    html = _render(
        "menus/row-menu",
        menu_id="menu-3",
        title="Checking",
        items=(
            {"label": "edit", "hx_get": "/accounts/3/edit"},
            {"label": "reconcile", "hx_get": "/accounts/3/reconcile", "href": "/r", "phone": True},
            {
                "label": "remove",
                "hx_post": "/accounts/3/remove",
                "hx_confirm": "Sure?",
                "danger": True,
            },
        ),
    )
    edit = _html.resolve_one(html, f.row_menu_item("edit"))
    assert (edit.name, edit.get("href"), edit.get("hx-get")) == (
        "a",
        "/accounts/3/edit",
        "/accounts/3/edit",
    )
    assert (edit.get("hx-target"), edit.get("hx-swap")) == ("#modal-root", "innerHTML")
    rec = _html.resolve_one(html, f.row_menu_item("reconcile"))
    assert (rec.get("href"), rec.get("class")) == ("/r", ["rd-menu__item", "rd-menu__item--phone"])
    rem = _html.resolve_one(html, f.row_menu_item("remove"))
    assert (rem.name, rem.get("hx-post"), rem.get("hx-confirm")) == (
        "button",
        "/accounts/3/remove",
        "Sure?",
    )
    assert rem.get("class") == ["rd-menu__item", "rd-menu__item--danger"]
    assert "rd-menu__sub" not in html  # no sub line without ``sub``


def test_pagination_shows_older_newer_and_the_aside() -> None:
    html = _render(
        "ledger/pagination",
        page=2,
        older_url="/ledger?page=3",
        newer_url="/ledger?page=1",
        deleted_url="/ledger/deleted",
    )
    assert _html.resolve_one(html, f.older).get("href") == "/ledger?page=3"
    assert _html.resolve_one(html, f.older).get("rel") == ["next"]
    assert _html.resolve_one(html, f.newer).get("href") == "/ledger?page=1"
    assert _html.resolve_one(html, f.newer).get("rel") == ["prev"]
    assert _html.resolve_one(html, f.recently_deleted).get("href") == "/ledger/deleted"
    assert "page 2" in _html.text_of(html, f.pagination)


def test_pagination_first_and_last_page_omit_missing_links() -> None:
    html = _render("ledger/pagination", page=1, older_url=None, newer_url=None)
    assert _html.count(html, f.older) == 0
    assert _html.count(html, f.newer) == 0
    assert _html.count(html, f.recently_deleted) == 0
    assert _html.text_of(html, f.pagination) == "page 1"
