"""T-D144 / ADR-0119: probe script behaviour (stub litestream) and wiring."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMPOSE_DIR = ROOT / "terraform" / "cloud-init" / "compose"
SCRIPT = COMPOSE_DIR / "litestream-replication-probe.sh"
IDENTITY = "AGE-SECRET-KEY-1TESTTESTTESTTESTTESTTESTTESTTESTTESTTESTTESTTESTTEST"

TABLE = """name  generation        lag  start                 end
s3    aaaaaaaaaaaaaaaa  -    2026-11-07T10:00:00Z  2026-11-07T17:52:00Z
s3    a1b2c3d4  0s   2026-11-18T14:37:00Z  2026-11-18T15:10:30Z
"""


def _run(tmp_path: Path, stub_body: str) -> dict[str, object]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "litestream"
    stub.write_text(f"#!/bin/sh\n{stub_body}\n")
    stub.chmod(0o755)
    key = tmp_path / "age.key"
    key.write_text(f"{IDENTITY}\n")
    status = tmp_path / "status"
    env = {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "LITESTREAM_AGE_KEY_FILE": str(key),
        "PROBE_STATUS_DIR": str(status),
        "PROBE_ONCE": "1",
    }
    subprocess.run(["/bin/sh", str(SCRIPT)], env=env, check=True)  # noqa: S603
    doc: dict[str, object] = json.loads((status / "status.json").read_text())
    return doc


def test_newest_end_over_all_generations(tmp_path: Path) -> None:
    doc = _run(tmp_path, f"cat <<'EOF'\n{TABLE}EOF")
    assert doc["newest_object_at"] == "2026-11-18T15:10:30Z"
    assert doc["generation"] == "a1b2c3d4"
    assert doc["error"] is None
    assert str(doc["checked_at"]).endswith("Z")


def test_command_failure_is_reported_as_error(tmp_path: Path) -> None:
    doc = _run(tmp_path, "exit 1")
    assert doc["error"] == "generations_failed"
    assert doc["newest_object_at"] is None


def test_header_only_means_no_objects(tmp_path: Path) -> None:
    doc = _run(tmp_path, "echo 'name  generation  lag  start  end'")
    assert doc["newest_object_at"] is None
    assert doc["error"] is None


def test_status_file_has_no_secret_material(tmp_path: Path) -> None:
    _run(tmp_path, f"cat <<'EOF'\n{TABLE}EOF")
    text = (tmp_path / "status" / "status.json").read_text()
    assert IDENTITY not in text


def test_compose_wires_probe_and_status_file() -> None:
    text = (COMPOSE_DIR / "docker-compose.yml.tpl").read_text()
    assert "litestream-probe:" in text
    assert 'BUDGET_REPLICATION_STATUS_FILE: "/replication/status.json"' in text
    assert "/var/lib/budget-planner/replication:/replication:ro" in text
    assert "/var/lib/budget-planner/replication:/status:rw" in text


def test_host_agent_delivers_probe_and_restarts_it() -> None:
    tf = (ROOT / "terraform" / "modules" / "compute" / "user_data.tf").read_text()
    m = re.search(
        r'litestream-replication-probe\.sh".*?restart = (\[[^\]]*\])',
        tf,
    )
    assert m is not None
    assert m.group(1) == '["litestream-probe"]'


def test_path_is_exempt_from_session_middleware() -> None:
    from budget_planner.web.middleware import auth, must_change_password  # noqa: PLC0415

    assert "/health/replication" in auth.EXEMPT_PATHS
    assert "/health/replication" in must_change_password.EXEMPT_PATHS
