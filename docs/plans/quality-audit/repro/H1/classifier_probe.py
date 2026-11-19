#!/usr/bin/env python3
"""H1 repro: drill-gate skip classifier (ADR-0121) vs. files that workflows/scripts consume.

Loads scripts/ci/drill_gate_skip.py from the repo and classifies crafted file lists, then
greps workflows for consumers of the paths the classifier calls inert.
"""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
spec = importlib.util.spec_from_file_location("gs", ROOT / "scripts/ci/drill_gate_skip.py")
gs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gs)

CASES = {
    "A docs restore-log (gates prod plaintext delete)": ["docs/plans/v3/runbooks/restore-log.md"],
    "B tests/render/render_check.py (run by terraform.yml fmt-validate)": ["tests/render/render_check.py"],
    "C tests/conftest.py (runs in release ci job)": ["tests/conftest.py"],
    "D .claude/settings.json (agent hooks)": [".claude/settings.json"],
    "E .claude/skills/x/SKILL.md (agent instructions)": [".claude/skills/orchestrator-mode/SKILL.md"],
    "F top-level CLAUDE.md": ["CLAUDE.md"],
    "G top-level LICENSE_run.sh": ["LICENSE_run.sh"],
    "H mixed docs + terraform": ["docs/a.md", "terraform/main.tf"],
    "I src package data md": ["src/budget_planner/x.md"],
    "J dot-slash prefix (API never emits)": ["./src/budget_planner/x.md"],
    "K upper-case dir": ["SRC/x.md"],
    "L empty": [],
    "M traversal": ["docs/../src/x.py"],
}
for name, paths in CASES.items():
    print(f"{gs.classify(paths)[0]:5s} {name}  {paths}")

print("\n-- workflow lines that consume 'inert' paths --")
for p in sorted((ROOT / ".github").rglob("*.yml")):
    for i, line in enumerate(p.read_text().splitlines(), 1):
        if re.search(r"tests/render|--restore-log", line):
            print(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
