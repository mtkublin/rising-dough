"""Guard and unit tests for the handoff data overlay (T-UR00b, ADR-0147 section 4)."""

from __future__ import annotations

import datetime as dt
import functools
import http.client
import json
import shutil
import sqlite3
import subprocess
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup, Tag

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.services import (
    analytics as analytics_service,
    budget as budget_service,
    categories as categories_service,
    fx as fx_service,
)
from budget_planner.web import plan_views
from budget_planner.web.auth_cookies import SESSION_DEV_COOKIE_NAME
from tests.visual import handoff_seed
from tests.visual.conftest import serve_db
from tests.visual.handoff_openers import opener_url
from tests.visual.handoff_recurring import state_opener_url
from tests.visual.overlay import (
    ABSENT_SETTABLE,
    ALLOWED_ATTRIBUTES,
    ALLOWED_CLASS_CHANGES,
    ALLOWED_CLASS_TOKENS,
    ANALYTICS_PAGE,
    APP_CHIPS_SOURCE,
    APP_VALUES_SOURCE,
    CHIP_ATTRIBUTES,
    CHIP_PRESET_NAMES,
    CHIP_ROW,
    GEOMETRY_ATTRIBUTES,
    GEOMETRY_SOURCES,
    OVERLAY_FILE,
    VALUE_SOURCES,
    OverlayError,
    Row,
    apply_rows,
    chip_rows,
    chip_violation,
    class_change_violation,
    delta_rows,
    kind_violation,
    load_rows,
    overlay_handler,
    overlay_page,
)
from tests.visual.test_reference import OVERLAY_DIALOGS, modifiers_for

REPO_ROOT = Path(__file__).resolve().parents[2]
HANDOFF = REPO_ROOT / "docs" / "design" / "rising-dough-frontend"
PAGES = sorted(p.relative_to(HANDOFF).as_posix() for p in (HANDOFF / "pages").rglob("*.html"))
ROWS = load_rows()

_BASE = Row(page="pages/p.html", select="b", field="text", old="x", value="y", reason="test")
_HTML = '<p class="a" id="i"><b>x</b> <i title="t">z</i></p>'


def row_violations(row: Row) -> list[str]:
    """Why a row breaks the ADR-0147 section 4 rules (empty = fine)."""
    found: list[str] = []
    if not row.reason.strip():
        found.append("no reason")
    if row.field not in {"text", "class"} and row.field not in ALLOWED_ATTRIBUTES:
        if row.field in CHIP_ATTRIBUTES:
            if row.source != APP_CHIPS_SOURCE:
                found.append(f"{row.field!r} needs an {APP_CHIPS_SOURCE!r} row")
        elif row.field in GEOMETRY_ATTRIBUTES:
            if row.source != "geometry" or row.source not in GEOMETRY_SOURCES:
                found.append(f"geometry attribute {row.field!r} needs a generated geometry source")
        else:
            found.append(f"field {row.field!r} is not allowed")
    if row.source == APP_VALUES_SOURCE and row.field != "text":
        found.append("an app-values row changes text only")
    if row.source and row.source not in GEOMETRY_SOURCES | VALUE_SOURCES:
        found.append(f"source {row.source!r} has no generator yet")
    if not row.page.startswith("pages/") or not row.page.endswith(".html"):
        found.append("page must be a handoff HTML page glob")
    if message := kind_violation(row):
        found.append(message)
    if row.old == row.value:
        found.append("old equals value")
    return found


def _is_recent_chip(el: Tag) -> bool:
    return (
        el.name == "label"
        and el.select_one("input") is not None
        and el.parent is not None
        and ("rd-catfield__recent" in (el.parent.get("class") or []))
    )


def _plain(name: str, value: object) -> str:
    """Attribute value for the skeleton: reviewed class tokens dropped, nothing else."""
    if name == "class" and isinstance(value, list):
        return str([t for t in value if t not in ALLOWED_CLASS_TOKENS])
    return str(value)


