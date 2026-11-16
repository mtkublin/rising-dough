"""T-D70 / ADR-0093: CI passes every Terraform input as TF_VAR_* (no tfvars, no network)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    ROOT / ".github/workflows/terraform.yml",
    ROOT / ".github/workflows/restore-drill.yml",
)
_SCRIPT = ROOT / "terraform/scripts/check_tf_vars.py"
_spec = importlib.util.spec_from_file_location("check_tf_vars", _SCRIPT)
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

REQUIRED = guard.required_variables((ROOT / "terraform/variables.tf").read_text())
TF_ACTIONS = ("terraform plan", "terraform apply", "terraform destroy")


def _load(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(path.read_text())
    return loaded


def _run_steps(job: dict[str, Any]) -> list[str]:
    return [s["run"] for s in job.get("steps", []) if "run" in s]


def _terraform_jobs() -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (path.name, name, job)
        for path in WORKFLOWS
        for name, job in _load(path)["jobs"].items()
        if any(a in run for run in _run_steps(job) for a in TF_ACTIONS)
    ]


def test_required_variables_parsed() -> None:
    assert {"env", "scaleway_project_id", "litestream_age_recipient"} <= set(REQUIRED)
    assert "scaleway_region" not in REQUIRED


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_var_file_in_run_steps(path: Path) -> None:
    for job in _load(path)["jobs"].values():
        assert not any("-var-file" in run for run in _run_steps(job))


def test_terraform_jobs_found() -> None:
    assert len(_terraform_jobs()) >= 3


@pytest.mark.parametrize(("wf", "name", "job"), _terraform_jobs())
def test_every_required_variable_has_tf_var_env(wf: str, name: str, job: dict[str, Any]) -> None:
    env = job.get("env", {})
    missing = [v for v in REQUIRED if f"TF_VAR_{v}" not in env]
    assert not missing, f"{wf}:{name} lacks TF_VAR_ for {missing}"
    assert "check_tf_vars.py" in "\n".join(_run_steps(job))


@pytest.mark.parametrize(("wf", "name", "job"), _terraform_jobs())
def test_terraform_runs_non_interactive(wf: str, name: str, job: dict[str, Any]) -> None:
    for run in _run_steps(job):
        for line in run.replace("\\\n", " ").splitlines():
            if line.strip().startswith(TF_ACTIONS):
                assert "-input=false" in line, f"{wf}:{name}: {line}"


def test_guard_reports_blank_variables() -> None:
    env = {"TF_VAR_env": "prod", "TF_VAR_admin_email": "  "}
    missing = guard.missing_variables(("env", "admin_email", "domain"), env)
    assert missing == ("admin_email", "domain")
