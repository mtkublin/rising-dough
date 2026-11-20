# mypy: ignore-errors
# Ported audit scanner (T-Q14b): stdlib AST/regex detector kept close to the original script, so style
# rules about branches, statements and line length are waived for this directory.
# ruff: noqa: E501, PLC0415
"""Ported T-Q14b compliance-inventory scanners (ADR-0130).

The scanners are the audit's deterministic AST/regex detectors, kept as in-memory
row producers: ``rows("p06-sql-outside-repos")`` returns ``(path:line, rule, detail)``
tuples. Everything runs once per process (parsed ASTs are cached).
"""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

from tests.architecture._scan import (
    p01_dry,
    p02_functional,
    p03_immutability,
    p04_p07_effects_clock,
    p05_p06_web_repo,
    p08_money,
    p09_p10_p11_imports_size_suppress,
    p12_templates,
    p13_other,
)
from tests.architecture._scan._common import ROOT, ROWS


def _inputs_key() -> str:
    """Content hash of everything a scanner reads (sources, templates, migrations, config, scanners)."""
    digest = hashlib.sha256()
    roots = (ROOT / "src" / "budget_planner", ROOT / "migrations", Path(__file__).parent)
    files = [p for r in roots for p in r.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    files.append(ROOT / "pyproject.toml")
    for p in sorted(files):
        digest.update(p.relative_to(ROOT).as_posix().encode())
        digest.update(p.read_bytes())
    return digest.hexdigest()[:20]


@lru_cache(maxsize=1)
def _run_all() -> None:
    """Run every scanner once per process; results are cached on disk by input content hash."""
    cache = ROOT / ".pytest_cache" / f"architecture-scan-{_inputs_key()}.json"
    try:
        ROWS.update({k: [tuple(r) for r in v] for k, v in json.loads(cache.read_text()).items()})
        return
    except (OSError, ValueError):
        pass  # missing, being replaced by a parallel worker, or corrupt: rescan
    _scan_all()
    cache.parent.mkdir(exist_ok=True)
    for stale in cache.parent.glob("architecture-scan-*.json"):
        if stale != cache:
            stale.unlink(missing_ok=True)
    tmp = cache.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(ROWS))
    tmp.replace(cache)


def _scan_all() -> None:
    p01_dry.p01_ast()
    p02_functional.main()
    p03_immutability.main()
    p04_p07_effects_clock.main()
    p05_p06_web_repo.p05()
    p05_p06_web_repo.p06()
    p08_money.main()
    p09_p10_p11_imports_size_suppress.p09()
    p09_p10_p11_imports_size_suppress.p10()
    p09_p10_p11_imports_size_suppress.p11()
    p12_templates.main()
    p13_other.main()


def rows(name: str) -> list[tuple[str, str, str]]:
    """All rows of one scanner output (inventory file stem, e.g. ``p07-clock``)."""
    _run_all()
    return ROWS[name]


def scan_synthetic(root: Path) -> dict[str, list[tuple[str, str, str]]]:
    """Run every scanner against a synthetic tree (``root/src/budget_planner/...``) for self-tests."""
    import sys

    saved_rows = {k: list(v) for k, v in ROWS.items()}
    saved_attrs: list[tuple[object, str, object]] = []
    src = root / "src" / "budget_planner"
    new = {
        "ROOT": root,
        "SRC": src,
        "TEMPLATES": src / "web" / "templates",
        "STATIC": src / "web" / "static",
    }
    for name, mod in list(sys.modules.items()):
        if name.startswith("tests.architecture._scan"):
            for attr, value in new.items():
                if hasattr(mod, attr):
                    saved_attrs.append((mod, attr, getattr(mod, attr)))
                    setattr(mod, attr, value)
    try:
        ROWS.clear()
        _scan_all()
        return {k: list(v) for k, v in ROWS.items()}
    finally:
        for mod, attr, value in saved_attrs:
            setattr(mod, attr, value)
        ROWS.clear()
        ROWS.update(saved_rows)
