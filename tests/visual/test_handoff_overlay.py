"""Guard and unit tests for the handoff data overlay (T-UR00b, ADR-0147 section 4)."""

from __future__ import annotations

import datetime as dt
import http.client
import json
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path

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
from tests.visual import handoff_seed
from tests.visual.overlay import (
    ABSENT_SETTABLE,
    ALLOWED_ATTRIBUTES,
    ALLOWED_CLASS_CHANGES,
    ALLOWED_CLASS_TOKENS,
    ANALYTICS_PAGE,
    APP_VALUES_SOURCE,
    GEOMETRY_ATTRIBUTES,
    GEOMETRY_SOURCES,
    HIDDEN_SETTABLE_CLASSES,
    OVERLAY_FILE,
    VALUE_SOURCES,
    OverlayError,
    Row,
    apply_rows,
    class_change_violation,
    delta_rows,
    kind_violation,
    load_rows,
    overlay_handler,
    overlay_page,
)

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
        if row.field == "hidden" and row.absent:
            pass  # kind_violation holds it to HIDDEN_SETTABLE_CLASSES
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
                and not (k == "hidden" and HIDDEN_SETTABLE_CLASSES & set(el.get("class") or []))
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


_HIDDEN = replace(
    _BASE, select=".rd-upcoming__promote-all", field="hidden", old="", value="hidden", absent=True
)


def test_hidden_row_sets_hidden_only_on_the_promote_all_form() -> None:
    html = '<form class="rd-upcoming__promote-all"><button>x</button></form>'
    assert row_violations(_HIDDEN) == []
    out = apply_rows("pages/p.html", html, [_HIDDEN])
    assert out == '<form class="rd-upcoming__promote-all" hidden="hidden"><button>x</button></form>'
    assert skeleton(out) == skeleton(html)
    assert row_violations(replace(_HIDDEN, select="form"))
    assert row_violations(replace(_HIDDEN, select=".rd-btn"))
    assert row_violations(replace(_HIDDEN, absent=False, old="x"))
    assert row_violations(replace(_HIDDEN, old="x"))
    assert skeleton('<p class="rd-btn" hidden>x</p>') != skeleton('<p class="rd-btn">x</p>')


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


def _values_toml(rows: tuple[Row, ...]) -> str:
    blocks = [VALUES_MARKER, ""]
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


if __name__ == "__main__":
    text = OVERLAY_FILE.read_text(encoding="utf-8")
    head = text.split(VALUES_MARKER)[0].rstrip("\n")
    OVERLAY_FILE.write_text(f"{head}\n\n{_values_toml(seed_value_rows())}", encoding="utf-8")