def skeleton(html: str) -> list[tuple[object, ...]]:
    """Tags in order, attributes except the allowed value and geometry ones; script/style bodies."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[object, ...]] = []
    for el in soup.find_all(True):
        assert isinstance(el, Tag)
        attrs = tuple(
            sorted(
                (k, _plain(k, v))
                for k, v in el.attrs.items()
                if k not in ALLOWED_ATTRIBUTES
                and k not in GEOMETRY_ATTRIBUTES
                and not (k in CHIP_ATTRIBUTES and _is_recent_chip(el))
            )
        )  # geometry: generated rows only; reviewed class tokens ignored
        body = el.get_text() if el.name in ("script", "style") else ""
        out.append((el.name, attrs, body))
    return out


# --- guard over the committed overlay ------------------------------------------------


def test_overlay_has_rows() -> None:
    assert len(ROWS) >= 10


@pytest.mark.parametrize("row", ROWS, ids=lambda r: f"{r.page}:{r.select}"[:90])
def test_row_follows_the_rules(row: Row) -> None:
    assert row_violations(row) == []


def test_every_row_matches_a_vendored_page() -> None:
    pages = set(PAGES)
    for row in ROWS:
        assert any(row.applies_to(p) for p in pages), f"{row.page} matches no handoff page"


def test_overlay_changes_only_text_and_allowed_attributes() -> None:
    changed = 0
    used: set[int] = set()
    for page in PAGES:
        todo = [r for r in ROWS if r.applies_to(page)]
        if not todo:
            continue
        pristine = (HANDOFF / page).read_text(encoding="utf-8")
        overlaid = apply_rows(page, pristine, ROWS)  # raises on a stale or ambiguous row
        assert skeleton(overlaid) == skeleton(pristine), page
        changed += overlaid != pristine
        for i, row in enumerate(ROWS):
            if row.applies_to(page) and BeautifulSoup(pristine, "html.parser").select(row.select):
                used.add(i)
    assert changed > 90
    assert used == set(range(len(ROWS))), "a row matches no page (stale)"


def test_no_stale_today_key_after_overlay() -> None:
    for page in PAGES:
        html = overlay_page(page, (HANDOFF / page).read_text(encoding="utf-8"))
        assert 'aria-keyshortcuts="g o"' not in html, page
        assert ">g o<" not in html, page


def test_vendored_handoff_is_untouched() -> None:
    done = subprocess.run(  # noqa: S603 - fixed argv, no user input
        [
            shutil.which("git") or "git",
            "diff",
            "--quiet",
            "HEAD",
            "--",
            "docs/design/rising-dough-frontend",
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    assert done.returncode == 0


# --- the guard bites -----------------------------------------------------------------


_CLASS = replace(
    _BASE,
    select="p",
    field="class",
    old="a rd-fc__net--negative",
    value="a",
)
_CLASS_HTML = '<p class="a rd-fc__net--negative">x</p>'
_ABSENT = replace(_BASE, select="input", field="value", old="", value="pizza", absent=True)


def test_red_class_row_with_a_disallowed_token_pair_is_refused() -> None:
    assert row_violations(_CLASS) == []
    assert row_violations(replace(_CLASS, old="a hidden", value="a"))
    assert row_violations(replace(_CLASS, old="a", value="a rd-fc__net--negative"))
    assert row_violations(replace(_CLASS, old="a b", value="c d"))
    assert "not in ALLOWED_CLASS_CHANGES" in class_change_violation("a b", "a c")
    assert "more than one token" in class_change_violation("a b c", "a")
    with pytest.raises(OverlayError, match="ALLOWED_CLASS_CHANGES"):
        apply_rows("pages/p.html", '<p class="a hidden">x</p>', [replace(_CLASS, old="a hidden")])


def test_class_row_replaces_exactly_the_allowed_token() -> None:
    assert apply_rows("pages/p.html", _CLASS_HTML, [_CLASS]) == '<p class="a">x</p>'
    assert {("rd-fc__net--negative", "")} == ALLOWED_CLASS_CHANGES


def test_stale_class_row_is_an_error() -> None:
    with pytest.raises(OverlayError, match="class='a'"):
        apply_rows("pages/p.html", '<p class="a">x</p>', [_CLASS])
    with pytest.raises(OverlayError, match="matched 0"):
        apply_rows("pages/p.html", "<i>x</i>", [_CLASS])


def test_skeleton_ignores_only_the_allowed_class_token() -> None:
    assert skeleton(_CLASS_HTML) == skeleton('<p class="a">x</p>')
    assert skeleton(_CLASS_HTML) != skeleton('<p class="b">x</p>')


def test_absent_row_sets_a_missing_text_attribute() -> None:
    assert row_violations(_ABSENT) == []
    out = apply_rows("pages/p.html", '<input id="q">', [_ABSENT])
    assert out == '<input id="q" value="pizza"/>'
    assert skeleton(out) == skeleton('<input id="q">')


def test_absent_row_refuses_other_attributes_and_stale_state() -> None:
    assert {"value", "placeholder"} == ABSENT_SETTABLE
    assert row_violations(replace(_ABSENT, field="title"))
    assert row_violations(replace(_ABSENT, field="id"))
    assert row_violations(replace(_ABSENT, old="x"))
    assert row_violations(replace(_CLASS, absent=True))
    with pytest.raises(OverlayError, match="expected it absent"):
        apply_rows("pages/p.html", '<input value="a">', [_ABSENT])
    with pytest.raises(OverlayError, match="cannot be created"):
        apply_rows("pages/p.html", "<input>", [replace(_ABSENT, field="id")])


def test_red_style_and_id_rows_are_refused() -> None:
    assert row_violations(replace(_BASE, field="style"))
    assert row_violations(replace(_BASE, field="id"))


def test_red_geometry_row_needs_the_registered_generator_source() -> None:
    assert row_violations(replace(_BASE, field="points", source="geometry")) == []
    assert row_violations(replace(_BASE, field="points"))
    assert row_violations(replace(_BASE, field="points", source="hand-written"))
    assert row_violations(replace(_BASE, source="hand-written"))


def test_red_row_without_reason_or_non_html_page() -> None:
    assert row_violations(replace(_BASE, reason=" ")) == ["no reason"]
    assert row_violations(replace(_BASE, page="static/css/tokens.css"))


def test_skeleton_catches_class_tag_and_script_edits() -> None:
    base = skeleton(_HTML)
    assert skeleton(_HTML.replace('class="a"', 'class="b"')) != base
    assert skeleton(_HTML.replace("<b>x</b>", "<u>x</u>")) != base
    assert skeleton("<script>a</script>") != skeleton("<script>b</script>")
    assert skeleton(_HTML.replace("<b>x</b>", "<b>other</b>")) == base
    assert skeleton(_HTML.replace('title="t"', 'title="u"')) == base


# --- apply ---------------------------------------------------------------------------


def test_apply_replaces_text() -> None:
    out = apply_rows("pages/p.html", _HTML, [_BASE])
    assert out == '<p class="a" id="i"><b>y</b> <i title="t">z</i></p>'


def test_apply_replaces_attribute() -> None:
    row = replace(_BASE, select="i", field="title", old="t", value="u")
    assert apply_rows("pages/p.html", _HTML, [row]) == (
        '<p class="a" id="i"><b>x</b> <i title="u">z</i></p>'
    )


def test_apply_leaves_other_pages_untouched() -> None:
    assert apply_rows("pages/other.html", _HTML, [_BASE]) is _HTML


def test_apply_zero_match_is_an_error() -> None:
    with pytest.raises(OverlayError, match="matched 0"):
        apply_rows("pages/p.html", _HTML, [replace(_BASE, select="u")])


def test_apply_multiple_match_is_an_error() -> None:
    with pytest.raises(OverlayError, match="matched 2"):
        apply_rows("pages/p.html", "<b>x</b><b>x</b>", [_BASE])
    assert (
        apply_rows("pages/p.html", "<b>x</b><b>x</b>", [replace(_BASE, count=2)])
        == "<b>y</b><b>y</b>"
    )


def test_apply_stale_old_is_an_error() -> None:
    with pytest.raises(OverlayError, match="text nodes"):
        apply_rows("pages/p.html", _HTML, [replace(_BASE, old="other")])
    with pytest.raises(OverlayError, match="expected 'zz'"):
        apply_rows("pages/p.html", _HTML, [replace(_BASE, select="i", field="title", old="zz")])


def test_optional_row_skips_pages_without_the_element() -> None:
    assert (
        apply_rows("pages/p.html", "<p>none</p>", [replace(_BASE, optional=True)]) == "<p>none</p>"
    )


# --- serve ---------------------------------------------------------------------------


@contextmanager
def _served() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), overlay_handler(HANDOFF))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get(base: str, path: str) -> bytes:
    host, port = base.removeprefix("http://").split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=10)
    try:
        conn.request("GET", path)
        return conn.getresponse().read()
    finally:
        conn.close()


def test_serve_returns_the_overlaid_page_and_static_files_as_is() -> None:
    with _served() as base:
        page = _get(base, "/pages/today--afford-over.html?theme=dark")
        css = _get(base, "/static/css/tokens.css")
    text = page.decode()
    assert f"{chr(0x2212)}116.01 {chr(0xB7)} 812.07 over" in text
    assert "114.20" not in text
    assert 'aria-keyshortcuts="g t"' in text
    assert css == (HANDOFF / "static/css/tokens.css").read_bytes()
    assert "114.20 over" in (HANDOFF / "pages/today--afford-over.html").read_text(encoding="utf-8")


# --- generated app-value rows: Plan · analytics "vs 12-mo avg" (ADR-0147 amendment) -------

DAY = dt.date(2026, 10, 31)
VALUES_MARKER = "# --- generated app-value rows (do not edit; regenerate, see below) ---"
VALUES_REASON = (
    "the handoff board's 12-month averages cannot be reproduced by the fixed 42-entry seed "
    "(its own chart implies different totals); the app computes the delta from the seed history"
)
REGENERATE = "uv run python -m tests.visual.test_handoff_overlay"
ANALYTICS_HTML = (HANDOFF / ANALYTICS_PAGE).read_text(encoding="utf-8")


def seed_deltas() -> tuple[tuple[str, bool], ...]:
    """The app's ``(delta_text, delta_down)`` per spend row, run over the base seed."""
    with tempfile.TemporaryDirectory() as tmp:
        result = handoff_seed.build_seed(Path(tmp) / "base.sqlite")
        settings = Settings(_env_file=None, database_url=f"sqlite:///{result.db_path.as_posix()}")
        conn = get_connection(settings)
        try:
            user = handoff_seed.OWNER_ID
            picked = budget_service.resolve_picker_month(
                conn, user, DAY, year_raw=None, month_raw=None
            )
            bundle = analytics_service.bundle(
                conn,
                user,
                fx_service.converter_for(conn, settings, DAY),
                today=analytics_service.reference_today(DAY, picked.year, picked.month),
                period=analytics_service.normalize_period(None),
            )
            colors = {
                c.id: c.color for c in categories_service.list_all(conn, user, include_deleted=True)
            }
        finally:
            conn.close()
    view = plan_views.analytics_page(bundle, picked, colors, settings.base_currency)
    return tuple((r.delta_text, r.delta_down) for r in view.rows)


