"""Handoff visual references (T-UT10, ADR-0106 amends ADR-0027 section 4).

Serves the frozen designer handoff (``docs/design/rising-dough-frontend/``)
over a loopback HTTP server and screenshots every page at 1440 / 1024 / 375 in
light and dark. The images are the target the redesigned templates are compared
against; ``just visual-reference`` regenerates them, ``just test-visual
--reference=handoff <surface>`` compares.

Stdlib-only PNG diff (no Pillow dependency; a stack change needs an ADR).
"""

from __future__ import annotations

import http.server
import os
import struct
import sys
import threading
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from playwright.sync_api import Browser, sync_playwright

from tests.visual.overlay import overlay_handler

VISUAL_ROOT: Final = Path(__file__).parent
REPO_ROOT: Final = VISUAL_ROOT.parents[1]
HANDOFF_ROOT: Final = REPO_ROOT / "docs" / "design" / "rising-dough-frontend"
REFERENCE_DIR: Final = VISUAL_ROOT / "reference"
# Same day as the frozen server (conftest.FROZEN_DATE) and the handoff's sample
# data ("day 25 of 31", period 7 Oct -> 7 Nov, due today 31 Oct).
HANDOFF_FIXED_TIME: Final = "2026-10-31T10:00:00Z"  # == frozen_server.HANDOFF_FIXTURE_DATE

VIEWPORTS: Final = {"1440": (1440, 900), "1024": (1024, 768), "375": (375, 812)}
THEMES: Final = ("light", "dark")

# One strict tolerance for every app-vs-handoff comparison (ADR-0147 section 2): at most
# MAX_DIFF_PIXEL_RATIO of the pixels differ AND the largest 8-connected differing region is at
# most MAX_DIFF_CLUSTER_PX. Exceptions only via derived.md "Tolerance exceptions".
MAX_DIFF_PIXEL_RATIO: Final = 0.001
# provisional until calibrated from CI self-comparison (T-UR00b): twice the largest cluster
# seen in repeated handoff-vs-itself runs (``self-clusters.txt``).
MAX_DIFF_CLUSTER_PX: Final = 64
# Handoff-vs-itself uses ``SELF_TOLERANCE`` (noise floor).
SELF_TOLERANCE: Final = 0.0005  # raster noise floor: observed <= 0.022% under load, most pages 0

CHROMIUM_ARGS: Final = [
    "--disable-gpu",
    "--disable-lcd-text",
    "--font-render-hinting=none",
    "--disable-font-subpixel-positioning",
    "--force-color-profile=srgb",
    "--disable-skia-runtime-opts",
    # Single raster thread + full raster: removes sub-0.01% run-to-run noise.
    "--num-raster-threads=1",
    "--disable-partial-raster",
]
FREEZE_CSS: Final = """
*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
  scroll-behavior: auto !important;
}
"""


def pages() -> list[str]:
    """Handoff page paths relative to the handoff root (``pages/...html``)."""
    return sorted(
        p.relative_to(HANDOFF_ROOT).as_posix() for p in (HANDOFF_ROOT / "pages").rglob("*.html")
    )


def surface_of(page: str) -> str:
    """``pages/today--empty.html`` -> ``today``; ``pages/ledger/actual.html`` -> ``ledger``."""
    parts = Path(page).relative_to("pages").parts
    return parts[0] if len(parts) > 1 else parts[0].removesuffix(".html").split("--")[0]


def surfaces() -> list[str]:
    return sorted({surface_of(p) for p in pages()})


def reference_path(page: str, viewport: str, theme: str) -> Path:
    stem = Path(page).relative_to("pages").with_suffix("")
    return REFERENCE_DIR / stem.parent / f"{stem.name}.{viewport}.{theme}.png"


