"""T-D40-FIX: restore-from-prod readiness probe (drill run 44330551119)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (ROOT / "terraform/cloud-init/bin/restore-from-prod.tpl").read_text()
USER_DATA = (ROOT / "terraform/modules/compute/user_data.tf").read_text()


def test_ready_probe_uses_host_name_not_localhost() -> None:
    assert "READY_HOST='${hostname}'" in SCRIPT
    assert '--resolve "$${READY_HOST}:443:127.0.0.1"' in SCRIPT
    assert "localhost" not in SCRIPT.replace("# ", "#")


def test_ready_probe_keeps_tls_verification() -> None:
    curl_lines = [ln for ln in SCRIPT.splitlines() if "curl -" in ln]
    assert curl_lines
    assert all(" -k" not in ln and "--insecure" not in ln for ln in curl_lines)


def test_ready_probe_requires_status_ready_and_db_ok() -> None:
    assert '"$${status}" == "ready"' in SCRIPT
    assert '"$${db}" == "ok"' in SCRIPT
    assert '"$${status}" == "ok"' not in SCRIPT


def test_ready_probe_logs_each_failed_attempt() -> None:
    assert "failed: $${err}" in SCRIPT


def test_hostname_passed_to_template() -> None:
    start = USER_DATA.index("restore-from-prod.tpl")
    block = USER_DATA[start : USER_DATA.index('}) : ""', start)]
    assert "hostname         = var.hostname" in block


# --- T-D40-FIX2: RETURN-trap bug (drill run 44340976282) -----------------

_OLD_PATTERN = r"""
set -euo pipefail
f() { local cfg; cfg="$(mktemp)"; trap 'rm -f -- "${cfg}"' RETURN; }
g() { :; }
main() { f; g; echo done; }
main
"""

_FIXED_PATTERN = r"""
set -euo pipefail
RESTORE_CFG=''
cleanup() {
  local rc=$?; set +e
  [[ -z "${RESTORE_CFG}" ]] || rm -f -- "${RESTORE_CFG}"
  exit "${rc}"
}
f() { RESTORE_CFG="$(mktemp)"; }
g() { :; }
main() { f; g; [[ -e "${RESTORE_CFG}" ]]; echo done; }
trap cleanup EXIT
main
"""


def _docker_usable(docker: str | None) -> bool:
    if not docker:
        return False
    probe = subprocess.run(  # noqa: S603 - fixed argv
        [docker, "info"], check=False, capture_output=True, timeout=30
    )
    return probe.returncode == 0


def _run_bash(script: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run under ubuntu:24.04 (bash 5.2, the drill host) if Docker works, else local bash."""
    file = tmp_path / "t.sh"
    file.write_text(script)
    docker = shutil.which("docker")
    if docker and _docker_usable(docker):
        mount = f"{tmp_path}:/w:ro"
        cmd = [docker, "run", "--rm", "-v", mount, "ubuntu:24.04", "bash", "/w/t.sh"]
    else:
        cmd = ["bash", str(file)]
    return subprocess.run(  # noqa: S603 - fixed argv, no user input
        cmd, capture_output=True, text=True, timeout=300, check=False
    )


def test_old_return_trap_pattern_fails_unbound(tmp_path: Path) -> None:
    res = _run_bash(_OLD_PATTERN, tmp_path)
    if res.returncode == 0:
        pytest.skip("bash on this host does not reproduce the RETURN-trap leak (bash 3.2?)")
    assert "cfg: unbound variable" in res.stderr


def test_fixed_pattern_survives_later_function_return(tmp_path: Path) -> None:
    res = _run_bash(_FIXED_PATTERN, tmp_path)
    assert res.returncode == 0, res.stderr
    assert "done" in res.stdout


def test_script_has_no_return_trap_and_cleans_cfg_on_exit() -> None:
    assert "RETURN" not in [
        w for ln in SCRIPT.splitlines() if ln.lstrip().startswith("trap") for w in ln.split()
    ]
    assert "local cfg" not in SCRIPT
    cleanup = SCRIPT[SCRIPT.index("cleanup_copies() {") : SCRIPT.index("compose()")]
    assert 'rm -f -- "$${RESTORE_CFG}"' in cleanup
    assert "trap cleanup_copies EXIT" in SCRIPT


def test_no_other_tpl_uses_return_trap() -> None:
    for tpl in (ROOT / "terraform/cloud-init/bin").glob("*.tpl"):
        assert "RETURN" not in "\n".join(
            ln for ln in tpl.read_text().splitlines() if ln.lstrip().startswith("trap")
        ), tpl.name
