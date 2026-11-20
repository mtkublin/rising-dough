"""T-D137: the CI SSH public key (`CI_SSH_PUBKEY`) reaches drill hosts only.

Static check over every workflow: a job may reference the variable only when
its environment is a fixed `drill*` one, or when each reference sits behind an
`<env> == 'drill' &&` guard (the shared `terraform.yml` plan/apply jobs also
serve prod). Terraform enforces the same rule structurally (`terraform test`).
ADR-0094, ADR-0111. No network.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
REFERENCE = re.compile(r"vars\.CI_SSH_PUBKEY")
GUARDED = re.compile(
    r"\{\{\s*(?:matrix|inputs)\.env\s*==\s*'drill'\s*&&\s*vars\.CI_SSH_PUBKEY\s*\|\|\s*''\s*\}\}"
)


def _environment_name(job: dict[Any, Any]) -> str:
    env = job.get("environment", "")
    return str(env.get("name", "")) if isinstance(env, dict) else str(env)


def _referencing_jobs() -> list[tuple[str, str, dict[Any, Any]]]:
    found = []
    for path in WORKFLOWS:
        wf: dict[Any, Any] = yaml.safe_load(path.read_text())
        for job_id, job in (wf.get("jobs") or {}).items():
            if REFERENCE.search(json.dumps(job)):
                found.append((path.name, job_id, job))
    return found


def test_no_workflow_reads_the_variable_directly_any_more() -> None:
    # T-D133: terraform.yml and restore-drill.yml get it through scripts/ci/tf_env.py
    # (`only_env="drill"`, checked in test_tf_env.py); no job may reference it itself.
    assert _referencing_jobs() == []


@pytest.mark.parametrize(("name", "job_id", "job"), _referencing_jobs())
def test_no_prod_job_references_the_ci_key(name: str, job_id: str, job: dict[Any, Any]) -> None:
    environment = _environment_name(job)
    text = json.dumps(job)
    assert environment not in {"prod", "prod-plan"}, f"{name}:{job_id} is a fixed prod job"
    if environment.startswith("drill"):
        return
    guarded = len(GUARDED.findall(text))
    assert guarded == len(REFERENCE.findall(text)) and guarded > 0, (
        f"{name}:{job_id}: shared job must guard each CI_SSH_PUBKEY use with env == 'drill'"
    )