@contextmanager
def serve_handoff() -> Iterator[str]:
    """Serve the handoff (data overlay applied, ``overlay.py``) on a free loopback port."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), overlay_handler(HANDOFF_ROOT))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def shoot(browser: Browser, base: str, page: str, *, viewport: str, theme: str, out: Path) -> None:
    """Deterministic full-page screenshot of one handoff page into ``out``."""
    width, height = VIEWPORTS[viewport]
    context = browser.new_context(
        viewport={"width": width, "height": height},
        reduced_motion="reduce",
        color_scheme=theme,  # type: ignore[arg-type]
        device_scale_factor=1,
    )
    try:
        context.clock.set_fixed_time(HANDOFF_FIXED_TIME)
        pg = context.new_page()
        # ?theme= is theme.js's documented handoff-review override.
        pg.goto(f"{base}/{page}?theme={theme}", wait_until="networkidle", timeout=20000)
        pg.add_style_tag(content=FREEZE_CSS)
        pg.evaluate("document.fonts.ready.then(() => undefined)")
        pg.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        out.parent.mkdir(parents=True, exist_ok=True)
        pg.wait_for_timeout(150)
        pg.screenshot(path=str(out), full_page=True, animations="disabled", caret="hide")
    finally:
        context.close()


SHARD_ENV: Final = "REFERENCE_SHARD"  # "<viewport>:<theme>"; set by the CI matrix job


def parse_shard(shard: str | None) -> tuple[str, str] | None:
    """``"<viewport>:<theme>"`` (CI shard, T-UR00b) -> ``(viewport, theme)``; None = all."""
    if not shard:
        return None
    viewport, _, theme = shard.partition(":")
    if viewport not in VIEWPORTS or theme not in THEMES:
        raise ValueError(f"bad shard {shard!r}; expected <viewport>:<theme>, e.g. 1440:dark")
    return viewport, theme


def generate(only_surface: str | None = None, shard: str | None = None) -> int:
    """Render page x viewport x theme (or one surface / shard) into ``REFERENCE_DIR``."""
    only = parse_shard(shard or os.environ.get(SHARD_ENV))
    count = 0
    with serve_handoff() as base, sync_playwright() as p:
        browser = p.chromium.launch(args=CHROMIUM_ARGS)
        try:
            for page in pages():
                if only_surface and surface_of(page) != only_surface:
                    continue
                for viewport in VIEWPORTS:
                    for theme in THEMES:
                        if only and (viewport, theme) != only:
                            continue
                        shoot(
                            browser,
                            base,
                            page,
                            viewport=viewport,
                            theme=theme,
                            out=reference_path(page, viewport, theme),
                        )
                        count += 1
        finally:
            browser.close()
    return count


def _decode(path: Path) -> tuple[int, int, int, bytes]:
    """Minimal PNG decoder: 8-bit, non-interlaced. Returns width, height, channels, raw rows."""
    data = path.read_bytes()
    pos, idat, width, height, channels = 8, b"", 0, 0, 0
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos : pos + 8])
        body = data[pos + 8 : pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or interlace or ctype not in (2, 6):
                raise ValueError(f"unsupported PNG layout in {path}")
            channels = 3 if ctype == 2 else 4
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = width * channels
    out = bytearray()
    prev = bytearray(stride)
    for row in range(height):
        base = row * (stride + 1)
        ftype, line = raw[base], bytearray(raw[base + 1 : base + 1 + stride])
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = prev[i]
            c = prev[i - channels] if i >= channels else 0
            if ftype == 1:
                line[i] = (line[i] + a) & 255
            elif ftype == 2:
                line[i] = (line[i] + b) & 255
            elif ftype == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif ftype == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 255
        out += line
        prev = line
    return width, height, channels, bytes(out)


def diff_ratio(expected: Path, actual: Path) -> float:
    """Fraction of differing pixels; 1.0 when the sizes differ."""
    if expected.read_bytes() == actual.read_bytes():
        return 0.0
    w1, h1, c1, a = _decode(expected)
    w2, h2, c2, b = _decode(actual)
    if (w1, h1, c1) != (w2, h2, c2):
        return 1.0
    differing = sum(1 for i in range(0, len(a), c1) if a[i : i + c1] != b[i : i + c1])
    return differing / (w1 * h1)


Box = tuple[int, int, int, int]  # left, top, right, bottom (inclusive)


@dataclass(frozen=True)
class Comparison:
    """Result of comparing two screenshots (``size_mismatch``: ratio 1.0, no cluster)."""

    ratio: float
    cluster: int
    box: Box | None
    width: int
    height: int
    mask: bytes
    size_mismatch: bool = False


def largest_cluster(mask: bytes, width: int, height: int) -> tuple[int, Box | None]:
    """Size and bounding box of the largest 8-connected region of set cells in ``mask``."""
    seen = bytearray(len(mask))
    best, best_box = 0, None
    for start in range(len(mask)):
        if not mask[start] or seen[start]:
            continue
        seen[start] = 1
        stack = [start]
        size = 0
        left, top, right, bottom = width, height, 0, 0
        while stack:
            i = stack.pop()
            y, x = divmod(i, width)
            size += 1
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            for ny in range(max(y - 1, 0), min(y + 2, height)):
                row = ny * width
                for nx in range(max(x - 1, 0), min(x + 2, width)):
                    j = row + nx
                    if mask[j] and not seen[j]:
                        seen[j] = 1
                        stack.append(j)
        if size > best:
            best, best_box = size, (left, top, right, bottom)
    return best, best_box


def compare(expected: Path, actual: Path) -> Comparison:
    """Pixel ratio plus largest differing cluster of two same-size PNGs."""
    w1, h1, c1, a = _decode(expected)
    w2, h2, c2, b = _decode(actual)
    if (w1, h1, c1) != (w2, h2, c2):
        return Comparison(1.0, 0, None, w2, h2, b"", size_mismatch=True)
    mask = bytes(1 if a[i : i + c1] != b[i : i + c1] else 0 for i in range(0, len(a), c1))
    cluster, box = largest_cluster(mask, w1, h1)
    return Comparison(sum(mask) / (w1 * h1), cluster, box, w1, h1, mask)


def _png(width: int, height: int, rows: bytes) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    raw = b"".join(b"\x00" + rows[y * width * 3 : (y + 1) * width * 3] for y in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def write_diff_png(actual: Path, result: Comparison, out: Path) -> None:
    """Actual screenshot with differing pixels red and the largest cluster outlined in blue."""
    if result.size_mismatch:
        return
    w, h, c, data = _decode(actual)
    rgb = bytearray(w * h * 3)
    for i in range(w * h):
        px = data[i * c : i * c + 3]
        if result.mask[i]:
            px = b"\xff\x00\x00"
        rgb[i * 3 : i * 3 + 3] = px
    if result.box:
        left, top, right, bottom = result.box
        left, top = max(left - 2, 0), max(top - 2, 0)
        right, bottom = min(right + 2, w - 1), min(bottom + 2, h - 1)
        for x in range(left, right + 1):
            for y in (top, bottom):
                rgb[(y * w + x) * 3 : (y * w + x) * 3 + 3] = b"\x00\x00\xff"
        for y in range(top, bottom + 1):
            for x in (left, right):
                rgb[(y * w + x) * 3 : (y * w + x) * 3 + 3] = b"\x00\x00\xff"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(_png(w, h, bytes(rgb)))


def main(argv: list[str]) -> None:
    surface = argv[0] if argv else None
    if surface and surface not in surfaces():
        raise SystemExit(f"unknown surface {surface!r}; choose from {surfaces()}")
    written = generate(surface)
    print(f"[visual-reference] wrote {written} references into {REFERENCE_DIR}")


if __name__ == "__main__":
    main(sys.argv[1:])
