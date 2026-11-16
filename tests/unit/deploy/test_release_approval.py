"""One reviewer approval per prod release (ADR-0110). Static, no network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"
REVIEWER_ENV = "prod"
DEPLOY_ENV = "prod-deploy"
DEPLOY_SECRETS = {
    "DEPLOY_SSH_PRIVATE_KEY",
    "DEPLOY_SSH_KNOWN_HOSTS",
    "PROD_HOST",
    "DRILL_HOST",
    "TS_OAUTH_CLIENT_ID",
    "TS_OAUTH_SECRET",
}


def _load(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text())
    return loaded


def _env_name(job: dict[str, Any]) -> str:
    env = job.get("environment")
    return str(env["name"] if isinstance(env, dict) else env)


def test_deploy_job_uses_prod_deploy_for_prod_and_env_for_drill() -> None:
    name = _env_name(_load("deploy.yml")["jobs"]["deploy"])
    assert "inputs.env == 'prod'" in name
    assert name.endswith("|| inputs.env }}")
    prod_branch = name.split("&&")[1].split("||")[0].strip().strip("'")
    assert prod_branch == DEPLOY_ENV
    assert prod_branch != REVIEWER_ENV


def test_release_deploys_only_after_the_approved_apply() -> None:
    jobs = _load("release.yml")["jobs"]
    assert jobs["tf-apply-prod"]["with"]["env"] == "prod"
    assert jobs["deploy-prod"]["with"]["env"] == "prod"
    assert "tf-apply-prod" in jobs["deploy-prod"]["needs"]


def test_terraform_apply_job_is_environment_gated() -> None:
    jobs = _load("terraform.yml")["jobs"]
    envs = [_env_name(j) for j in jobs.values() if "environment" in j]
    assert any("inputs.env" in e for e in envs)


def test_deploy_reads_no_secret_outside_the_deploy_set() -> None:
    text = (WORKFLOWS / "deploy.yml").read_text()
    used = {
        part.split("}}")[0].split("|")[0].strip().split()[0] for part in text.split("secrets.")[1:]
    }
    assert used <= DEPLOY_SECRETS
    assert "SCW_" not in text


def test_rollback_stays_behind_reviewers() -> None:
    jobs = _load("rollback.yml")["jobs"]
    names = [_env_name(j) for j in jobs.values() if "environment" in j]
    assert names
    assert all(DEPLOY_ENV not in n for n in names)
