"""Host-side deploy-budget-planner forced command (T-D127, ADR-0037). No network.

The script runs as the deploy user's SSH forced command, so its real input is
SSH_ORIGINAL_COMMAND, not argv. Strict-mode IFS ($'\\n\\t') once stopped that
string from splitting on spaces, which broke `deploy <tag>` on the first
pipeline release while single-word `status` kept working.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "terraform" / "cloud-init" / "bin" / "deploy-budget-planner.tpl"

BASH = shutil.which("bash") or ""

pytestmark = pytest.mark.skipif(not BASH, reason="bash not installed")


def _render(tmp_path: Path) -> Path:
    compose_dir = tmp_path / "compose"
    compose_dir.mkdir()
    text = (
        TEMPLATE.read_text()
        .replace("${owner}", "owner")
        .replace("${app_image}", "ghcr.io/owner/budget-planner")
        .replace("${compose_dir}", str(compose_dir))
        .replace("${previous_tag_file}", str(compose_dir / "previous-tag"))
        .replace("$${", "${")
    )
    script = tmp_path / "deploy-budget-planner"
    script.write_text(text)
    script.chmod(0o755)
    return script


def _run_forced(
    script: Path, original_command: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "SSH_ORIGINAL_COMMAND": original_command}
    return subprocess.run(  # noqa: S603
        [BASH, str(script)], env=env, cwd=cwd, capture_output=True, text=True, check=False
    )


def test_forced_command_splits_on_spaces(tmp_path: Path) -> None:
    # Two words reach the `status` arity check (exit 2) instead of being one
    # unknown subcommand "status extra" (exit 1).
    result = _run_forced(_render(tmp_path), "status extra")

    assert result.returncode == 2, result.stderr


def test_forced_command_does_not_glob(tmp_path: Path) -> None:
    (tmp_path / "a").touch()
    (tmp_path / "b").touch()

    result = _run_forced(_render(tmp_path), "status *", cwd=tmp_path)

    assert result.returncode == 2, result.stderr


def test_forced_command_rejects_unknown_subcommand(tmp_path: Path) -> None:
    result = _run_forced(_render(tmp_path), "ls /")

    assert result.returncode == 1
    assert "usage:" in result.stderr


def test_deploy_with_tag_reaches_tag_validation(tmp_path: Path) -> None:
    # `deploy <tag>` must parse as subcommand + argument and reach the tag
    # check (invalid tag -> exit 2), not fall through to usage (exit 1).
    result = _run_forced(_render(tmp_path), "deploy not-a-valid-tag")

    assert result.returncode == 2, result.stderr
    assert "invalid image tag" in result.stderr
