"""T-D134: every `python3 <script>.py` a workflow step runs must exist.

Paths resolve against the step's working directory (step `working-directory`,
else job `defaults.run.working-directory`, else workflow `defaults`, else the
repo root). The v3.0.0 release failed because the prod-only ref guard in
terraform.yml ran `scripts/ci/ref_guard.py` from `terraform/`. No network.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
SCRIPT = re.compile(r"\bpython3?\s+(?:-[A-Za-z]+\s+)*([^\s\"'|;&]+\.py)\b")


def _run_dir(wf: dict[Any, Any], job: dict[Any, Any], step: dict[Any, Any]) -> str:
    for scope in (
        step,
        job.get("defaults", {}).get("run", {}),
        wf.get("defaults", {}).get("run", {}),
    ):
        wd = scope.get("working-directory")
        if wd:
            return str(wd)
    return "."


def _script_calls() -> list[tuple[str, str, str]]:
    calls = []
    for path in WORKFLOWS:
        wf: dict[Any, Any] = yaml.safe_load(path.read_text())
        for job_id, job in (wf.get("jobs") or {}).items():
            for step in job.get("steps") or []:
                for script in SCRIPT.findall(str(step.get("run", ""))):
                    calls.append(
                        (
                            f"{path.name}:{job_id}:{step.get('name', '?')}",
                            _run_dir(wf, job, step),
                            script,
                        )
                    )
    return calls


CALLS = _script_calls()


def test_finds_script_calls() -> None:
    assert len(CALLS) > 10
    assert any(s.endswith("ref_guard.py") for _, _, s in CALLS)


@pytest.mark.parametrize(("where", "workdir", "script"), CALLS, ids=[c[0] for c in CALLS])
def test_script_exists_relative_to_working_directory(where: str, workdir: str, script: str) -> None:
    assert "${" not in workdir, f"{where}: cannot resolve working-directory {workdir!r}"
    assert (ROOT / workdir / script).is_file(), f"{where}: {script} not found from {workdir}/"
