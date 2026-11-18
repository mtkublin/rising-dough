"""One reviewer approval per prod release (ADR-0110, ADR-0111). Static, no network.

ADR-0111: the release is the approved `terraform apply` in environment `prod`;
there is no deploy job, so no second (reviewer-less) environment either.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"
REVIEWER_ENV = "prod"


def _load(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text())
    return loaded


def _env_name(job: dict[str, Any]) -> str:
    env = job.get("environment")
    return str(env["name"] if isinstance(env, dict) else env)


def test_release_has_exactly_one_prod_apply_and_no_deploy_job() -> None:
    jobs = _load("release.yml")["jobs"]
    prod_calls = [j for j in jobs.values() if j.get("with", {}).get("env") == "prod"]
    assert prod_calls == [jobs["tf-apply-prod"]]
    assert jobs["tf-apply-prod"]["uses"] == "./.github/workflows/terraform.yml"
    assert not any("environment" in j for j in jobs.values())


def test_terraform_apply_job_is_environment_gated() -> None:
    jobs = _load("terraform.yml")["jobs"]
    envs = [_env_name(j) for j in jobs.values() if "environment" in j]
    assert any("inputs.env" in e for e in envs)


def test_no_workflow_uses_the_reviewerless_prod_deploy_environment() -> None:
    for path in WORKFLOWS.glob("*.yml"):
        assert "prod-deploy" not in path.read_text(), path.name


def test_rollback_goes_through_the_gated_apply() -> None:
    jobs = _load("rollback.yml")["jobs"]
    assert jobs["apply"]["uses"] == "./.github/workflows/terraform.yml"
    assert jobs["apply"]["with"]["env"] == "${{ inputs.env }}"
    assert not any("environment" in j for j in jobs.values())


def test_prod_apply_waits_for_host_and_rolls_back_in_the_same_job() -> None:
    steps = _load("terraform.yml")["jobs"]["apply"]["steps"]
    names = [s["name"] for s in steps]
    wait = names.index("Wait for host convergence (prod)")
    rollback = names.index("Roll back to the previous ref (prod)")
    assert names.index("terraform apply (${{ inputs.env }})") < wait < rollback
    assert "steps.converge.outcome == 'failure'" in steps[rollback]["if"]
