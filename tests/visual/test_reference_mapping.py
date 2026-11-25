"""Page-to-route and page-to-modifier mapping of the handoff reference run (T-UR00b, ADR-0147).

Unmarked on purpose: these run in the default suite (the ``visual`` marker is deselected there).
"""

from __future__ import annotations

from tests.visual import handoff, handoff_seed
from tests.visual.test_reference import (
    OVERLAY_DIALOGS,
    PAGE_MODIFIERS,
    UNMAPPED_OVERLAYS,
    modifiers_for,
    route_for,
)


def test_recurring_reference_uses_board_modifier() -> None:
    assert modifiers_for("pages/ledger/recurring.html") == ("recurring-board",)
    assert route_for("pages/ledger/recurring.html") == "/ledger?view=recurring"
    assert modifiers_for("pages/ledger/planned.html") == ()
    assert set(PAGE_MODIFIERS.values()) <= {(m,) for m in handoff_seed.MODIFIER_NAMES}


def test_every_overlay_page_is_mapped_or_listed_unmapped() -> None:
    overlays = {p for p in handoff.pages() if handoff.surface_of(p) == "overlays"}
    mapped = set(OVERLAY_DIALOGS)
    unmapped = {f"pages/overlays/{n}.html" for n in UNMAPPED_OVERLAYS}
    assert mapped | unmapped == overlays
    assert not mapped & unmapped
    for page in mapped:
        assert route_for(page).startswith("/add?dialog=1&when=")
    for page in unmapped:
        assert route_for(page) == "/today"
