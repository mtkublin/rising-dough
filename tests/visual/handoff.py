"""Handoff visual references (T-UT10, ADR-0106 amends ADR-0027 section 4).

Serves the frozen designer handoff (``docs/design/rising-dough-frontend/``)
over a loopback HTTP server and screenshots every page at 1440 / 1024 / 375 in
light and dark. The images are the target the redesigned templates are compared
against (retired comparison, T-UR65); ``just visual-reference`` regenerates them.

PNG decode via Pillow (dev-only dependency, ADR-0153); the diff itself is stdlib.
"""

from __future__ import annotations

import http.server
import struct
import sys
import threading
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image
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
# 2 x 26 px: the largest handoff-vs-itself cluster in visual.yml runs
# 45496302019, 45496318944 and 45498452834 of 2026-11-24 (T-UR00b, ADR-0147 section 2).
MAX_DIFF_CLUSTER_PX: Final = 52
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


def generate(only_surface: str | None = None) -> int:
    """Render page x viewport x theme (or one surface) into ``REFERENCE_DIR``."""
    count = 0
    with serve_handoff() as base, sync_playwright() as p:
        browser = p.chromium.launch(args=CHROMIUM_ARGS)
        try:
            for page in pages():
                if only_surface and surface_of(page) != only_surface:
                    continue
                for viewport in VIEWPORTS:
                    for theme in THEMES:
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
    """Decode an 8-bit RGB or RGBA PNG. Returns width, height, channels, raw interleaved bytes."""
    with Image.open(path) as image:
        if image.mode not in ("RGB", "RGBA") or image.info.get("interlace"):
            raise ValueError(f"unsupported PNG layout in {path}")
        channels = 3 if image.mode == "RGB" else 4
        return image.width, image.height, channels, image.tobytes()


def diff_ratio(expected: Path, actual: Path) -> float:
    """Fraction of differing pixels; 1.0 when the sizes differ."""
    if expected.read_bytes() == actual.read_bytes():
        return 0.0
    w1, h1, c1, a = _decode(expected)
    w2, h2, c2, b = _decode(actual)
    if (w1, h1) == (w2, h2) and c1 != c2:
        a, b, c1 = _rgb_crop(a, (w1, h1, c1), w1, h1), _rgb_crop(b, (w2, h2, c2), w2, h2), 3
    elif (w1, h1, c1) != (w2, h2, c2):
        return 1.0
    differing = sum(1 for i in range(0, len(a), c1) if a[i : i + c1] != b[i : i + c1])
    return differing / (w1 * h1)


Box = tuple[int, int, int, int]  # left, top, right, bottom (inclusive)


@dataclass(frozen=True)
class Comparison:
    """Result of comparing two screenshots.

    ``cluster`` is -1 when not computed (ratio already over the limit or a size mismatch)
    and ``cap + 1`` when the scan stopped early on a cluster above ``cluster_cap``.
    """

    ratio: float
    cluster: int
    box: Box | None
    width: int
    height: int
    mask: bytes
    pixels: bytes = b""
    channels: int = 3
    size_mismatch: bool = False
    expected_size: tuple[int, int] = (0, 0)
    actual_size: tuple[int, int] = (0, 0)


def _rgb_crop(pixels: bytes, size: tuple[int, int, int], width: int, height: int) -> bytes:
    """Top-left ``width`` x ``height`` window of ``pixels`` as packed RGB (alpha dropped)."""
    src_w, _, channels = size
    out = bytearray()
    for y in range(height):
        row = pixels[y * src_w * channels : (y * src_w + width) * channels]
        out += row if channels == 3 else b"".join(row[i : i + 3] for i in range(0, len(row), 4))
    return bytes(out)


def _compare_mismatched(
    expected: tuple[int, int, int, bytes], actual: tuple[int, int, int, bytes]
) -> Comparison:
    """Size mismatch: always a failure, but report an honest ratio instead of a flat 100%.

    The two images are compared over their shared top-left window; every pixel outside that
    window (the extra page height or width of the larger image) counts as differing. The
    cluster is not computed (-1). ``expected_size``/``actual_size`` carry the real sizes, so a
    report can say "page is 1329px tall, handoff 1451px" (T-UR00b).
    """
    w1, h1, c1, a = expected
    w2, h2, c2, b = actual
    cw, ch = min(w1, w2), min(h1, h2)
    crop_a = _rgb_crop(a, (w1, h1, c1), cw, ch)
    crop_b = _rgb_crop(b, (w2, h2, c2), cw, ch)
    mask = diff_mask(crop_a, crop_b, 3)
    union = max(w1, w2) * max(h1, h2)
    ratio = (mask.count(1) + union - cw * ch) / union
    return Comparison(
        ratio,
        -1,
        None,
        cw,
        ch,
        mask,
        crop_b,
        3,
        size_mismatch=True,
        expected_size=(w1, h1),
        actual_size=(w2, h2),
    )


