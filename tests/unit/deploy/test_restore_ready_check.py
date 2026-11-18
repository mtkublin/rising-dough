"""T-D40-FIX: restore-from-prod readiness probe (drill run 44330551119)."""

from __future__ import annotations

from pathlib import Path

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