def seed_value_rows() -> tuple[Row, ...]:
    return delta_rows(ANALYTICS_HTML, seed_deltas(), reason=VALUES_REASON)


def _values_toml(rows: tuple[Row, ...], marker: str = VALUES_MARKER) -> str:
    blocks = [marker, ""]
    for r in rows:
        blocks += [
            "[[row]]",
            *(
                f"{key} = {json.dumps(getattr(r, key), ensure_ascii=False)}"
                for key in ("page", "select", "field", "old", "value", "reason", "source")
            ),
            "",
        ]
    return "\n".join(blocks)


def test_committed_app_value_rows_equal_the_generated_rows() -> None:
    committed = tuple(r for r in ROWS if r.source == APP_VALUES_SOURCE)
    generated = seed_value_rows()
    assert generated, "no app-value rows generated"
    assert committed == generated, f"stale app-value rows; regenerate with: {REGENERATE}"


def test_app_value_rows_make_the_handoff_deltas_equal_the_app() -> None:
    applied = apply_rows(ANALYTICS_PAGE, ANALYTICS_HTML, ROWS)
    cells = BeautifulSoup(applied, "html.parser").select("tr.rd-row--spend .rd-spend__delta")
    assert [c.get_text() for c in cells] == [t for t, _ in seed_deltas()]
    assert delta_rows(applied, seed_deltas(), reason="x") == ()


