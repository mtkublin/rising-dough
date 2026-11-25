"""Every ``edit_dialogs`` name resolves in the handoff overlays (T-UR10, ADR-0106)."""

from __future__ import annotations

import pytest

from tests.ui_map import _html, edit_dialogs as d
from tests.ui_map.locator import Locator
from tests.ui_map.mockup_routes import HANDOFF_ROOT, handoff_page

_OVERLAYS = HANDOFF_ROOT / "pages" / "overlays"


def _page(name: str) -> str:
    return (_OVERLAYS / f"{name}.html").read_text(encoding="utf-8")


def _cases() -> list[tuple[str, str, Locator]]:
    planned = d.planned_dialog("Car")
    fixed = d.recurring_dialog("Fixed Costs")
    formula = d.recurring_dialog("Taxes")
    occurrence = d.occurrence_dialog("Fixed Costs")
    removal = d.remove_dialog()
    return [
        ("edit-planned", "planned_dialog", planned),
        ("edit-planned", "hero_amount", d.hero_amount(planned)),
        ("edit-planned", "category_group", d.category_group(planned)),
        ("edit-planned", "category_choice", d.category_choice(planned, "Groceries")),
        ("edit-planned", "field_account", d.field_account(planned)),
        ("edit-planned", "field_due", d.field_due(planned)),
        ("edit-planned", "field_note", d.field_note(planned)),
        ("edit-planned", "save", d.save(planned)),
        ("edit-planned", "cancel", d.cancel(planned)),
        ("edit-recurring--fixed", "recurring_dialog", fixed),
        ("edit-recurring--fixed", "hero_amount", d.hero_amount(fixed)),
        ("edit-recurring--fixed", "field_start", d.field_start(fixed)),
        ("edit-recurring--fixed", "field_stop", d.field_stop(fixed)),
        ("edit-recurring--fixed", "field_day", d.field_day(fixed)),
        ("edit-recurring--fixed", "field_note", d.field_note(fixed)),
        ("edit-recurring--fixed", "amount_fixed", d.amount_fixed(fixed)),
        ("edit-recurring--fixed", "amount_formula", d.amount_formula(fixed)),
        ("edit-recurring--fixed", "cadence_group", d.cadence_group(fixed)),
        ("edit-recurring--fixed", "save_rule", d.save_rule(fixed)),
        ("edit-recurring--formula", "recurring_dialog", formula),
        ("edit-recurring--formula", "formula_group", d.formula_group(formula)),
        ("edit-recurring--empty", "recurring_dialog", formula),
        ("edit-recurring--incomplete", "recurring_dialog", formula),
        ("edit-recurring--picking", "recurring_dialog", formula),
        ("override--occurrence", "occurrence_dialog", occurrence),
        ("override--occurrence", "hero_amount", d.hero_amount(occurrence)),
        ("override--occurrence", "month_group", d.month_group(occurrence)),
        ("override--occurrence", "month_prev", d.month_prev(occurrence)),
        ("override--occurrence", "month_next", d.month_next(occurrence)),
        ("override--occurrence", "save", d.save(occurrence)),
        ("override--occurrence", "cancel", d.cancel(occurrence)),
        ("override--remove", "remove_dialog", removal),
        ("override--remove", "keep", d.keep(removal)),
        ("override--remove", "remove", d.remove(removal)),
    ]


@pytest.mark.parametrize(
    ("page", "name", "loc"), _cases(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_name_resolves_in_handoff(page: str, name: str, loc: Locator) -> None:
    assert _html.count(_page(page), loc) >= 1, f"{page}: {name}"


def test_routes_map_to_these_overlays() -> None:
    assert handoff_page("/planned/{planned_id}/edit").endswith("overlays/edit-planned.html")
    assert handoff_page("/recurring/{rule_id}/edit").endswith("edit-recurring--fixed.html")
    assert handoff_page("/recurring/{rule_id}/overrides/new").endswith("override--occurrence.html")
