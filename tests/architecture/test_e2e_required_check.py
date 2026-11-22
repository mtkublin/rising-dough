"""e2e runs on every PR to main and its job is a required check (T-Q297, ADR-0120).

The job name is the status-check context of the ``protect-main`` ruleset, so it must equal the
entry in ``scripts/check_github_settings.py`` ``REQUIRED_CHECKS`` (the operator-run G17b check).
"""

from __future__ import annotations

import ast
from typing import Any

import yaml

from tests.architecture._ratchet import REPO_ROOT

E2E_JOB_NAME = "tests/e2e (Chromium, Playwright container)"


def _workflow() -> dict[Any, Any]:
    loaded = yaml.safe_load((REPO_ROOT / ".github/workflows/e2e.yml").read_text())
    assert isinstance(loaded, dict)
    return loaded


def _required_checks() -> tuple[str, ...]:
    tree = ast.parse((REPO_ROOT / "scripts/check_github_settings.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "REQUIRED_CHECKS" for t in node.targets
        ):
            value = ast.literal_eval(node.value)
            return tuple(value)
    raise AssertionError("REQUIRED_CHECKS not found")


def test_e2e_job_name_is_a_required_check() -> None:
    jobs = _workflow()["jobs"]
    assert isinstance(jobs, dict)

    assert jobs["e2e"]["name"] == E2E_JOB_NAME
    assert E2E_JOB_NAME in _required_checks()


def test_e2e_runs_on_pull_requests_to_main() -> None:
    triggers = _workflow()[True]  # YAML 1.1 parses the key `on` as True
    assert isinstance(triggers, dict)

    assert triggers["pull_request"] == {"branches": ["main"]}
    assert "push" in triggers
    assert "workflow_dispatch" in triggers
