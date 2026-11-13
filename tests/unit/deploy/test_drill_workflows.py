"""Static assertions on the drill pipeline workflows (T-D90, ADR-0099). No network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
DRILL_FILES = ("drill.yml", "drill-sweeper.yml", "drill-destroy.yml")


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

    assert "needs" not in jobs["gate-start"]
    assert str(jobs["gate-start"]["if"]) == "${{ inputs.mode == 'gate' }}"
    assert "inputs.mode == 'gate'" in str(jobs["gate-result"]["if"])


def test_destroy_is_dispatch_only() -> None:
    triggers = _triggers("drill-destroy.yml")
    job = _load("drill-destroy.yml")["jobs"]["destroy"]

    assert set(triggers) == {"workflow_dispatch"}
    assert job["with"] == {
        "env": "drill",
        "image_tag": "sha-0000000",
        "destroy": True,
    }


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
