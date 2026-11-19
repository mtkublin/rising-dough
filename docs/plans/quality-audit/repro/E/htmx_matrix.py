"""T-Q08 Track E: HTMX emitter / listener / swap-target matrix.

Run: ``python3 docs/plans/quality-audit/repro/E/htmx_matrix.py``.
Stdlib only, read-only. Prints markdown to stdout. Static analysis of
``src/budget_planner/web`` at the checked-out commit (AUDIT_SHA for the audit).
"""

from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
WEB = ROOT / "src" / "budget_planner" / "web"
TEMPLATES = WEB / "templates"
JS_DIR = WEB / "static" / "js"
DYN = "\x00"

# DOM events that are not application events.
STANDARD = {
    "click", "change", "submit", "input", "keyup", "keydown", "load", "revealed",
    "intersect", "every", "focus", "blur", "mouseenter", "mouseover", "toggle",
    "DOMContentLoaded", "beforeinput", "paste", "mousedown", "resize", "scroll", "keypress", "dblclick", "pointerdown",
}

Loc = tuple[str, int]


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def short(p: str) -> str:
    return p.replace("src/budget_planner/web/templates/", "t/").replace("src/budget_planner/web/", "")


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


# --------------------------------------------------------------------------- emitters
def _const_strs(node: ast.AST) -> list[str]:
    return [
        n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def _dict_keys(node: ast.AST, params: dict[str, list[str]]) -> list[str]:
    """Top-level keys of the outermost dict(s) only (nested keys are payload fields)."""
    keys: list[str] = []
    nested: set[int] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Dict) and id(n) not in nested:
            for v in n.values:
                nested.update(id(x) for x in ast.walk(v) if isinstance(x, ast.Dict))
            for k in n.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.append(k.value)
                elif isinstance(k, ast.Name):
                    keys.extend(params.get(k.id, [f"<dynamic:{k.id}>"]))
    return keys


def _fn_params(fn: ast.FunctionDef, wrapper_kwargs: dict[str, list[str]]) -> dict[str, list[str]]:
    params: dict[str, list[str]] = {}
    pos = fn.args.args
    pairs: list[tuple[ast.arg, ast.expr | None]] = list(
        zip(pos, [None] * (len(pos) - len(fn.args.defaults)) + list(fn.args.defaults), strict=True)
    )
    pairs += list(zip(fn.args.kwonlyargs, fn.args.kw_defaults, strict=True))
    for a, d in pairs:
        vals = list(wrapper_kwargs.get(f"{fn.name}.{a.arg}", []))
        if isinstance(d, ast.Constant) and isinstance(d.value, str):
            vals.append(d.value)
        if vals:
            params[a.arg] = vals
    return params


def _call_name(n: ast.Call) -> str:
    if isinstance(n.func, ast.Name):
        return n.func.id
    if isinstance(n.func, ast.Attribute):
        return n.func.attr
    return ""


def collect_emitters() -> tuple[dict[str, list[Loc]], list[tuple[str, int, str, str]]]:
    events: dict[str, list[Loc]] = defaultdict(list)
    other: list[tuple[str, int, str, str]] = []
    wrapper_kwargs: dict[str, list[str]] = defaultdict(list)
    trees: dict[Path, ast.Module] = {}
    for f in sorted((ROOT / "src" / "budget_planner").rglob("*.py")):
        trees[f] = ast.parse(f.read_text(), filename=str(f))
    for tree in trees.values():
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                for kw in n.keywords:
                    if kw.arg and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        wrapper_kwargs[f"{n.func.id}.{kw.arg}"].append(kw.value.value)
    for f, tree in trees.items():
        r = rel(f)
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            params = _fn_params(fn, wrapper_kwargs)
            for n in ast.walk(fn):
                if isinstance(n, ast.Call):
                    name = _call_name(n)
                    if name == "trigger" and len(n.args) >= 2:
                        for a in n.args[1:]:
                            for s in _const_strs(a):
                                events[s].append((r, n.lineno))
                    elif name == "trigger_from_iterable":
                        events["<dynamic:trigger_from_iterable>"].append((r, n.lineno))
                if isinstance(n, ast.Assign):
                    _scan_header_assign(fn, n, params, events, other, r)
                if isinstance(n, ast.Dict):
                    _scan_header_dict(n, other, r)
    for k in events:
        events[k] = sorted(set(events[k]))
    return events, sorted(set(other))


