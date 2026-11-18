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

# Captured from `litestream generations` of litestream/litestream:0.3.14 (T-D144
# local verification; generation id replaced). Columns: name generation lag start end.
FIXTURE = Path(__file__).parent / "fixtures" / "litestream_generations_0.3.14.txt"
REAL = FIXTURE.read_text()
# Same real format, plus an older generation with a longer lag token.
TABLE = REAL + "file  aaaaaaaaaaaaaaaa  3d2h  2026-11-07T10:00:00Z  2026-11-07T17:52:00Z\n"


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
    assert doc["newest_object_at"] == "2026-11-18T16:08:05Z"
    assert doc["generation"] == "00112233aabbccdd"
    assert doc["error"] is None
    assert str(doc["checked_at"]).endswith("Z")


def test_command_failure_is_reported_as_error(tmp_path: Path) -> None:
    doc = _run(tmp_path, "exit 1")
    assert doc["error"] == "generations_failed"
    assert doc["newest_object_at"] is None


def test_list_error_on_stdout_with_exit_0_is_reported_as_error(tmp_path: Path) -> None:
    # Real 0.3.14 behaviour: ERROR log line plus header on stdout, exit status 0.
    body = (
        'echo \'time=2026-11-18T16:09:50.184Z level=ERROR msg="cannot list generations" '
        'db=/data/budget.db replica=file error=\\"permission denied\\"\'; '
        "echo 'name  generation  lag  start  end'"
    )
    doc = _run(tmp_path, body)
    assert doc["error"] == "generations_failed"


def test_real_output_through_endpoint_logic(tmp_path: Path) -> None:
    """Probe output (real format) feeds the /health/replication verdict."""
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415

    from budget_planner.services import replication_health as rh  # noqa: PLC0415

    doc = _run(tmp_path, f"cat <<'EOF'\n{REAL}EOF")
    newest = datetime(2026, 11, 18, 16, 8, 5, tzinfo=UTC)
    assert doc["newest_object_at"] == "2026-11-18T16:08:05Z"
    limit = timedelta(hours=26)

    def verdict(hours: int) -> rh.ReplicationHealth:
        now = newest + timedelta(hours=hours)
        probe_doc = {**doc, "checked_at": (now - timedelta(minutes=1)).isoformat()}
        return rh.evaluate(json.dumps(probe_doc), now=now, max_age=limit)

    assert verdict(2).ok
    stale = verdict(30)
    assert (stale.ok, stale.status) == (False, "stale")


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
