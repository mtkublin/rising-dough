# mypy: ignore-errors
# Ported audit scanner (T-Q14b): stdlib AST/regex detector kept close to the original script, so style
# rules about branches, statements and line length are waived for this directory.
# ruff: noqa: E501, PLR0912, PLR0915, SIM114, E741
"""P8 money (ADR-0008 / ADR-0006). Canonical homes today: ``domain/money.py`` (exponent, parse, format, rounding),
``web/templating.py`` Jinja filters (display), ``services/fx.py`` + ``domain/fx.py`` (conversion).
Rows inside canonical files are emitted with suffix ``:canonical`` so a guard allowlist can skip them.

Rules
  money-scale      arithmetic with 100 / 100.0 / 1000 / 10000, ``10 ** n``, ``Decimal("100")``, ``divmod(x, 100)``
  money-float      ``float(...)`` call, ``: float`` annotation, float literal in arithmetic (money-ish flag in detail)
  money-round      ``round(``, ``.quantize(``, ``ROUND_*``, ``math.floor/ceil``, ``//`` on non-literal operands
  money-format     f-string / %-format / .format with an ``f`` or ``,`` spec, ``locale.``; hand-built "<amount> <ccy>" strings
  money-parse      ``Decimal(`` / ``int(`` / ``float(`` applied to user-text-looking names (amount/raw/value/text), ``_parse_amount*`` defs
  fx-def           function whose name matches convert|to_base|rate|fx|exchange
  fx-call          call to convert / convert_cached / get_rate / latest_rate / rate lookup
  fx-arith         arithmetic whose operand name contains ``rate``
"""

from __future__ import annotations

import ast
import re

from tests.architecture._scan._common import (
    dotted,
    enclosing_function_map,
    layer,
    parse,
    py_files,
    rel,
    unparse,
    walk,
    write,
)

SCALES = {100, 1000, 10000}
MONEYISH = re.compile(
    r"amount|minor|balance|price|total|spent|budget|cost|fortune|income|expense|saving|major|rate|money|salary|payment",
    re.I,
)


def ftag(f: str, text: str) -> str:
    """money-float when the expression/name looks monetary, else float-other (geometry, time)."""
    return tag(f, "money-float" if MONEYISH.search(text) else "float-other")


ROUND_NAMES = {"round", "quantize", "floor", "ceil"}
CANON = {
    "src/budget_planner/domain/money.py",
    "src/budget_planner/domain/fx.py",
    "src/budget_planner/services/fx.py",
    "src/budget_planner/repositories/fx.py",
    "src/budget_planner/web/templating.py",
}
FX_DEF = re.compile(r"convert|to_base|exchange|(^|_)rate(s)?($|_(?!limit|now))|(^|_)fx($|_)", re.I)
FX_CALLS = {
    "convert",
    "convert_cached",
    "get_rate",
    "latest_rate",
    "get_cached_rate",
    "lookup_rate",
    "find_rate",
    "rate_on",
}
PARSE_NAME = re.compile(r"parse.*(amount|money|minor|decimal)|(amount|money).*parse", re.I)


def tag(f: str, rule: str) -> str:
    return f"{rule}:canonical" if f in CANON else rule


def const_num(n: ast.AST) -> float | None:
    if (
        isinstance(n, ast.Constant)
        and isinstance(n.value, int | float)
        and not isinstance(n.value, bool)
    ):
        return n.value
    return None