def test_delta_rows_refuse_an_up_down_or_count_mismatch() -> None:
    html = (
        '<table><tr class="rd-row--spend"><td class="rd-spend__delta rd-num">▲ +1.00</td></tr>'
        '<tr class="rd-row--spend"><td class="rd-spend__delta rd-num rd-spend__delta--down">'
        "▼ \u22122.00</td></tr></table>"
    )
    rows = delta_rows(html, [("▲ +5.00", False), ("▼ \u22122.00", True)], reason="r")
    assert [(r.select, r.old, r.value, r.source) for r in rows] == [
        ("tr.rd-row--spend:nth-of-type(1) .rd-spend__delta", "▲ +1.00", "▲ +5.00", "app-values")
    ]
    with pytest.raises(OverlayError, match="up/down"):
        delta_rows(html, [("▲ +5.00", False), ("▲ +1.00", False)], reason="r")
    with pytest.raises(OverlayError, match="2 spend rows, the app has 1"):
        delta_rows(html, [("▲ +5.00", False)], reason="r")


def test_red_app_values_row_is_text_only() -> None:
    row = replace(_BASE, source=APP_VALUES_SOURCE)
    assert row_violations(row) == []
    assert row_violations(replace(row, field="title"))


# --- generated chip rows: the dialogs' "recent categories" (ADR-0147 amendment, O2) -------