def _resolve_names(value: ast.AST, fn: ast.FunctionDef) -> ast.AST:
    """Replace a bare variable inside the header expression by its dict literal in ``fn``."""
    names = {x.id for x in ast.walk(value) if isinstance(x, ast.Name)}
    found: list[ast.AST] = [value]
    for a in ast.walk(fn):
        if isinstance(a, ast.AnnAssign) and isinstance(a.target, ast.Name) and a.target.id in names:
            if a.value is not None:
                found.append(a.value)
        if isinstance(a, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in a.targets):
            found.append(a.value)
    return ast.Tuple(elts=[x for x in found if isinstance(x, ast.expr)], ctx=ast.Load())


def _scan_header_assign(
    fn: ast.FunctionDef,
    n: ast.Assign,
    params: dict[str, list[str]],
    events: dict[str, list[Loc]],
    other: list[tuple[str, int, str, str]],
    r: str,
) -> None:
    for t in n.targets:
        if not (
            isinstance(t, ast.Subscript)
            and isinstance(t.slice, ast.Constant)
            and isinstance(t.slice.value, str)
            and t.slice.value.startswith("HX-")
        ):
            continue
        hname = t.slice.value
        if hname.startswith("HX-Trigger"):
            for k in _dict_keys(_resolve_names(n.value, fn), params):
                events[k].append((r, n.lineno))
        else:
            other.append((r, n.lineno, hname, ast.unparse(n.value)))


def _scan_header_dict(n: ast.Dict, other: list[tuple[str, int, str, str]], r: str) -> None:
    for k, v in zip(n.keys, n.values, strict=False):
        if (
            isinstance(k, ast.Constant)
            and isinstance(k.value, str)
            and k.value.startswith("HX-")
            and not k.value.startswith("HX-Trigger")
        ):
            other.append((r, n.lineno, k.value, ast.unparse(v)))


# --------------------------------------------------------------------------- listeners
def collect_template_listeners() -> dict[str, list[Loc]]:
    out: dict[str, list[Loc]] = defaultdict(list)
    pat = re.compile(r'hx-trigger="([^"]*)"', re.S)
    for t in sorted(TEMPLATES.rglob("*.html")):
        text = t.read_text()
        for m in pat.finditer(text):
            for part in m.group(1).split(","):
                tok = part.strip().split()
                if tok:
                    out[tok[0]].append((rel(t), line_of(text, m.start())))
    return out


def collect_js() -> tuple[dict[str, list[Loc]], dict[str, list[Loc]]]:
    listen: dict[str, list[Loc]] = defaultdict(list)
    dispatch: dict[str, list[Loc]] = defaultdict(list)
    for j in sorted(JS_DIR.glob("*.js")) + [WEB / "static" / "htmx-csrf.js"]:
        text = j.read_text()
        for m in re.finditer(r"(?:addEventListener|htmx\.on)\(\s*[\"']([^\"']+)[\"']", text):
            listen[m.group(1)].append((rel(j), line_of(text, m.start())))
        for m in re.finditer(r"dispatchEvent\(\s*new\s+(?:Custom)?Event\(\s*[\"']([^\"']+)[\"']", text):
            dispatch[m.group(1)].append((rel(j), line_of(text, m.start())))
    return listen, dispatch


def fmt(locs: list[Loc], limit: int = 4) -> str:
    shown = [f"`{short(p)}:{ln}`" for p, ln in locs[:limit]]
    more = f" (+{len(locs) - limit})" if len(locs) > limit else ""
    return ", ".join(shown) + more


# --------------------------------------------------------------------------- ids / targets
def norm(s: str) -> str:
    s = re.sub(r"\{\{.*?\}\}", DYN, s, flags=re.S)
    return re.sub(r"\{%.*?%\}", DYN, s, flags=re.S)


