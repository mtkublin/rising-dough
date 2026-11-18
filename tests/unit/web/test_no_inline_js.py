"""Templates must carry no inline JS (T-D140b, ADR-0113): the prod CSP blocks it."""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[3] / "src" / "budget_planner" / "web" / "templates"

# Inline <script> without src (a <script ... src=...> tag is fine).
INLINE_SCRIPT = re.compile(r"<script\b(?![^>]*\bsrc=)[^>]*>", re.IGNORECASE)
# Inline event handler attributes (onclick=, onsubmit=, ...) and hx-on / hx-on:: attributes.
HANDLER_ATTR = re.compile(r"""\s(on[a-z]+|hx-on[:\w-]*)\s*=""", re.IGNORECASE)
JS_HREF = re.compile(r"""(href|action)\s*=\s*["']\s*javascript:""", re.IGNORECASE)

SKIPPED: frozenset[str] = frozenset()


def _templates() -> list[Path]:
    return sorted(
        p for p in TEMPLATES.rglob("*.html") if p.relative_to(TEMPLATES).as_posix() not in SKIPPED
    )


def test_no_inline_script_blocks() -> None:
    offenders = [
        f"{p.relative_to(TEMPLATES)}:{text[: m.start()].count(chr(10)) + 1}"
        for p in _templates()
        for text in [p.read_text()]
        for m in INLINE_SCRIPT.finditer(text)
    ]
    assert offenders == []


def test_no_inline_event_handlers() -> None:
    offenders = [
        f"{p.relative_to(TEMPLATES)}:{text[: m.start()].count(chr(10)) + 1}: {m.group(1)}"
        for p in _templates()
        for text in [p.read_text()]
        for m in [*HANDLER_ATTR.finditer(text), *JS_HREF.finditer(text)]
    ]
    assert offenders == []
