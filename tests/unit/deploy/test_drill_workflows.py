"""Static assertions on the drill pipeline workflows (T-D90, ADR-0099). No network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
DRILL_FILES = ("drill.yml", "drill-sweeper.yml", "drill-destroy.yml", "replace-rehearsal.yml")


def _load(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text())
    return loaded


def _triggers(name: str) -> dict[str, Any]:
    wf: dict[Any, Any] = _load(name)
    # PyYAML parses the bare key `on` as boolean True.
    triggers: dict[str, Any] = wf[True] if True in wf else wf["on"]
    return triggers


def test_drill_triggers() -> None:
    triggers = _triggers("drill.yml")

    # T-D98: manual only; no push and no pull_request trigger.
    assert set(triggers) == {"workflow_dispatch"}
    inputs = triggers["workflow_dispatch"]["inputs"]
    assert inputs["mode"]["default"] == "gate"
    assert inputs["mode"]["options"] == ["gate", "explore"]
    assert inputs["ttl_minutes"]["default"] == 60
    assert inputs["keep"]["default"] is True
    assert inputs["boot_logs"]["default"] is False


@pytest.mark.parametrize("name", [*DRILL_FILES, "restore-drill.yml"])
def test_drill_workflows_share_concurrency_group(name: str) -> None:
    concurrency = _load(name)["concurrency"]

    assert concurrency["group"] == "drill"
    assert concurrency["cancel-in-progress"] is False


@pytest.mark.parametrize("name", DRILL_FILES)
def test_drill_workflows_never_reference_prod(name: str) -> None:
    text = (WORKFLOWS / name).read_text()
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))

    assert "prod" not in code.replace("production", "")
    assert "env: drill" in code or name == "drill-sweeper.yml"


def test_drill_pipeline_chain_and_replace() -> None:
    jobs = _load("drill.yml")["jobs"]

    assert "if" not in jobs["ci"]
    assert jobs["build"]["needs"] == "ci"
    assert jobs["apply"]["uses"] == "./.github/workflows/terraform.yml"
    assert "build" in jobs["apply"]["needs"]
    with_ = jobs["apply"]["with"]
    assert with_["env"] == "drill"
    assert "module.compute.scaleway_instance_server.app" in with_["replace"]
    assert "tailscale_tailnet_key.vm" in with_["replace"]
    assert "drill_expires_at" in with_
    assert jobs["smoke"]["needs"] == "apply"


def test_gate_mode_has_always_teardown_with_destroy() -> None:
    teardown = _load("drill.yml")["jobs"]["teardown"]
    condition = " ".join(str(teardown["if"]).split())

    assert teardown["uses"] == "./.github/workflows/terraform.yml"
    assert teardown["with"]["env"] == "drill"
    assert teardown["with"]["destroy"] is True
    assert "always()" in condition
    # Gate mode is torn down regardless of `keep`.
    assert "inputs.mode == 'gate' || !inputs.keep" in condition
    # Runs after a failed apply/smoke, but only when apply was attempted.
    assert "needs.apply.result != 'skipped'" in condition
    assert set(teardown["needs"]) == {"apply", "smoke"}


def test_sweeper_runs_every_15_minutes_and_destroys_conditionally() -> None:
    triggers = _triggers("drill-sweeper.yml")
    jobs = _load("drill-sweeper.yml")["jobs"]

    assert triggers["schedule"] == [{"cron": "*/15 * * * *"}]
    assert "workflow_dispatch" in triggers
    assert jobs["check"]["environment"] == "drill-teardown"
    assert jobs["destroy"]["needs"] == "check"
    assert jobs["destroy"]["if"] == "needs.check.outputs.expired == 'true'"
    assert jobs["destroy"]["with"]["destroy"] is True
    assert jobs["destroy"]["with"]["env"] == "drill"


def test_gate_status_jobs_post_drill_gate_on_built_sha() -> None:
    wf = _load("drill.yml")
    jobs = wf["jobs"]

    # Only the two status jobs may write statuses; the workflow default stays read-only.
    assert wf["permissions"] == {"contents": "read"}
    for name in ("gate-start", "gate-result"):
        assert jobs[name]["permissions"] == {"statuses": "write"}
        assert "inputs.mode == 'gate'" in str(jobs[name]["if"])
        env = jobs[name]["env"]
        assert env["SHA"] == "${{ github.sha }}"
        run = "\n".join(str(s.get("run", "")) for s in jobs[name]["steps"])
        assert "repos/${REPO}/statuses/${SHA}" in run
        assert "context=drill-gate" in run
        assert "GITHUB_STEP_SUMMARY" in run
    assert sum("statuses" in (j.get("permissions") or {}) for j in jobs.values()) == 2


def test_gate_result_reflects_apply_and_smoke_only() -> None:
    result = _load("drill.yml")["jobs"]["gate-result"]
    run = "\n".join(str(s.get("run", "")) for s in result["steps"])

    assert set(result["needs"]) == {"apply", "smoke"}  # not teardown
    assert "always()" in str(result["if"])
    assert '[ "${APPLY_RESULT}" = "success" ] && [ "${SMOKE_RESULT}" = "success" ]' in run
    assert "state=failure" in run


def test_gate_start_has_no_dependencies_and_explore_posts_nothing() -> None:
    jobs = _load("drill.yml")["jobs"]

    assert jobs["gate-start"]["needs"] == "drill-lock"
    assert str(jobs["gate-start"]["if"]) == "${{ inputs.mode == 'gate' }}"
    assert "inputs.mode == 'gate'" in str(jobs["gate-result"]["if"])


def test_destroy_is_dispatch_only() -> None:
    triggers = _triggers("drill-destroy.yml")
    job = _load("drill-destroy.yml")["jobs"]["destroy"]

    assert set(triggers) == {"workflow_dispatch"}
    assert job["with"] == {"env": "drill", "destroy": True}


def test_terraform_workflow_drill_only_inputs_are_gated() -> None:
    wf = _load("terraform.yml")
    inputs = _triggers("terraform.yml")["workflow_call"]["inputs"]
    env = wf["jobs"]["apply"]["env"]

    assert inputs["drill_expires_at"]["default"] == ""
    assert inputs["boot_log_upload"]["default"] is False
    assert "inputs.env == 'drill'" in env["TF_VAR_drill_expires_at"]
    assert "inputs.env == 'drill'" in env["TF_VAR_boot_log_upload"]


def test_drill_apply_is_gated_and_teardown_paths_are_not() -> None:
    """ADR-0101: apply -> `drill` (reviewers); destroy, plan, smoke -> ungated envs."""
    tf = _load("terraform.yml")["jobs"]
    apply_env = str(tf["apply"]["environment"]["name"])

    # Non-destroy drill (and any prod) apply resolves to inputs.env (gated).
    assert apply_env.endswith("|| inputs.env }}")
    # Drill destroy never waits for approval.
    assert "inputs.destroy && inputs.env == 'drill'" in apply_env
    assert "'drill-teardown'" in apply_env
    assert "'drill-plan'" in tf["plan"]["environment"]
    assert "'prod-plan'" in tf["plan"]["environment"]

    drill = _load("drill.yml")["jobs"]
    assert drill["smoke"]["environment"]["name"] == "drill-teardown"
    assert drill["teardown"]["with"]["destroy"] is True  # -> drill-teardown via terraform.yml
    assert "environment" not in drill["apply"]  # gate lives in terraform.yml's apply job


def test_no_drill_workflow_uses_gated_drill_environment_for_teardown() -> None:
    for name in ("drill-sweeper.yml", "drill-destroy.yml"):
        text = (WORKFLOWS / name).read_text()
        code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
        assert "environment: drill\n" not in code


def test_restore_drill_uses_the_shared_terraform_jobs() -> None:
    """T-D133: apply and destroy are terraform.yml calls; restore/verify/evidence stay local."""
    jobs = _load("restore-drill.yml")["jobs"]

    assert jobs["apply"]["uses"] == "./.github/workflows/terraform.yml"
    assert jobs["apply"]["with"]["env"] == "drill"
    assert jobs["apply"]["with"]["image_ref"] == "${{ needs.image.outputs.ref }}"
    assert "destroy" not in jobs["apply"]["with"]
    assert set(jobs["apply"]["needs"]) == {"drill-lock", "image"}
    assert jobs["destroy"]["uses"] == "./.github/workflows/terraform.yml"
    assert jobs["destroy"]["with"] == {"env": "drill", "destroy": True}
    # Destroy always runs once apply was attempted, even after a failed restore.
    assert "always()" in jobs["destroy"]["if"]
    assert "needs.apply.result != 'skipped'" in jobs["destroy"]["if"]
    assert set(jobs["destroy"]["needs"]) == {"apply", "restore-drill"}
    # The restore job no longer runs Terraform itself (the gate stays on the apply job).
    local = "\n".join(str(s.get("run", "")) for s in jobs["restore-drill"]["steps"])
    assert "terraform " not in local
    assert jobs["restore-drill"]["environment"] == "drill"
    assert jobs["verify-destroy"]["needs"] == "destroy"
    assert jobs["tailnet-cleanup"]["uses"] == "./.github/workflows/tailnet-cleanup.yml"
    assert set(jobs["report"]["needs"]) >= {"restore-drill", "destroy", "verify-destroy"}


def _apply_steps() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = _load("terraform.yml")["jobs"]["apply"]["steps"]
    return steps


def _step(name_prefix: str) -> dict[str, Any]:
    return next(s for s in _apply_steps() if str(s.get("name", "")).startswith(name_prefix))


def test_terraform_ref_input_is_optional_and_empty_by_default() -> None:
    """T-Q306b / ADR-0149 section 2: apply `terraform/` from a baseline tag, off by default."""
    inputs = _triggers("terraform.yml")["workflow_call"]["inputs"]

    assert inputs["terraform_ref"]["type"] == "string"
    assert inputs["terraform_ref"]["required"] is False
    assert inputs["terraform_ref"]["default"] == ""


def test_terraform_ref_is_rejected_for_prod_and_non_tags() -> None:
    steps = _apply_steps()
    guard = _step("Guard terraform_ref")
    run = str(guard["run"])

    assert guard["if"] == "${{ inputs.terraform_ref != '' }}"
    assert '"${TARGET_ENV}" != "drill"' in run
    assert "exit 1" in run
    assert "^v(0|[1-9][0-9]*)" in run  # vMAJOR.MINOR.PATCH only
    # The ref reaches the script as env, never interpolated into it.
    assert "inputs.terraform_ref" not in run
    assert (
        _load("terraform.yml")["jobs"]["apply"]["env"]["TERRAFORM_REF"]
        == "${{ inputs.terraform_ref }}"
    )
    # The guard runs before the baseline ref is fetched.
    names = [str(s.get("name", "")) for s in steps]
    assert names.index(str(guard["name"])) < names.index(
        "Checkout terraform_ref (baseline Terraform)"
    )


def test_terraform_ref_checkout_replaces_terraform_dir_but_keeps_tooling() -> None:
    checkout = _step("Checkout terraform_ref")
    use = _step("Use terraform/ from terraform_ref")
    run = str(use["run"])

    for step in (checkout, use):
        assert "inputs.terraform_ref != ''" in step["if"]
        assert "inputs.env == 'drill'" in step["if"]
    assert checkout["with"]["ref"] == "refs/tags/${{ inputs.terraform_ref }}"
    assert checkout["with"]["path"] == "terraform-baseline"
    assert checkout["with"]["persist-credentials"] is False
    # terraform/ comes from the checked-out ref; terraform/scripts (CI tooling) stays at HEAD.
    assert "cp -a terraform-baseline/terraform terraform" in run
    assert run.index("mv terraform/scripts") < run.index("rm -rf terraform\n")
    assert 'mv "${RUNNER_TEMP}/tf-tooling" terraform/scripts' in run
    # Plan and apply run in terraform/, i.e. against the replaced directory.
    assert (
        _load("terraform.yml")["jobs"]["apply"]["defaults"]["run"]["working-directory"]
        == "terraform"
    )
    names = [str(s.get("name", "")) for s in _apply_steps()]
    assert names.index(str(use["name"])) < names.index("terraform init (${{ inputs.env }})")


def test_terraform_workflow_never_passes_var_flags() -> None:
    """A `-var` for a variable the baseline tag lacks is an error; TF_VAR_* is ignored."""
    jobs = _load("terraform.yml")["jobs"]
    for job in jobs.values():
        for step in job.get("steps", []):
            code = "\n".join(
                ln
                for ln in str(step.get("run", "")).splitlines()
                if not ln.lstrip().startswith("#")
            )
            assert " -var " not in code and " -var=" not in code, step.get("name")
    apply_run = str(_step("terraform plan")["run"])
    assert "TF_VAR_*" in apply_run  # the explaining comment sits next to the plan
