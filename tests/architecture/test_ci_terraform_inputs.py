"""T-D70 / ADR-0093: CI passes every Terraform input as TF_VAR_* (no tfvars, no network)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (ROOT / ".github/workflows/terraform.yml",)
_ENV_SCRIPT = ROOT / "scripts/ci/tf_env.py"
_env_spec = importlib.util.spec_from_file_location("tf_env", _ENV_SCRIPT)
assert _env_spec is not None and _env_spec.loader is not None
tf_env = importlib.util.module_from_spec(_env_spec)
sys.modules["tf_env"] = tf_env
_env_spec.loader.exec_module(tf_env)
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
    assert {"env", "scaleway_project_id", "ghcr_pull_pat"} <= set(REQUIRED)
    # ADR-0135: the age pair is prod-only (validated per env), not unconditionally required.
    assert not {"litestream_age_identity", "litestream_age_recipient"} & set(REQUIRED)
    assert "scaleway_region" not in REQUIRED


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_var_file_in_run_steps(path: Path) -> None:
    for job in _load(path)["jobs"].values():
        assert not any("-var-file" in run for run in _run_steps(job))


def test_terraform_jobs_found() -> None:
    assert len(_terraform_jobs()) >= 2


@pytest.mark.parametrize(("wf", "name", "job"), _terraform_jobs())
def test_every_required_variable_has_tf_var_env(wf: str, name: str, job: dict[str, Any]) -> None:
    # T-D133: the TF_VAR_* set comes from one mapping (scripts/ci/tf_env.py) exported by
    # the terraform-env action; the image refs are step-level env set by the job itself.
    env = {f"TF_VAR_{e.var}" for e in tf_env.ENTRIES} | set(job.get("env", {}))
    for step in job.get("steps", []):
        env |= set(step.get("env", {}))
    missing = [v for v in REQUIRED if f"TF_VAR_{v}" not in env]
    assert not missing, f"{wf}:{name} lacks TF_VAR_ for {missing}"
    uses = [s.get("uses", "") for s in job.get("steps", [])]
    assert "./.github/actions/terraform-env" in uses
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