def passes(result: Comparison, *, ratio_limit: float, cluster_cap: int) -> bool:
    """Verdict: a size mismatch always fails, whatever its ratio; else ratio and cluster limits."""
    return (
        not result.size_mismatch and result.ratio <= ratio_limit and result.cluster <= cluster_cap
    )


def largest_cluster(
    mask: bytes, width: int, height: int, cap: int | None = None
) -> tuple[int, Box | None]:
    """Size and bounding box of the largest 8-connected region of set cells in ``mask``.

    With ``cap`` the scan stops at the first region larger than ``cap`` (returns ``cap + 1``).
    """
    seen = bytearray(len(mask))
    best, best_box = 0, None
    start = mask.find(1)
    while start != -1:
        if seen[start]:
            start = mask.find(1, start + 1)
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
            if cap is not None and size > cap:
                return cap + 1, (left, top, right, bottom)
        if size > best:
            best, best_box = size, (left, top, right, bottom)
        start = mask.find(1, start + 1)
    return best, best_box


_NONZERO_TO_ONE: Final = bytes([0] + [1] * 255)


def diff_mask(a: bytes, b: bytes, channels: int) -> bytes:
    """Per-pixel 1/0 mask of differing pixels, via big-int XOR (no per-pixel Python loop)."""
    n = len(a)
    xor = (int.from_bytes(a, "little") ^ int.from_bytes(b, "little")).to_bytes(n, "little")
    flags = xor.translate(_NONZERO_TO_ONE)
    merged = int.from_bytes(flags[0::channels], "little")
    for k in range(1, channels):
        merged |= int.from_bytes(flags[k::channels], "little")
    return merged.to_bytes(n // channels, "little")


def compare(
    expected: Path,
    actual: Path,
    *,
    ratio_limit: float | None = None,
    cluster_cap: int | None = None,
) -> Comparison:
    """Pixel ratio plus largest differing cluster of two same-size PNGs.

    The cluster scan is skipped when the ratio is above ``ratio_limit`` and stops early above
    ``cluster_cap`` (both ``None`` = exact cluster, used for self-comparison calibration).
    """
    w1, h1, c1, a = _decode(expected)
    w2, h2, c2, b = _decode(actual)
    if (w1, h1) == (w2, h2) and c1 != c2:
        # RGBA against RGB at one size: the alpha channel is not content, compare in RGB.
        a = _rgb_crop(a, (w1, h1, c1), w1, h1)
        b = _rgb_crop(b, (w2, h2, c2), w2, h2)
        c1 = c2 = 3
    if (w1, h1, c1) != (w2, h2, c2):
        return _compare_mismatched((w1, h1, c1, a), (w2, h2, c2, b))
    mask = diff_mask(a, b, c1)
    ratio = mask.count(1) / (w1 * h1)
    if ratio_limit is not None and ratio > ratio_limit:
        return Comparison(ratio, -1, None, w1, h1, mask, b, c1)
    cluster, box = largest_cluster(mask, w1, h1, cluster_cap)
    return Comparison(ratio, cluster, box, w1, h1, mask, b, c1)


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


def write_diff_png(result: Comparison, out: Path) -> None:
    """Actual screenshot with differing pixels red; the largest cluster (if scanned) outlined.

    After a size mismatch the image covers the shared top-left window only.
    """
    w, h, c = result.width, result.height, result.channels
    n = w * h
    rgb = bytearray(n * 3)
    on = int.from_bytes(result.mask.translate(bytes([0, 255] + [255] * 254)), "little")
    off = on ^ int.from_bytes(b"\xff" * n, "little")
    chans = [int.from_bytes(result.pixels[k::c], "little") for k in range(3)]
    red = (chans[0] | on).to_bytes(n, "little")
    green = (chans[1] & off).to_bytes(n, "little")
    blue = (chans[2] & off).to_bytes(n, "little")
    rgb[0::3], rgb[1::3], rgb[2::3] = red, green, blue
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