def _rx(s: str, other: str) -> bool:
    pat = "^" + ".*".join(re.escape(p) for p in s.split(DYN)) + "$"
    return re.match(pat, other.replace(DYN, "X")) is not None


def skeleton_match(a: str, b: str) -> bool:
    """True when two id strings (either may contain DYN) can denote the same id."""
    return _rx(a, b) or _rx(b, a)


def collect_ids() -> dict[str, list[Loc]]:
    ids: dict[str, list[Loc]] = defaultdict(list)
    for t in sorted(TEMPLATES.rglob("*.html")):
        text = t.read_text()
        for m in re.finditer(r'\sid="([^"]+)"', text):
            ids[norm(m.group(1))].append((rel(t), line_of(text, m.start())))
    for f in list(WEB.rglob("*.py")) + list(JS_DIR.glob("*.js")):
        text = f.read_text()
        for m in re.finditer(r'\bid=\\?"([A-Za-z][\w-]*)\\?"', text):
            ids[m.group(1)].append((rel(f), line_of(text, m.start())))
    return ids


def collect_classes() -> set[str]:
    classes: set[str] = set()
    for t in TEMPLATES.rglob("*.html"):
        for m in re.finditer(r'class="([^"]*)"', t.read_text()):
            classes.update(norm(m.group(1)).split())
    return classes


def collect_targets() -> list[tuple[str, str, str, int]]:
    out: list[tuple[str, str, str, int]] = []
    for t in sorted(TEMPLATES.rglob("*.html")):
        text = t.read_text()
        for m in re.finditer(r'(hx-target|hx-select|hx-indicator)="([^"]*)"', text):
            out.append((m.group(1), norm(m.group(2)), rel(t), line_of(text, m.start())))
    return out


def collect_py_retargets() -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for f in WEB.rglob("*.py"):
        text = f.read_text()
        for m in re.finditer(r'"HX-Retarget"\]?\s*[:=]\s*"([^"]+)"', text):
            out.append((rel(f), line_of(text, m.start()), m.group(1)))
    return out


def collect_js_id_refs() -> list[tuple[str, str, int]]:
    out: list[tuple[str, str, int]] = []
    for j in sorted(JS_DIR.glob("*.js")):
        text = j.read_text()
        for m in re.finditer(r"getElementById\(\s*[\"']([^\"']+)[\"']", text):
            out.append((m.group(1), rel(j), line_of(text, m.start())))
        for m in re.finditer(r"target:\s*[\"']#([\w-]+)[\"']", text):
            out.append((m.group(1), rel(j), line_of(text, m.start())))
    return out


def target_exists(sel: str, ids: dict[str, list[Loc]], classes: set[str]) -> str:
    sel = sel.strip()
    if sel == DYN:
        return "dynamic"
    if sel in {"this", "body", "document", "window"}:
        return "n/a"
    if sel.startswith("closest "):
        sel = sel[len("closest "):].strip()
    first = sel.split()[0] if sel.split() else sel
    if first.startswith("#"):
        want = first[1:]
        return "ok" if any(skeleton_match(want, i) for i in ids) else "MISSING"
    if first.startswith("."):
        return "ok" if first[1:] in classes else "MISSING"
    return "n/a"


