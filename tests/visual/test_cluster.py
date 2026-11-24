"""Largest 8-connected differing cluster (T-UR00b, ADR-0147 section 2)."""

from __future__ import annotations

from tests.visual.handoff import largest_cluster


def _mask(rows: list[str]) -> tuple[bytes, int, int]:
    return bytes(1 if c == "#" else 0 for r in rows for c in r), len(rows[0]), len(rows)


def test_empty_mask_has_no_cluster() -> None:
    assert largest_cluster(*_mask(["...", "..."])) == (0, None)


def test_single_pixel() -> None:
    assert largest_cluster(*_mask(["...", ".#.", "..."])) == (1, (1, 1, 1, 1))


def test_two_blobs_report_the_larger() -> None:
    rows = ["##...", "##..#", ".....", "...##"]
    assert largest_cluster(*_mask(rows)) == (4, (0, 0, 1, 1))


def test_diagonal_pixels_are_connected() -> None:
    assert largest_cluster(*_mask(["#..", ".#.", "..#"])) == (3, (0, 0, 2, 2))


def test_gap_of_one_cell_separates() -> None:
    assert largest_cluster(*_mask(["#.#"]))[0] == 1
