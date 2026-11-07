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

    assert triggers["push"]["branches"] == ["**-deploy"]
    assert triggers["pull_request"]["branches"] == ["main"]
    inputs = triggers["workflow_dispatch"]["inputs"]
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

    assert jobs["ci"]["if"] == "github.event_name != 'pull_request'"
    assert jobs["build"]["needs"] == "ci"
    assert jobs["apply"]["uses"] == "./.github/workflows/terraform.yml"
    assert "build" in jobs["apply"]["needs"]
    with_ = jobs["apply"]["with"]
    assert with_["env"] == "drill"
    assert "module.compute.scaleway_instance_server.app" in with_["replace"]
    assert "tailscale_tailnet_key.vm" in with_["replace"]
    assert "drill_expires_at" in with_
    assert jobs["smoke"]["needs"] == "apply"


def test_pr_path_has_always_teardown_with_destroy() -> None:
    teardown = _load("drill.yml")["jobs"]["teardown"]
    condition = " ".join(str(teardown["if"]).split())

    assert teardown["uses"] == "./.github/workflows/terraform.yml"
    assert teardown["with"]["env"] == "drill"
    assert teardown["with"]["destroy"] is True
    assert "always()" in condition
    assert "github.event_name == 'pull_request'" in condition
    # Runs after a failed apply/smoke, but only when apply was attempted.
    assert "needs.apply.result != 'skipped'" in condition
    assert set(teardown["needs"]) == {"apply", "smoke"}


def test_sweeper_runs_every_15_minutes_and_destroys_conditionally() -> None:
    triggers = _triggers("drill-sweeper.yml")
    jobs = _load("drill-sweeper.yml")["jobs"]

    assert triggers["schedule"] == [{"cron": "*/15 * * * *"}]
    assert "workflow_dispatch" in triggers
    assert jobs["check"]["environment"] == "drill"
    assert jobs["destroy"]["needs"] == "check"
    assert jobs["destroy"]["if"] == "needs.check.outputs.expired == 'true'"
    assert jobs["destroy"]["with"]["destroy"] is True
    assert jobs["destroy"]["with"]["env"] == "drill"


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