# --------------------------------------------------------------------------- report
def _events_table() -> None:
    emit, _ = collect_emitters()
    t_listen = collect_template_listeners()
    js_listen, js_dispatch = collect_js()
    all_listen: dict[str, list[Loc]] = defaultdict(list)
    for src in (t_listen, js_listen):
        for k, v in src.items():
            if k not in STANDARD and not k.startswith("htmx:"):
                all_listen[k].extend(v)
    all_emit: dict[str, list[Loc]] = defaultdict(list)
    for k, v in emit.items():
        all_emit[k].extend(v)
    for k, v in js_dispatch.items():
        if k not in STANDARD:
            all_emit[k].extend(v)
    print("## 1. Application events: emitters vs listeners\n")
    print("| Event | Emitted by (HX-Trigger / JS dispatch) | Listened by (hx-trigger / addEventListener) | Status |")
    print("|---|---|---|---|")
    names = sorted(set(all_emit) | set(all_listen))
    orphan_e = orphan_l = 0
    for n in names:
        e, ls = all_emit.get(n, []), all_listen.get(n, [])
        if e and ls:
            status = "paired"
        elif e:
            status = "ORPHAN emitter (no listener)"
            orphan_e += 1
        else:
            status = "ORPHAN listener (no emitter)"
            orphan_l += 1
        print(f"| `{n}` | {fmt(e) or '-'} | {fmt(ls) or '-'} | {status} |")
    n_emit = len([n for n in names if all_emit.get(n)])
    n_listen = len([n for n in names if all_listen.get(n)])
    print(
        f"\nEmitted names: {n_emit}; listened names: {n_listen}; "
        f"orphan emitters: {orphan_e}; orphan listeners: {orphan_l}.\n"
    )
    print("## 2. HTMX lifecycle listeners (htmx:*)\n")
    print("| Event | Listeners |")
    print("|---|---|")
    for k in sorted(k for k in js_listen if k.startswith("htmx:")):
        print(f"| `{k}` | {fmt(js_listen[k], 8)} |")
    print()


def _headers_table() -> None:
    _, other_hx = collect_emitters()
    print("## 3. Other HX-* response headers set by routers/middleware\n")
    print("| Header | Value | Location |")
    print("|---|---|---|")
    for r, ln, h, v in other_hx:
        print(f"| `{h}` | `{v}` | `{short(r)}:{ln}` |")
    print()


def _targets_table(ids: dict[str, list[Loc]]) -> None:
    classes = collect_classes()
    print("## 4. Swap targets that resolve to no id/class in any template, router or JS\n")
    print("| Attr | Selector | Location | Result |")
    print("|---|---|---|---|")
    bad = dyn = total = 0
    for attr, val, f, ln in collect_targets():
        total += 1
        res = target_exists(val, ids, classes)
        if res == "dynamic":
            dyn += 1
        if res == "MISSING":
            bad += 1
            print(f"| {attr} | `{val.replace(DYN, '{..}')}` | `{short(f)}:{ln}` | MISSING |")
    for r, ln, v in collect_py_retargets():
        total += 1
        if target_exists(v, ids, classes) == "MISSING":
            bad += 1
            print(f"| HX-Retarget | `{v}` | `{short(r)}:{ln}` | MISSING |")
    for ident, f, ln in collect_js_id_refs():
        total += 1
        if not any(skeleton_match(ident, i) for i in ids):
            bad += 1
            print(f"| JS id ref | `#{ident}` | `{short(f)}:{ln}` | MISSING |")
    print(f"\nChecked {total} selectors ({dyn} fully dynamic, unverifiable statically); missing: {bad}.\n")


def _dup_tables(ids: dict[str, list[Loc]]) -> None:
    print("## 5. Literal ids defined in more than one file\n")
    print("| id | Defined in |")
    print("|---|---|")
    n_dup = 0
    for i, locs in sorted(ids.items()):
        if DYN in i:
            continue
        files = sorted({p for p, _ in locs})
        if len(files) > 1:
            n_dup += 1
            print(f"| `{i}` | {', '.join('`' + short(p) + '`' for p in files)} |")
    print(f"\n{n_dup} literal ids appear in more than one file (static only).\n")
    print("## 6. Literal ids repeated within one file\n")
    print("| id | File | Lines |")
    print("|---|---|---|")
    for i, locs in sorted(ids.items()):
        by_file: dict[str, list[int]] = defaultdict(list)
        for p, ln in locs:
            by_file[p].append(ln)
        for p, lns in by_file.items():
            if len(lns) > 1 and DYN not in i:
                print(f"| `{i}` | `{short(p)}` | {', '.join(map(str, lns))} |")


def main() -> int:
    print("# HTMX contract matrix (generated)\n")
    _events_table()
    _headers_table()
    ids = collect_ids()
    _targets_table(ids)
    _dup_tables(ids)
    return 0


if __name__ == "__main__":
    sys.exit(main())
