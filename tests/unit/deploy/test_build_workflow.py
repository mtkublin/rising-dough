"""Static assertions on .github/workflows/build.yml (T-D76, ADR-0037 §2). No network."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUILD_WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
PUSH_BRANCHES = re.compile(r"^  push:\n(?:    .*\n)*?    branches: \[([^\]]*)\]", re.MULTILINE)
MAIN_TAG_GATE = "type=raw,value=main,enable={{is_default_branch}}"


def _push_branches(workflow: str) -> set[str]:
    match = PUSH_BRANCHES.search(workflow)
    assert match, "expected a push.branches list in build.yml"
    return {name.strip() for name in match.group(1).split(",")}


def test_push_trigger_builds_main_and_v3() -> None:
    workflow = BUILD_WORKFLOW.read_text()

    assert {"main", "v3"} <= _push_branches(workflow)


def test_main_tag_stays_gated_by_default_branch() -> None:
    workflow = BUILD_WORKFLOW.read_text()

    assert MAIN_TAG_GATE in workflow
    assert workflow.count("value=main") == 1