CHIPS_MARKER = "# --- generated recent-chip rows (do not edit; regenerate, see above) ---"
CHIPS_REASON = (
    "the handoff's recent chips cannot be produced by its own ledger data (Big Purchases and "
    "Entertainment used on 30 Oct but absent; Transport not on the board); the app derives them "
    "from the seed history (documented last-used rule)"
)
# Overlay pages whose dialog is the new-entry dialog the browser recipes start from.
NEW_ENTRY_DIALOGS = {
    "pages/overlays/category-picker.html": "/add?when=happened",
    "pages/overlays/category-picker--no-match.html": "/add?when=happened",
    "pages/overlays/new-entry--error.html": "/add?when=happened",
    "pages/overlays/new-entry--over-limit.html": "/add?when=happened",
    "pages/overlays/new-entry--repeats-formula.html": "/add?when=repeats",
}
Chip = tuple[str, str | None, bool]


def chip_pages() -> tuple[str, ...]:
    return tuple(
        p
        for p in PAGES
        if BeautifulSoup((HANDOFF / p).read_text(encoding="utf-8"), "html.parser").select(CHIP_ROW)
    )


def _dialog_url(page: str, conn: sqlite3.Connection) -> str:
    url = (
        OVERLAY_DIALOGS.get(page)
        or NEW_ENTRY_DIALOGS.get(page)
        or state_opener_url(page, conn)
        or opener_url(page, conn)
    )
    assert url, f"{page}: no app dialog route"
    return url


def app_chips(html: str) -> tuple[Chip, ...]:
    """The app dialog's recent chips: (name, preset, checked) in order."""
    out: list[Chip] = []
    for label in BeautifulSoup(html, "html.parser").select(CHIP_ROW):
        color = label.get("data-color")
        radio = label.select_one("input")
        assert radio is not None
        out.append(
            (label.get_text(), color if isinstance(color, str) else None, radio.has_attr("checked"))
        )
    return tuple(out)


@functools.cache
def seed_chips() -> dict[str, tuple[Chip, ...]]:
    """The app's recent chips for every chip page, from the dialog it serves over the seed."""
    groups: dict[tuple[str, ...], list[str]] = {}
    for page in chip_pages():
        groups.setdefault(tuple(modifiers_for(page)), []).append(page)
    found: dict[str, tuple[Chip, ...]] = {}
    for modifiers, members in groups.items():
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "chips.sqlite"
            token = handoff_seed.build_seed(db, modifiers=modifiers).session_token
            settings = Settings(_env_file=None, database_url=f"sqlite:///{db.as_posix()}")
            conn = get_connection(settings)
            try:
                urls = {p: _dialog_url(p, conn) for p in members}
            finally:
                conn.close()
            with serve_db(db) as base:
                cookies = {SESSION_DEV_COOKIE_NAME: token}
                for page, url in urls.items():
                    got = httpx.get(f"{base}{url}", cookies=cookies, headers={"HX-Request": "true"})
                    got.raise_for_status()
                    found[page] = app_chips(got.text)
    return found


def seed_chip_rows() -> tuple[Row, ...]:
    chips = seed_chips()
    rows: list[Row] = []
    for page in chip_pages():
        html = (HANDOFF / page).read_text(encoding="utf-8")
        rows += chip_rows(page, html, chips[page], reason=CHIPS_REASON)
    return tuple(rows)


def test_chip_pages_are_the_eighteen_overlays_with_a_recent_row() -> None:
    pages = chip_pages()
    assert len(pages) == 18
    assert all(p.startswith("pages/overlays/") for p in pages)


def test_committed_chip_rows_equal_the_generated_rows() -> None:
    committed = tuple(r for r in ROWS if r.source == APP_CHIPS_SOURCE)
    generated = seed_chip_rows()
    assert generated, "no chip rows generated"
    assert committed == generated, f"stale chip rows; regenerate with: {REGENERATE}"


def test_chip_rows_make_every_recent_row_equal_the_app() -> None:
    chips = seed_chips()
    for page in chip_pages():
        html = (HANDOFF / page).read_text(encoding="utf-8")
        applied = apply_rows(page, html, ROWS)
        assert chip_rows(page, applied, chips[page], reason="x") == (), page


