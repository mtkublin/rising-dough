"""T-D44: prod uptime workflow shape. No network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "uptime.yml"


def _wf() -> dict[Any, Any]:
    loaded: dict[Any, Any] = yaml.safe_load(WORKFLOW.read_text())
    return loaded


def test_runs_every_five_minutes_and_on_dispatch() -> None:
    triggers = _wf()[True]
    assert triggers["schedule"] == [{"cron": "*/5 * * * *"}]
    assert "workflow_dispatch" in triggers


def test_least_privilege_and_no_secrets() -> None:
    wf = _wf()
    assert wf["permissions"] == {"contents": "read", "issues": "write"}
    assert "environment" not in wf["jobs"]["check"]
    assert "secrets." not in WORKFLOW.read_text()


def test_checks_health_and_agent_status() -> None:
    probe = _wf()["jobs"]["check"]["steps"][0]["run"]
    assert "/health" in probe
    assert "/.well-known/bp-deploy-status.json" in probe
    assert '"failed"' in probe


def test_issue_opened_on_failure_and_closed_on_recovery() -> None:
    steps = _wf()["jobs"]["check"]["steps"]
    opener = next(s for s in steps if s["name"].startswith("Open an issue"))
    closer = next(s for s in steps if s["name"].startswith("Close the issue"))
    assert "failure()" in opener["if"]
    assert "gh issue create" in opener["run"]
    assert closer["if"] == "${{ success() }}"
    assert "gh issue close" in closer["run"]