def main() -> None:
    rows: list[tuple[str, str, str]] = []
    for p in py_files():
        f = rel(p)
        lay = layer(p)
        tree = parse(p)
        enc = enclosing_function_map(tree)
        for n in walk(tree):
            where = f"{f}:{getattr(n, 'lineno', 0)}"
            fn = enc.get(id(n), "<module>")
            if isinstance(n, ast.BinOp):
                l, r = const_num(n.left), const_num(n.right)
                txt = unparse(n)
                if isinstance(n.op, ast.Div | ast.FloorDiv | ast.Mult | ast.Mod) and (
                    l in SCALES or r in SCALES
                ):
                    rows.append((where, tag(f, "money-scale"), f"[{lay}] {fn}: {txt}"))
                elif isinstance(n.op, ast.Pow) and l == 10:
                    rows.append((where, tag(f, "money-scale"), f"[{lay}] {fn}: {txt}"))
                if isinstance(n.op, ast.FloorDiv) and l is None and r is None:
                    rows.append((where, tag(f, "money-round"), f"[{lay}] {fn}: {txt}"))
                if isinstance(n.op, ast.Mult | ast.Div) and re.search(r"\brate\w*\b", txt):
                    rows.append((where, tag(f, "fx-arith"), f"[{lay}] {fn}: {txt}"))
                if isinstance(l, float) or isinstance(r, float):
                    rows.append((where, ftag(f, txt), f"[{lay}] {fn}: float literal in {txt}"))
            elif isinstance(n, ast.Call):
                d = dotted(n.func)
                tail = d.split(".")[-1] if d else ""
                txt = unparse(n)
                if tail == "float":
                    rows.append((where, ftag(f, txt), f"[{lay}] {fn}: {txt}"))
                if tail in ROUND_NAMES and (
                    d == tail or d.split(".")[0] in {"math", "decimal"} or tail == "quantize"
                ):
                    rows.append((where, tag(f, "money-round"), f"[{lay}] {fn}: {txt}"))
                if (
                    tail == "Decimal"
                    and n.args
                    and isinstance(n.args[0], ast.Constant)
                    and str(n.args[0].value) in {"100", "1000"}
                ):
                    rows.append((where, tag(f, "money-scale"), f"[{lay}] {fn}: {txt}"))
                if tail == "divmod" and any(const_num(a) in SCALES for a in n.args):
                    rows.append((where, tag(f, "money-scale"), f"[{lay}] {fn}: {txt}"))
                if (
                    tail == "Decimal"
                    and n.args
                    and re.search(
                        r"amount|raw|text|money|value|minor|major", unparse(n.args[0]), re.I
                    )
                    and lay in {"web.routers", "web", "services"}
                ):
                    rows.append((where, tag(f, "money-parse"), f"[{lay}] {fn}: {txt}"))
                if tail in FX_CALLS and tail != "get":
                    rows.append((where, tag(f, "fx-call"), f"[{lay}] {fn}: {txt}"))
                if d.startswith("locale."):
                    rows.append((where, tag(f, "money-format"), f"[{lay}] {fn}: {txt}"))
                if (
                    tail == "format"
                    and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Constant)
                    and re.search(r"\{[^}]*:[^}]*[f,][^}]*\}", str(n.func.value.value))
                ):
                    rows.append((where, tag(f, "money-format"), f"[{lay}] {fn}: {txt}"))
            elif isinstance(n, ast.FormattedValue) and n.format_spec is not None:
                spec = (
                    "".join(v.value for v in n.format_spec.values if isinstance(v, ast.Constant))
                    if isinstance(n.format_spec, ast.JoinedStr)
                    else ""
                )
                if re.search(r"[,_]|\.\d*f|f$", spec):
                    rows.append(
                        (
                            where,
                            tag(f, "money-format"),
                            f"[{lay}] {fn}: {{{unparse(n.value, 40)}:{spec}}}",
                        )
                    )
            elif (
                isinstance(n, ast.BinOp)
                and isinstance(n.op, ast.Mod)
                and isinstance(n.left, ast.Constant)
                and isinstance(n.left.value, str)
                and re.search(r"%[\d.,]*f", n.left.value)
            ):
                rows.append((where, tag(f, "money-format"), f"[{lay}] {fn}: {unparse(n)}"))
            elif (
                isinstance(n, ast.arg)
                and n.annotation is not None
                and unparse(n.annotation) in {"float", "float | None"}
            ):
                rows.append(
                    (where, ftag(f, n.arg), f"[{lay}] {fn}: param {n.arg}: {unparse(n.annotation)}")
                )
            elif isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
                if n.returns is not None and unparse(n.returns) in {"float", "float | None"}:
                    rows.append(
                        (where, ftag(f, n.name), f"[{lay}] {n.name}() -> {unparse(n.returns)}")
                    )
                if FX_DEF.search(n.name):
                    rows.append((where, tag(f, "fx-def"), f"[{lay}] def {n.name}"))
                if PARSE_NAME.search(n.name):
                    rows.append((where, tag(f, "money-parse"), f"[{lay}] def {n.name}"))
            elif isinstance(n, ast.AnnAssign) and unparse(n.annotation) in {
                "float",
                "float | None",
            }:
                rows.append(
                    (
                        where,
                        ftag(f, unparse(n.target)),
                        f"[{lay}] {fn}: field {unparse(n.target)}: {unparse(n.annotation)}",
                    )
                )
        for n in walk(tree):
            if isinstance(n, ast.Name) and n.id.startswith("ROUND_"):
                rows.append((f"{f}:{n.lineno}", tag(f, "money-round"), f"[{lay}] {n.id}"))
            if (
                isinstance(n, ast.Assign)
                and isinstance(n.targets[0], ast.Name)
                and re.search(r"MINOR_UNITS|PER_MAJOR|SCALE|DECIMALS", n.targets[0].id)
                and const_num(n.value) is not None
            ):
                rows.append(
                    (
                        f"{f}:{n.lineno}",
                        tag(f, "money-scale"),
                        f"[{lay}] const {n.targets[0].id} = {unparse(n.value)}",
                    )
                )
    write(
        "p08-money",
        "P8 money. Script: repro/inventory/p08_money.py\n"
        "Rules: money-scale, money-float, money-round, money-format, money-parse, fx-def, fx-call, fx-arith.\n"
        "Suffix :canonical = inside the file that is the canonical home today (domain/money.py, domain/fx.py, services/fx.py, web/templating.py).",
        rows,
    )
