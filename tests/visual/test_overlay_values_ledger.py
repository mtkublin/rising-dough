"""Drift test: the ledger board overlay rows equal what the board seeds and services produce.

T-UR00b (F2), ADR-0147 section 4: the recurring board lists twelve of the base seed's 24 rules
(modifier ``recurring-board``); its hero, tab count and formula amounts come from the services
over that seed, never from the handoff. The empty boards print the real zero totals.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.web import ledger_data, ledger_view
from budget_planner.web.ledger_types import LedgerFilters
from tests.visual import handoff_seed as seed
from tests.visual.frozen_server import HANDOFF_FIXTURE_DATE
from tests.visual.overlay import Row, load_rows

DAY = dt.date.fromisoformat(HANDOFF_FIXTURE_DATE)
MINUS = "−"
BOARD_PAGE = "pages/ledger/recurring.html"
ROWS = load_rows()


def _row(page: str, select_part: str, old: str) -> Row:
    (row,) = (
        r for r in ROWS if r.page == page and select_part in r.select and r.old == old
    )
    return row


def _context(tmp_path: Path, view: str, *modifiers: str) -> dict[str, object]:
    result = seed.build_seed(tmp_path / "ledger.sqlite", modifiers=modifiers)
    settings = Settings(_env_file=None, database_url=f"sqlite:///{result.db_path.as_posix()}")
    conn = get_connection(settings)
    try:
        return ledger_data.index_context(
            conn, seed.OWNER_ID, settings=settings, view=view, filters=LedgerFilters(), today=DAY
        )
    finally:
        conn.close()


def test_recurring_board_rows_carry_the_board_totals(tmp_path: Path) -> None:
    ctx = _context(tmp_path, "recurring", "recurring-board")
    hero = ctx["hero"]
    assert isinstance(hero, ledger_view.LedgerHero)
    assert hero.figure == f"{MINUS}7,894.97"
    assert hero.note == "in +19,551.34 · 12 rules · next due 01 nov"
    assert _row(BOARD_PAGE, "13,755.41", f"{MINUS}13,755.41").value == hero.figure
    assert _row(BOARD_PAGE, "27 rules", "in +23,253.18 · 27 rules · next due 01 nov").value == (
        hero.note
    )
    counts = ctx["tab_counts"]
    assert isinstance(counts, dict)
    tab = _row(BOARD_PAGE, "recurring 27", "recurring 27")
    assert tab.value == f"recurring {counts['recurring']}"


@pytest.mark.parametrize(
    ("page", "view", "modifier", "old", "value"),
    [
        ("pages/ledger/planned--empty.html", "planned", "empty-planned", f"{MINUS}1,531.35", "0.00"),
        ("pages/ledger/recurring--empty.html", "recurring", "empty-recurring", f"{MINUS}13,755.41", "0.00"),
    ],
)
def test_empty_board_hero_rows_print_the_real_zero(
    tmp_path: Path, page: str, view: str, modifier: str, old: str, value: str
) -> None:
    ctx = _context(tmp_path, view, modifier)
    hero = ctx["hero"]
    assert isinstance(hero, ledger_view.LedgerHero)
    assert hero.figure == value
    assert _row(page, ".rd-hero__figure", old).value == value
