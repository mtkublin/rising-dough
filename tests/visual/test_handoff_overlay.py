"""Guard and unit tests for the handoff data overlay (T-UR00b, ADR-0147 section 4)."""

from __future__ import annotations

import http.client
import shutil
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag

from tests.visual.overlay import (
    ALLOWED_ATTRIBUTES,
    GEOMETRY_ATTRIBUTES,
    GEOMETRY_SOURCES,
    OverlayError,
    Row,
    apply_rows,
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
    if row.field != "text" and row.field not in ALLOWED_ATTRIBUTES:
        if row.field in GEOMETRY_ATTRIBUTES:
            if row.source != "geometry" or row.source not in GEOMETRY_SOURCES:
                found.append(f"geometry attribute {row.field!r} needs a generated geometry source")
        else:
            found.append(f"field {row.field!r} is not allowed")
    if row.source and row.source not in GEOMETRY_SOURCES:
        found.append(f"source {row.source!r} has no generator yet")
    if not row.page.startswith("pages/") or not row.page.endswith(".html"):
        found.append("page must be a handoff HTML page glob")
    if row.old == row.value:
        found.append("old equals value")
    return found


def skeleton(html: str) -> list[tuple[object, ...]]:
    """Tags in order with every attribute except the allowed value ones; script/style bodies."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[object, ...]] = []
    for el in soup.find_all(True):
        assert isinstance(el, Tag)
        attrs = tuple(
            sorted((k, str(v)) for k, v in el.attrs.items() if k not in ALLOWED_ATTRIBUTES)
        )
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


def test_red_class_row_is_refused() -> None:
    assert row_violations(replace(_BASE, field="class")) == ["field 'class' is not allowed"]


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
