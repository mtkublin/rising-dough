"""T-D157 / ADR-0127 amendment: terraform.yml drains the old host before a replacing apply.

Static, no network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "terraform.yml"
REPLACED = "steps.replace.outputs.replaced == 'true'"


def _steps() -> list[dict[str, Any]]:
    loaded: dict[Any, Any] = yaml.safe_load(WORKFLOW.read_text())
    steps: list[dict[str, Any]] = loaded["jobs"]["apply"]["steps"]
    return steps


def _index(name: str) -> int:
    return next(i for i, s in enumerate(_steps()) if s["name"] == name)


def test_drain_runs_after_detection_and_before_the_apply() -> None:
    detect = _index("Detect VM replacement")
    join = _index("Join the tailnet for the drill drain (tag:ci)")
    drain = _index("Drain the old host (VM replacement)")
    apply = _index("terraform apply (${{ inputs.env }})")

    assert detect < join < drain < apply
    assert _steps()[apply]["id"] == "apply"


def test_drain_only_on_a_replacement_and_waits_for_the_agent() -> None:
    step = _steps()[_index("Drain the old host (VM replacement)")]

    assert step["id"] == "drain"
    assert step["if"] == "${{ " + REPLACED + " }}"
    assert step["env"]["SERVER_ID"] == "${{ steps.replace.outputs.server_id }}"
    assert step["env"]["DRAIN_REQUEST"] == "${{ github.run_id }}-${{ github.run_attempt }}"
    run = step["run"]
    # The old host's status (fqdn from state, before the apply).
    assert 'url="https://$(terraform output -raw fqdn)/.well-known/bp-deploy-status.json"' in run
    assert run.index("scw_user_data.py set") < run.index("host_release.py wait-drained")
    assert '--request "${DRAIN_REQUEST}"' in run


def test_only_the_drill_drain_joins_the_tailnet() -> None:
    step = _steps()[_index("Join the tailnet for the drill drain (tag:ci)")]

    assert step["if"] == "${{ " + REPLACED + " && inputs.env == 'drill' }}"
    assert step["uses"].startswith(
        "tailscale/github-action@064b10558093f38325e838ddea35486bdc6b1d5c"
    )
    assert step["with"]["tags"] == "tag:ci"


def test_failed_drain_or_apply_undrains_the_old_host() -> None:
    steps = _steps()
    undrain = _index("Undrain the old host (drain or apply failed)")
    step = steps[undrain]

    assert _index("terraform apply (${{ inputs.env }})") < undrain
    # Review finding: a cancel or the job timeout must undrain too.
    assert "(failure() || cancelled())" in step["if"]
    assert "steps.drain.outcome == 'cancelled'" in step["if"]
    assert "steps.drain.outcome == 'success' || steps.drain.outcome == 'failure'" in step["if"]
    assert "steps.apply.outcome != 'success'" in step["if"]
    assert "scw_user_data.py delete" in step["run"]


def test_apply_job_budget_covers_the_drain() -> None:
    loaded: dict[Any, Any] = yaml.safe_load(WORKFLOW.read_text())
    assert (
        loaded["jobs"]["apply"]["timeout-minutes"] >= 55
    )  # 1800 s wait + 300 s drain + plan/apply


def test_drain_wait_matches_the_agent_settle() -> None:
    """wait-drained's 300 s default leaves room for the 30 s settle and timer runs."""
    agent = (ROOT / "terraform" / "host" / "agent" / "bp_agent.py").read_text()
    script = (ROOT / "scripts" / "ci" / "host_release.py").read_text()
    assert "DRAIN_SETTLE_S = 30" in agent
    assert 'drain.add_argument("--timeout", type=float, default=300)' in script
