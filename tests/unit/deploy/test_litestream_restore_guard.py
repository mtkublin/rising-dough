"""T-D156 / ADR-0122: litestream-restore.sh behaviour with a stub litestream."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "terraform" / "cloud-init" / "compose" / "litestream-restore.sh"
COMPOSE = ROOT / "terraform" / "cloud-init" / "compose" / "docker-compose.yml.tpl"
IDENTITY = "AGE-SECRET-KEY-1TESTTESTTESTTESTTESTTESTTESTTESTTESTTESTTESTTESTTEST"
GEN = "2901fbd3873a6696"  # pragma: allowlist secret

# The stub mimics `litestream restore` (0.3.14) per $STUB_RESTORE:
#   ok     write the db, log the generation       (exit 0)
#   blank  exit 0 without writing the db
#   none   "no matching backups found"            (exit 1)
#   error  replica cannot be listed               (exit 1)
STUB = """#!/bin/sh
echo "$*" >> "$STUB_CALLS"
echo "identity=$LITESTREAM_AGE_IDENTITY" >> "$STUB_CALLS"
eval "db=\\${$#}"
case "${STUB_RESTORE:-ok}" in
  ok)
    echo "level=INFO msg=\\"restoring snapshot\\" db=$db replica=s3 generation=$STUB_GEN index=0"
    printf 'SQLITE' > "$db"
    ;;
  blank) ;;
  none) echo 'level=ERROR msg="failed to run" error="no matching backups found"' >&2; exit 1 ;;
  error)
    echo 'level=ERROR msg="failed to run" error="cannot fetch generations: AccessDenied"' >&2
    exit 1
    ;;
esac
"""


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    data = tmp_path / "data"
    data.mkdir()
    key = tmp_path / "age.key"
    key.write_text(f"# comment\n{IDENTITY}\n")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "litestream"
    stub.write_text(STUB)
    stub.chmod(0o755)
    return {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "LITESTREAM_DATA_DIR": str(data),
        "LITESTREAM_AGE_KEY_FILE": str(key),
        "LITESTREAM_CONFIG": "/etc/litestream.yml",
        "APP_UID": str(os.getuid()),
        "APP_GID": str(os.getgid()),
        "STUB_CALLS": str(tmp_path / "calls.txt"),
        "STUB_GEN": GEN,
    }


def _run(env: dict[str, str], **extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["/bin/sh", str(SCRIPT)],
        env={**env, **extra},
        capture_output=True,
        text=True,
        check=False,
    )


def _report(env: dict[str, str]) -> dict[str, str]:
    path = Path(env["LITESTREAM_DATA_DIR"]) / "restore-report.json"
    data: dict[str, str] = json.loads(path.read_text())
    return data


def _calls(env: dict[str, str]) -> str:
    path = Path(env["STUB_CALLS"])
    return path.read_text() if path.exists() else ""


def test_restores_when_db_missing_and_reports_generation(env: dict[str, str]) -> None:
    res = _run(env)
    assert res.returncode == 0, res.stderr
    assert (Path(env["LITESTREAM_DATA_DIR"]) / "budget.db").read_text() == "SQLITE"
    report = _report(env)
    assert report["result"] == "restored"
    assert report["generation"] == GEN
    calls = _calls(env)
    assert "restore -config /etc/litestream.yml" in calls
    assert "-if-replica-exists" not in calls
    assert f"identity={IDENTITY}" in calls


def test_empty_replica_fails_closed_by_default(env: dict[str, str]) -> None:
    res = _run(env, STUB_RESTORE="none")
    assert res.returncode != 0
    assert "refusing to start empty" in res.stderr
    assert not (Path(env["LITESTREAM_DATA_DIR"]) / "budget.db").exists()
    assert not (Path(env["LITESTREAM_DATA_DIR"]) / "restore-report.json").exists()


def test_empty_replica_allowed_when_flag_set(env: dict[str, str]) -> None:
    res = _run(env, STUB_RESTORE="none", LITESTREAM_ALLOW_EMPTY_DB="true")
    assert res.returncode == 0, res.stderr
    assert _report(env)["result"] == "empty"
    assert not (Path(env["LITESTREAM_DATA_DIR"]) / "budget.db").exists()


def test_replica_error_fails_even_when_empty_db_allowed(env: dict[str, str]) -> None:
    res = _run(env, STUB_RESTORE="error", LITESTREAM_ALLOW_EMPTY_DB="true")
    assert res.returncode != 0
    assert "AccessDenied" in res.stderr
    assert "restore failed" in res.stderr
    assert not (Path(env["LITESTREAM_DATA_DIR"]) / "restore-report.json").exists()


def test_restore_that_leaves_no_db_fails(env: dict[str, str]) -> None:
    res = _run(env, STUB_RESTORE="blank")
    assert res.returncode != 0
    assert "missing or empty" in res.stderr


def test_present_db_is_left_alone(env: dict[str, str]) -> None:
    db = Path(env["LITESTREAM_DATA_DIR"]) / "budget.db"
    db.write_text("LIVE")
    res = _run(env)
    assert res.returncode == 0, res.stderr
    assert db.read_text() == "LIVE"
    assert _report(env)["result"] == "skipped-db-present"
    assert _calls(env) == ""


def test_rerun_keeps_the_first_report(env: dict[str, str]) -> None:
    assert _run(env).returncode == 0
    res = _run(env)
    assert res.returncode == 0, res.stderr
    report = _report(env)
    assert report["result"] == "restored"
    assert report["generation"] == GEN


def test_missing_identity_fails_before_restore(env: dict[str, str]) -> None:
    Path(env["LITESTREAM_AGE_KEY_FILE"]).write_text("# no key here\n")
    res = _run(env)
    assert res.returncode != 0
    assert "no AGE-SECRET-KEY line" in res.stderr
    assert _calls(env) == ""


def test_compose_runs_the_guard_and_passes_the_flag() -> None:
    text = COMPOSE.read_text()
    assert 'entrypoint: ["/bin/sh", "/etc/litestream-restore.sh"]' in text
    assert "/etc/budget-planner/litestream-restore.sh:/etc/litestream-restore.sh:ro" in text
    assert 'LITESTREAM_ALLOW_EMPTY_DB: "${allow_empty_db}"' in text
    assert "-if-replica-exists" not in text
