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
    prod_calls = {k for k, j in jobs.items() if j.get("with", {}).get("env") == "prod"}
    # T-D155: the only other prod-env call is the tailnet cleanup, not an apply.
    assert prod_calls == {"tf-apply-prod", "tailnet-cleanup-prod"}
    assert jobs["tf-apply-prod"]["uses"] == "./.github/workflows/terraform.yml"
    assert jobs["tailnet-cleanup-prod"]["uses"] == "./.github/workflows/tailnet-cleanup.yml"
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


def _step(steps: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(s for s in steps if s["name"] == name)


def test_vm_replacement_is_detected_before_apply_without_printing_the_plan() -> None:
    """T-D155 / ADR-0121: the plan JSON holds secrets; only `replaced=` is printed."""
    job = _load("terraform.yml")["jobs"]["apply"]
    names = [s["name"] for s in job["steps"]]
    detect = names.index("Detect VM replacement")
    assert names.index("terraform plan (${{ inputs.env }})") < detect
    assert detect < names.index("terraform apply (${{ inputs.env }})")
    run = job["steps"][detect]["run"]
    assert "terraform show -json plan.bin | python3 ../scripts/ci/host_release.py replaced" in run
    assert "plan.json" not in run
    assert job["outputs"]["server_replaced"] == "${{ steps.replace.outputs.replaced }}"
    assert job["timeout-minutes"] >= 45  # 1800 s wait + plan/apply


def test_replaced_vm_waits_longer_requires_restore_and_never_rolls_back() -> None:
    steps = _load("terraform.yml")["jobs"]["apply"]["steps"]
    wait = _step(steps, "Wait for host convergence (prod)")
    assert wait["env"]["SERVER_REPLACED"] == "${{ steps.replace.outputs.replaced }}"
    assert "--timeout 1800 --require-restore" in wait["run"]
    rollback = _step(steps, "Roll back to the previous ref (prod)")
    assert "steps.replace.outputs.replaced != 'true'" in rollback["if"]
    stop = _step(steps, "Replaced VM did not converge (prod)")
    assert "steps.replace.outputs.replaced == 'true'" in stop["if"]
    assert "disaster-recovery.md" in stop["run"]


def test_release_cleans_up_the_old_prod_node_only_after_a_replacement() -> None:
    loaded: dict[Any, Any] = _load("terraform.yml")
    outputs = loaded[True]["workflow_call"]["outputs"]  # PyYAML reads `on:` as True
    assert outputs["server_replaced"]["value"] == "${{ jobs.apply.outputs.server_replaced }}"
    job = _load("release.yml")["jobs"]["tailnet-cleanup-prod"]
    assert job["needs"] == "tf-apply-prod"
    # Runs only on success of the apply (default), never with always().
    assert job["if"] == "${{ needs.tf-apply-prod.outputs.server_replaced == 'true' }}"
    assert job["with"] == {"env": "prod"}
    assert job["permissions"] == {"contents": "read"}
