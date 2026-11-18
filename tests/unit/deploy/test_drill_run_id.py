"""Drill re-applies reuse the existing drill run id (T-D139, ADR-0116). No network."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
_spec = importlib.util.spec_from_file_location("drill_run_id", ROOT / "scripts/ci/drill_run_id.py")
assert _spec is not None and _spec.loader is not None
drill_run_id = importlib.util.module_from_spec(_spec)
sys.modules["drill_run_id"] = drill_run_id
_spec.loader.exec_module(drill_run_id)


def _load(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text())
    return loaded


def test_state_value_is_used_when_no_override() -> None:
    assert drill_run_id.resolve("", "44356288331\n") == "44356288331"


def test_override_wins_over_state() -> None:
    assert drill_run_id.resolve("44356288331", "44360554182") == "44356288331"


@pytest.mark.parametrize("bad", ["abc", "12 3", "12;rm", "-1", "1" * 21])
def test_non_digits_are_rejected(bad: str) -> None:
    with pytest.raises(drill_run_id.DrillRunIdError):
        drill_run_id.resolve(bad, "")
    with pytest.raises(drill_run_id.DrillRunIdError):
        drill_run_id.resolve("", bad)


def test_missing_id_fails_instead_of_minting_one() -> None:
    with pytest.raises(drill_run_id.DrillRunIdError):
        drill_run_id.resolve("", "")


def test_main_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    assert drill_run_id.main(["--state", "7"]) == 0
    assert capsys.readouterr().out.strip() == "7"
    assert drill_run_id.main([]) == 1


def test_rollback_reuses_the_drill_id_never_the_run_id() -> None:
    wf = _load("rollback.yml")
    apply = wf["jobs"]["apply"]["with"]
    text = (WORKFLOWS / "rollback.yml").read_text()

    assert apply["reuse_drill_run_id"] == "${{ inputs.env == 'drill' }}"
    assert apply["drill_run_id"] == "${{ inputs.env == 'drill' && inputs.drill_run_id || '' }}"
    assert "github.run_id" not in text
    inputs = wf[True]["workflow_dispatch"]["inputs"]  # type: ignore[index]
    assert inputs["drill_run_id"]["default"] == ""
    assert "^[0-9]{1,20}$" in text


def test_terraform_workflow_reads_state_and_fails_closed() -> None:
    text = (WORKFLOWS / "terraform.yml").read_text()
    inputs = _load("terraform.yml")[True]["workflow_call"]["inputs"]  # type: ignore[index]

    assert inputs["reuse_drill_run_id"]["default"] is False
    assert inputs["drill_run_id"]["default"] == ""
    assert "terraform output -raw drill_run_id" in text
    assert "scripts/ci/drill_run_id.py" in text
    assert "TF_VAR_drill_run_id=${id}" in text


@pytest.mark.parametrize("name", ["drill.yml", "restore-drill.yml"])
def test_creating_workflows_do_not_reuse(name: str) -> None:
    for job in _load(name)["jobs"].values():
        with_ = job.get("with", {})
        assert not with_.get("reuse_drill_run_id"), name
        assert "drill_run_id" not in with_, name


def test_terraform_outputs_drill_run_id() -> None:
    assert 'output "drill_run_id"' in (ROOT / "terraform" / "outputs.tf").read_text()
