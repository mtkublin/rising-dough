"""Tests for scripts/prod_db_seed.sh (T-D93, ADR-0099 exception d).

Only throwaway DBs under ``tmp_path`` are used; ``data/budget.sqlite`` is never
touched (every run passes ``--source``). ssh/scp are fake executables on PATH.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from budget_planner.db.migrate import apply_migrations

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "prod_db_seed.sh"

pytestmark = pytest.mark.skipif(shutil.which("sqlite3") is None, reason="sqlite3 CLI missing")


def _make_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    try:
        apply_migrations(conn)
        conn.execute(
            "INSERT INTO accounts(user_id, name, currency, type) "
            "VALUES (1, 'Main', 'PLN', 'checking')"
        )
        conn.commit()
    except sqlite3.Error:
        # Schema drift must not make these tests brittle: fall back to a tiny schema.
        conn.close()
        path.unlink()
        conn = sqlite3.connect(path)
        conn.executescript(
            "CREATE TABLE accounts(id INTEGER PRIMARY KEY); INSERT INTO accounts DEFAULT VALUES;"
        )
        conn.commit()
    finally:
        conn.close()
    return path


def _run(
    args: list[str], *, env_path: str | None = None, cwd: Path = REPO
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ}
    if env_path:
        env["PATH"] = env_path + os.pathsep + env["PATH"]
    return subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT), *args],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        check=False,
    )


@pytest.fixture
def fake_bin(tmp_path: Path) -> Path:
    d = tmp_path / "fakebin"
    d.mkdir()
    log = tmp_path / "calls.log"
    ssh = d / "ssh"
    ssh.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "ssh $*" >> "{log}"\n'
        "cat >/dev/null <&0 || true\n"
        'case "$*" in *"sqlite3 -readonly"*) echo "${FAKE_REMOTE_COUNT:-0}";; esac\n'
    )
    scp = d / "scp"
    scp.write_text(f'#!/usr/bin/env bash\necho "scp $*" >> "{log}"\n')
    for f in (ssh, scp):
        f.chmod(0o755)
    return d


def test_refuses_without_confirmation_flag(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "src.sqlite")
    r = _run(["--source", str(db)])
    assert r.returncode == 2
    assert "PLAN" in r.stdout
    assert "--yes-i-own-prod-data" in r.stderr


def test_default_source_is_prod_path_but_not_touched() -> None:
    text = SCRIPT.read_text()
    assert "SOURCE='data/budget.sqlite'" in text
    assert "HOST='budget-planner-prod'" in text
    # Without the flag the script exits before opening the default source.
    r = _run([])
    assert r.returncode == 2


def test_dry_run_snapshots_and_reports(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "src.sqlite")
    tmp_root = tmp_path / "tmproot"
    tmp_root.mkdir()
    env_run = subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT), "--source", str(db), "--dry-run"],  # noqa: S607
        capture_output=True,
        text=True,
        env={**os.environ, "TMPDIR": str(tmp_root)},
        cwd=REPO,
        check=False,
    )
    assert env_run.returncode == 0, env_run.stderr
    out = env_run.stdout
    assert "integrity_check=ok" in out
    assert "rows accounts=1" in out
    assert "user_version=" in out
    assert re.search(r"sha256=[0-9a-f]{64}", out)
    assert "dry-run" in out
    assert list(tmp_root.iterdir()) == []  # snapshot cleaned up


def test_missing_source_fails(tmp_path: Path) -> None:
    r = _run(["--source", str(tmp_path / "nope.sqlite"), "--dry-run"])
    assert r.returncode != 0
    assert "not found" in r.stderr


def test_full_flow_with_fake_ssh(tmp_path: Path, fake_bin: Path) -> None:
    db = _make_db(tmp_path / "src.sqlite")
    r = _run(
        ["--source", str(db), "--host", "h.example", "--yes-i-own-prod-data"],
        env_path=str(fake_bin),
    )
    assert r.returncode == 0, r.stderr
    calls = (tmp_path / "calls.log").read_text()
    assert "scp" in calls
    assert "operator@h.example:/tmp/seed.db" in calls
    assert "sudo bash -s -- " in calls
    assert calls.rstrip().splitlines()[-1].endswith(" budget.rising-dough.eu")


def test_full_flow_passes_custom_fqdn(tmp_path: Path, fake_bin: Path) -> None:
    db = _make_db(tmp_path / "src.sqlite")
    r = _run(
        ["--source", str(db), "--fqdn", "x.example.org", "--yes-i-own-prod-data"],
        env_path=str(fake_bin),
    )
    assert r.returncode == 0, r.stderr
    calls = (tmp_path / "calls.log").read_text()
    assert "sudo bash -s -- " in calls
    assert " x.example.org" in calls


def test_remote_ready_probe_uses_fqdn_not_localhost() -> None:
    text = SCRIPT.read_text()
    assert '--resolve "${FQDN}:443:127.0.0.1" "https://${FQDN}/ready"' in text
    assert "https://localhost/ready" not in text
    assert "--fqdn" in text
    assert "FQDN='budget.rising-dough.eu'" in text
    assert "docker inspect -f '{{.State.Health.Status}}' budget-planner-app" in text
    assert "docker exec budget-planner-app curl" in text


def test_aborts_when_remote_has_data(tmp_path: Path, fake_bin: Path) -> None:
    db = _make_db(tmp_path / "src.sqlite")
    env_path = str(fake_bin)
    env = {
        **os.environ,
        "PATH": env_path + os.pathsep + os.environ["PATH"],
        "FAKE_REMOTE_COUNT": "7",
    }
    r = subprocess.run(  # noqa: S603
        ["bash", str(SCRIPT), "--source", str(db), "--yes-i-own-prod-data"],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO,
        check=False,
    )
    assert r.returncode != 0
    assert "--force-overwrite" in r.stderr
    assert "scp" not in (tmp_path / "calls.log").read_text()


def test_shellcheck_clean() -> None:
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not installed")
    r = subprocess.run(  # noqa: S603
        ["shellcheck", str(SCRIPT)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stdout
