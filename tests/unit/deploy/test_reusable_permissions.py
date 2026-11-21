"""Callers grant every permission their reusable workflows request (T-D121). No network.

GitHub refuses to start a run (startup_failure, no job log) when a called workflow
requests more GITHUB_TOKEN permissions than the calling job grants. actionlint does
not check this, so the first drill gate failed that way.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
LEVEL = {"none": 0, "read": 1, "write": 2}
LOCAL_PREFIX = "./.github/workflows/"


def _load(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(path.read_text())
    return loaded


def _required(called: dict[str, Any]) -> dict[str, int]:
    """Highest level per scope requested anywhere in the called workflow."""
    blocks = [called.get("permissions") or {}]
    blocks += [job.get("permissions") or {} for job in called.get("jobs", {}).values()]
    required: dict[str, int] = {}
    for block in blocks:
        for scope, level in block.items():
            required[scope] = max(required.get(scope, 0), LEVEL[level])
    return required


def _calls() -> list[tuple[str, str, dict[str, Any] | None, str]]:
    """(caller file, job id, granted permissions or None for unrestricted, called file)."""
    calls = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        wf = _load(path)
        for job_id, job in wf.get("jobs", {}).items():
            uses = job.get("uses", "")
            if not uses.startswith(LOCAL_PREFIX):
                continue
            granted = job.get("permissions", wf.get("permissions"))
            calls.append((path.name, job_id, granted, uses.removeprefix(LOCAL_PREFIX)))
    return calls


def test_some_reusable_calls_exist() -> None:
    assert any(caller == "drill.yml" for caller, *_ in _calls())


@pytest.mark.parametrize(("caller", "job_id", "granted", "called"), _calls())
def test_caller_grants_what_reusable_requests(
    caller: str, job_id: str, granted: dict[str, Any] | None, called: str
) -> None:
    if granted is None:
        return  # no permissions block: repository default, not capped here
    required = _required(_load(WORKFLOWS / called))
    missing = {
        scope: level
        for scope, level in required.items()
        if LEVEL[granted.get(scope, "none")] < level
    }
    assert not missing, f"{caller}:{job_id} -> {called} lacks {missing}"
