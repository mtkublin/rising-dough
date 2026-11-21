# mypy: ignore-errors
# Ported audit scanner (T-Q14b): stdlib AST/regex detector kept close to the original script, so style
# rules about branches, statements and line length are waived for this directory.
# ruff: noqa: E501, PLR0912
"""P12 logic in templates. ADR-0107 replaces every template (and presentational JS) in the Sourdough redesign, so
this inventory records per-file COUNTS only (no per-line list); the rules become a strict guard for the new tree.

Rules (counted per ``{{ }}`` / ``{% %}`` expression after stripping string literals and filters' arguments):
  tpl-scale        ``/ 100``, ``/ 100.0``, ``* 100``, ``/ 1000``
  tpl-float        ``|float``, ``|round``, ``|int`` applied to an amount-looking expression
  tpl-arith        any other arithmetic operator between operands (``+ - * / // %``) in an output or ``if`` expression
  tpl-set          ``{% set %}`` (derived value in the template)
  tpl-domain-if    ``{% if %}`` comparing direction/kind/status/cadence/currency/account_type to a literal
  tpl-currency-lit hard-coded ISO currency code string ('PLN', 'EUR', ...)
  tpl-format       ``|format``, ``%``-format, ``.strftime(``, ``.isoformat(`` (formatting outside the shared filters)
Also counts kept JS (htmx-csrf.js, passkeys.js, users-admin.js) for money math / clock: ``js-money``, ``js-clock``.
"""

from __future__ import annotations

import re
from collections import Counter

from tests.architecture._scan._common import ROOT, STATIC, TEMPLATES, write

EXPR = re.compile(r"\{\{-?(.*?)-?\}\}|\{%-?(.*?)-?%\}", re.S)
STR = re.compile(r"'[^']*'|\"[^\"]*\"")
SCALE = re.compile(r"(/|\*|//)\s*(100\.0|100|1000)\b|\b(100\.0|100|1000)\s*(\*|/)")
FLOAT = re.compile(r"\|\s*(float|round|int)\b")
ARITH = re.compile(r"[\w\)\]]\s*(\+|-|\*|/|//|%)\s*[\w\(\[]")
DOMAIN = re.compile(
    r"\b(direction|kind|status|cadence|currency|account_type|type)\b\s*(==|!=|in|not in)\s*[\[(]?['\"]",
    re.I,
)
CCY = re.compile(r"['\"](PLN|EUR|USD|GBP|CHF|JPY|CZK)['\"]")
FMT = re.compile(r"\|\s*format\b|\.strftime\(|\.isoformat\(|\"\s*%\s*|'\s*%\s*")


def main() -> None:
    per_file: list[tuple[str, str, str]] = []
    totals: Counter[str] = Counter()
    for p in sorted(TEMPLATES.rglob("*.html")):
        rel_p = p.relative_to(ROOT).as_posix()
        txt = p.read_text()
        c: Counter[str] = Counter()
        for m in EXPR.finditer(txt):
            expr = m.group(1) if m.group(1) is not None else m.group(2)
            raw = expr
            is_stmt = m.group(2) is not None
            clean = STR.sub("''", raw)
            if is_stmt and raw.strip().startswith("set "):
                c["tpl-set"] += 1
            if is_stmt and re.match(r"\s*(if|elif)\b", raw) and DOMAIN.search(raw):
                c["tpl-domain-if"] += 1
            if is_stmt and re.match(
                r"\s*(import|from|macro|include|extends|block|endblock|endmacro|call)\b", raw
            ):
                continue
            if SCALE.search(clean):
                c["tpl-scale"] += 1
            if FLOAT.search(clean):
                c["tpl-float"] += 1
            if CCY.search(raw):
                c["tpl-currency-lit"] += 1
            if FMT.search(raw):
                c["tpl-format"] += 1
            body = re.sub(r"\|\s*\w+(\([^)]*\))?", "", clean)  # drop filters
            if ARITH.search(body) and not SCALE.search(clean):
                c["tpl-arith"] += 1
        for k, v in c.items():
            per_file.append((f"{rel_p}:0", k, str(v)))
            totals[k] += v
    write(
        "p12-templates",
        "P12 template logic: per-file COUNTS (rule<TAB>count). Script: repro/inventory/p12_templates.py\n"
        "All templates are replaced by ADR-0107; count only. Totals: "
        + ", ".join(f"{k}={v}" for k, v in sorted(totals.items())),
        per_file,
    )
    js: list[tuple[str, str, str]] = []
    for name in ("htmx-csrf.js", "js/passkeys.js", "js/users-admin.js"):
        p = STATIC / name
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if re.search(r"/\s*100\b|\*\s*100\b|toFixed|parseFloat", line):
                js.append((f"{p.relative_to(ROOT).as_posix()}:{i}", "js-money", line.strip()[:90]))
            if re.search(r"Date\.now\(|new Date\(", line):
                js.append((f"{p.relative_to(ROOT).as_posix()}:{i}", "js-clock", line.strip()[:90]))
    write("p12-js-kept", "P12 kept JS (htmx-csrf, passkeys, users-admin): money math / clock", js)