def test_chip_rows_keep_checked_and_the_chip_count() -> None:
    for page in chip_pages():
        html = (HANDOFF / page).read_text(encoding="utf-8")
        before = BeautifulSoup(html, "html.parser").select(f"{CHIP_ROW} input")
        after = BeautifulSoup(apply_rows(page, html, ROWS), "html.parser").select(
            f"{CHIP_ROW} input"
        )
        assert [i.has_attr("checked") for i in before] == [i.has_attr("checked") for i in after]
        assert len(before) == 4


def test_committed_chip_rows_only_touch_chip_text_value_and_preset() -> None:
    rows = [r for r in ROWS if r.source == APP_CHIPS_SOURCE]
    assert {r.field for r in rows} == {"text", "value", "data-color"}
    for r in rows:
        assert chip_violation(r) == "", r
        assert r.reason == CHIPS_REASON
        assert (r.old in CHIP_PRESET_NAMES) == (r.field == "data-color")


_CHIP_HTML = (
    '<div class="rd-catfield__recent"><span>recent</span>'
    '<label class="rd-chip-option" data-color="orange"><input type="radio" name="category" '
    'value="Takeaway" checked>Takeaway</label>'
    '<label class="rd-chip-option" data-color="lime"><input type="radio" name="category" '
    'value="Groceries">Groceries</label></div>'
)


def test_chip_rows_rewrite_text_value_and_preset_only() -> None:
    chips = [("Takeaway", "orange", True), ("Big Purchases", "cyan", False)]
    rows = chip_rows("pages/p.html", _CHIP_HTML, chips, reason="r")
    assert [(r.select.split(":nth-of-type")[1], r.field, r.old, r.value) for r in rows] == [
        ("(2)", "text", "Groceries", "Big Purchases"),
        ("(2) input", "value", "Groceries", "Big Purchases"),
        ("(2)", "data-color", "lime", "cyan"),
    ]
    out = apply_rows("pages/p.html", _CHIP_HTML, rows)
    assert skeleton(out) == skeleton(_CHIP_HTML)
    assert 'data-color="cyan"' in out
    assert 'value="Big Purchases"' in out
    assert "checked" in out


def test_chip_rows_refuse_a_count_preset_or_checked_difference() -> None:
    first = ("Takeaway", "orange", True)
    with pytest.raises(OverlayError, match="2 recent chips, the app has 1"):
        chip_rows("pages/p.html", _CHIP_HTML, [first], reason="r")
    with pytest.raises(OverlayError, match="preset on one side only"):
        chip_rows("pages/p.html", _CHIP_HTML, [first, ("Groceries", None, False)], reason="r")
    with pytest.raises(OverlayError, match="checked in the app only"):
        chip_rows("pages/p.html", _CHIP_HTML, [first, ("Groceries", "lime", True)], reason="r")


def test_red_chip_rows_are_limited_to_chip_text_value_and_preset_names() -> None:
    row = Row(
        "pages/p.html",
        f"{CHIP_ROW}:nth-of-type(1)",
        "data-color",
        "orange",
        "cyan",
        "r",
        source=APP_CHIPS_SOURCE,
    )
    assert row_violations(row) == []
    assert row_violations(replace(row, source=""))  # data-color needs the generated source
    assert row_violations(replace(row, value="not-a-preset"))
    assert row_violations(replace(row, select="label.rd-chip-option:nth-of-type(1)"))
    assert row_violations(replace(row, select=f"{CHIP_ROW}:nth-of-type(1) input"))
    assert row_violations(replace(row, field="checked", old="", value="checked"))
    assert row_violations(replace(row, field="class", old="a", value="a b"))
    assert row_violations(replace(row, field="text", old="x", value="y", absent=True))
    assert row_violations(replace(row, select="p", field="text", old="x", value="y"))
    with pytest.raises(OverlayError, match="app-chips"):
        apply_rows("pages/p.html", _CHIP_HTML, [replace(row, source="")])


if __name__ == "__main__":
    text = OVERLAY_FILE.read_text(encoding="utf-8")
    head = text.split(VALUES_MARKER)[0].rstrip("\n")
    values = _values_toml(seed_value_rows())
    chips_block = _values_toml(seed_chip_rows(), CHIPS_MARKER)
    OVERLAY_FILE.write_text(f"{head}\n\n{values}\n{chips_block}", encoding="utf-8")
