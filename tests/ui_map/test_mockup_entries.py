"""Every ``entries`` name resolves against the handoff overlays (T-UT09, T-UR07b)."""

from __future__ import annotations

import pytest

from tests.ui_map import _html, entries as app_entries
from tests.ui_map.locator import Locator
from tests.ui_map.mockup import entries as mockup_entries
from tests.ui_map.mockup_routes import HANDOFF_ROOT
from tests.ui_map.target import surface

_OVERLAYS = HANDOFF_ROOT / "pages" / "overlays"


def _page(name: str) -> str:
    return (_OVERLAYS / f"{name}.html").read_text(encoding="utf-8")


# name -> (overlay page, resolves to this many elements at least)
_WHERE: dict[str, str] = {
    "dialog": "new-entry--happened",
    "tab_happened": "new-entry--happened",
    "tab_planned": "new-entry--happened",
    "tab_repeats": "new-entry--happened",
    "hero_amount": "new-entry--happened",
    "category_group": "new-entry--happened",
    "category_search": "new-entry--happened",
    "field_account": "new-entry--happened",
    "field_date": "new-entry--happened",
    "field_due": "new-entry--planned",
    "field_note": "new-entry--happened",
    "field_start": "new-entry--repeats-fixed",
    "field_stop": "new-entry--repeats-fixed",
    "field_day": "new-entry--repeats-fixed",
    "amount_fixed": "new-entry--repeats-fixed",
    "amount_formula": "new-entry--repeats-fixed",
    "cadence_group": "new-entry--repeats-fixed",
    "cadence_quarterly": "new-entry--repeats-fixed",
    "formula_group": "new-entry--repeats-formula",
    "save": "new-entry--happened",
    "cancel": "new-entry--happened",
    "alert": "new-entry--error",
    "promote_amount": "promote--planned",
    "promote_date": "promote--planned",
    "promote_note": "promote--planned",
    "promote_submit": "promote--recurring",
}


def _locators() -> list[tuple[str, Locator]]:
    return [
        (n, v)
        for n, v in sorted(vars(mockup_entries).items())
        if isinstance(v, Locator) and n not in mockup_entries.NO_HANDOFF_TWIN
    ]


def test_variant_defines_every_app_name() -> None:
    def names(module: object) -> set[str]:
        return {n for n, v in vars(module).items() if isinstance(v, Locator) or callable(v)}

    assert {n for n in names(app_entries) if not n.startswith("_")} <= names(mockup_entries)


def test_every_resolvable_name_has_a_page() -> None:
    assert {n for n, _ in _locators()} == set(_WHERE)


@pytest.mark.parametrize(
    ("name", "loc"), _locators(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_name_resolves_in_handoff(name: str, loc: Locator) -> None:
    assert _html.count(_page(_WHERE[name]), loc) >= 1, name


def test_builders_resolve_in_handoff() -> None:
    assert (
        _html.count(_page("new-entry--happened"), mockup_entries.category_option("Takeaway")) == 1
    )
    assert (
        _html.count(
            _page("promote--planned"), mockup_entries.promote_dialog("promote to actual · Car")
        )
        == 1
    )
    assert (
        _html.count(
            _page("promote--recurring"), mockup_entries.promote_dialog("promote · Fixed Costs")
        )
        == 1
    )


def test_surface_selects_by_target() -> None:
    assert surface("entries", "app") is app_entries
    assert surface("entries", "mockup") is mockup_entries
