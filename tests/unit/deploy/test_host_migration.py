"""One-time host migration to Terraform-declared host state (T-D129f, ADR-0111).

The migration script installs the same fixed bootstrap that cloud-init writes on
new VMs, so its file bodies must not drift from the cloud-init template.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "terraform/cloud-init/bootstrap.yaml.tpl"
SCRIPT = ROOT / "terraform/host/migrate/adr-0111-install-agent.sh"
BOOTSTRAP_FILES = (
    ("/usr/local/sbin/bp-agent-loader", "0755"),
    ("/etc/systemd/system/bp-converge.service", "0644"),
    ("/etc/systemd/system/bp-converge.timer", "0644"),
    ("/etc/systemd/system/bp-metadata-guard.service", "0644"),
)


def _template_body(path: str) -> str:
    text = TEMPLATE.read_text()
    start = text.index(f"  - path: {path}\n")
    content = text.index("    content: |\n", start) + len("    content: |\n")
    lines: list[str] = []
    for line in text[content:].splitlines():
        if line and not line.startswith("      "):
            break
        lines.append(line[6:])
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n"


def _script_body(path: str, mode: str) -> str:
    match = re.search(
        rf"^install_file {re.escape(path)} {mode} <<'BP_EOF'\n(.*?)^BP_EOF$",
        SCRIPT.read_text(),
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, path
    return match.group(1)


@pytest.mark.parametrize(("path", "mode"), BOOTSTRAP_FILES)
def test_script_installs_the_cloud_init_bootstrap_verbatim(path: str, mode: str) -> None:
    assert _script_body(path, mode) == _template_body(path)


def test_script_enables_guard_and_timer_and_removes_the_deploy_path() -> None:
    text = SCRIPT.read_text()

    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text
    assert "systemctl enable --now bp-metadata-guard.service" in text
    assert "systemctl enable --now bp-converge.timer" in text
    assert "userdel --remove deploy" in text
    assert "rm -f /usr/local/bin/deploy-budget-planner" in text
