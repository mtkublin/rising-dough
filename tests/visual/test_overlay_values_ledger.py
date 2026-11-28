"""Drift test: the ledger board overlay rows equal what the board seeds and services produce.

T-UR00b (F2), ADR-0147 section 4: the recurring board lists twelve of the base seed's 24 rules
(modifier ``recurring-board``); its hero, tab count and formula amounts come from the services
over that seed, never from the handoff. The empty boards print the real zero totals.
"""

from __future__ import annotations

import datetime as dt
import urllib.request
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.web import ledger_data, ledger_view
from budget_planner.web.auth_cookies import SESSION_DEV_COOKIE_NAME
from budget_planner.web.ledger_types import LedgerFilters, ViewKind
from tests.visual import handoff_seed as seed
from tests.visual.conftest import serve_db
from tests.visual.frozen_server import HANDOFF_FIXTURE_DATE
from tests.visual.handoff_openers import opener_url
from tests.visual.overlay import Row, load_rows

DAY = dt.date.fromisoformat(HANDOFF_FIXTURE_DATE)
MINUS = "\N{MINUS SIGN}"
BOARD_PAGE = "pages/ledger/recurring.html"
ROWS = load_rows()


def _row(page: str, select_part: str, old: str) -> Row:
    (row,) = (r for r in ROWS if r.page == page and select_part in r.select and r.old == old)
    return row


def _context(tmp_path: Path, view: ViewKind, *modifiers: str) -> dict[str, object]:
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
    ("page", "view", "modifier", "old"),
    [
        ("pages/ledger/planned--empty.html", "planned", "empty-planned", f"{MINUS}1,531.35"),
        ("pages/ledger/recurring--empty.html", "recurring", "empty-recurring", f"{MINUS}13,755.41"),
    ],
)
def test_empty_board_hero_rows_print_the_real_zero(
    tmp_path: Path, page: str, view: ViewKind, modifier: str, old: str
) -> None:
    ctx = _context(tmp_path, view, modifier)
    hero = ctx["hero"]
    assert isinstance(hero, ledger_view.LedgerHero)
    assert hero.figure == "0.00"
    assert _row(page, ".rd-hero__figure", old).value == "0.00"


def test_edit_recurring_formula_rows_carry_the_served_dialog_figure(tmp_path: Path) -> None:
    """The Taxes edit dialog's hero and result are the figure the overlay rows print."""
    built = seed.build_seed(tmp_path / "dialog.sqlite", modifiers=("recurring-board",))
    settings = Settings(_env_file=None, database_url=f"sqlite:///{built.db_path.as_posix()}")
    page = "pages/overlays/edit-recurring--formula.html"
    conn = get_connection(settings)
    try:
        url = opener_url(page, conn)
    finally:
        conn.close()
    assert url is not None
    hero = _row(page, "rd-dialog__amount--static", "1,836.93")
    result_row = _row(page, "rd-formula__result", "\u2192 next amount 1,836.93 PLN")
    with serve_db(built.db_path) as base:
        request = urllib.request.Request(  # noqa: S310 — the scratch server on loopback
            f"{base}{url}",
            headers={
                "Cookie": f"{SESSION_DEV_COOKIE_NAME}={built.session_token}",
                "HX-Request": "true",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 — as above
            html = response.read().decode()
    dialog = BeautifulSoup(html, "html.parser").select_one("dialog")
    assert dialog is not None
    figure = dialog.select_one(".rd-dialog__amount--static")
    note = dialog.select_one(".rd-formula__result")
    assert figure is not None
    assert note is not None
    assert figure.get_text(strip=True) == hero.value == "3,002.00"
    assert note.get_text(strip=True) == result_row.value == "\u2192 next amount 3,002.00 PLN"
