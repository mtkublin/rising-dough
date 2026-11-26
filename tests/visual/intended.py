"""Intended differences from the handoff (ADR-0147 amendment 2026-11-26).

Single source: the "## Intended differences" table in ``docs/plans/ui-redesign/derived.md``.
Each row becomes ``{(page, width, theme): "<decision>: <reason>"}``; the reference comparison marks
those ids ``xfail(strict=True)`` (they are not tolerance exceptions).
"""

from __future__ import annotations

from pathlib import Path

DERIVED = Path(__file__).resolve().parents[2] / "docs/plans/ui-redesign/derived.md"
WIDTHS: tuple[str, ...] = ("1440", "1024", "375")
THEMES: tuple[str, ...] = ("light", "dark")
HEADING = "## Intended differences"

Key = tuple[str, str, str]


def _rows(text: str) -> list[list[str]]:
    lines = text.splitlines()
    try:
        start = lines.index(HEADING)
    except ValueError:
        return []
    rows: list[list[str]] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] in ("Page", "") or set(cells[0]) <= {"-"}:
            continue
        rows.append(cells)
    return rows


def _shards(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Widths and themes named by a shards cell.

    "all" or "every shard" mean every width and theme; a named width or theme narrows that axis
    only. A cell naming none of them (free text) raises ``ValueError``: a typo must not silently
    widen the xfail set.
    """
    low = text.lower()
    if "all" in low.split() or "every shard" in low:
        return WIDTHS, THEMES
    if not any(w in low for w in WIDTHS) and not any(t in low for t in THEMES):
        raise ValueError(f"shards cell names no width or theme and is not 'all': {text!r}")
    widths = tuple(w for w in WIDTHS if w in low) or WIDTHS
    themes = tuple(t for t in THEMES if t in low) or THEMES
    return widths, themes


def _page_id(name: str, known: frozenset[str] | None) -> str:
    """``pages/<name>.html``; a bare name of an overlay page resolves under overlays/."""
    name = name.strip()
    first = f"pages/{name}.html"
    overlay = f"pages/overlays/{name}.html"
    if known is not None and first not in known and overlay in known:
        return overlay
    return first


def parse(text: str, known: frozenset[str] | None = None) -> dict[Key, str]:
    """Parse the table text into ``{(page, width, theme): "decision: reason"}``.

    A key listed by two rows keeps the first row's decision and reason (first row wins).
    """
    out: dict[Key, str] = {}
    for cells in _rows(text):
        pages, shards, decision, reason = cells[0], cells[1], cells[2], cells[3]
        widths, themes = _shards(shards)
        for page in pages.split(","):
            for width in widths:
                for theme in themes:
                    out.setdefault((_page_id(page, known), width, theme), f"{decision}: {reason}")
    return out


def load(known: frozenset[str] | None = None, path: Path = DERIVED) -> dict[Key, str]:
    return parse(path.read_text(), known)
