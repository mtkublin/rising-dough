"""``handoff.compare`` on synthetic images: equal sizes and the size-mismatch rule (T-UR00b)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from tests.visual.handoff import Comparison, compare, passes, write_diff_png


def _write(
    path: Path, width: int, height: int, paint: dict[tuple[int, int], tuple[int, int, int]]
) -> Path:
    white = (255, 255, 255)
    raw = b"".join(
        b"\x00" + b"".join(bytes(paint.get((x, y), white)) for x in range(width))
        for y in range(height)
    )

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return path


def test_equal_images_have_no_difference(tmp_path: Path) -> None:
    a = _write(tmp_path / "a.png", 10, 10, {})
    b = _write(tmp_path / "b.png", 10, 10, {})
    result = compare(a, b)
    assert (result.ratio, result.cluster, result.size_mismatch) == (0.0, 0, False)


def test_same_size_reports_exact_ratio_and_cluster(tmp_path: Path) -> None:
    a = _write(tmp_path / "a.png", 10, 10, {})
    b = _write(tmp_path / "b.png", 10, 10, {(1, 1): (0, 0, 0), (2, 1): (0, 0, 0)})
    result = compare(a, b)
    assert result.ratio == 0.02
    assert (result.cluster, result.box) == (2, (1, 1, 2, 1))


def test_height_mismatch_is_honest_not_a_flat_100_percent(tmp_path: Path) -> None:
    expected = _write(tmp_path / "e.png", 10, 20, {})
    actual = _write(tmp_path / "a.png", 10, 10, {(0, 0): (0, 0, 0)})
    result = compare(expected, actual)
    assert result.size_mismatch is True
    assert (result.expected_size, result.actual_size) == ((10, 20), (10, 10))
    # 1 differing pixel in the shared 10 x 10 window + the 100 pixels the shorter page lacks.
    assert result.ratio == 101 / 200
    assert result.cluster == -1


def test_identical_content_with_extra_height_still_fails_by_the_missing_rows(
    tmp_path: Path,
) -> None:
    expected = _write(tmp_path / "e.png", 10, 20, {})
    actual = _write(tmp_path / "a.png", 10, 10, {})
    result = compare(expected, actual, ratio_limit=0.001)
    assert result.size_mismatch is True
    assert result.ratio == 0.5


def test_width_mismatch_compares_the_shared_window(tmp_path: Path) -> None:
    expected = _write(tmp_path / "e.png", 8, 4, {(7, 3): (0, 0, 0)})
    actual = _write(tmp_path / "a.png", 10, 4, {(9, 3): (0, 0, 0)})
    result = compare(expected, actual)
    # Shared window is 8 x 4 and has no differing pixel (the marks are outside it for actual,
    # inside it for expected at (7, 3) where actual is white): 1 + (40 - 32).
    assert result.ratio == 9 / 40


def test_size_mismatch_writes_a_diff_of_the_shared_window(tmp_path: Path) -> None:
    expected = _write(tmp_path / "e.png", 6, 8, {})
    actual = _write(tmp_path / "a.png", 6, 5, {(2, 2): (0, 0, 0)})
    out = tmp_path / "out" / "d.png"
    write_diff_png(compare(expected, actual), out)
    assert out.is_file()
    assert compare(out, out).ratio == 0.0


def _result(ratio: float, cluster: int, *, mismatch: bool = False) -> Comparison:
    return Comparison(ratio, cluster, None, 1, 1, b"", size_mismatch=mismatch)


def test_passes_fails_a_size_mismatch_even_under_the_ratio_limit() -> None:
    assert not passes(_result(0.0005, -1, mismatch=True), ratio_limit=0.001, cluster_cap=52)


def test_passes_accepts_equal_sizes_under_both_limits() -> None:
    assert passes(_result(0.0005, 10), ratio_limit=0.001, cluster_cap=52)


def test_passes_fails_over_the_ratio() -> None:
    assert not passes(_result(0.002, 10), ratio_limit=0.001, cluster_cap=52)


def test_passes_fails_over_the_cluster() -> None:
    assert not passes(_result(0.0005, 53), ratio_limit=0.001, cluster_cap=52)
