"""T-D136 / ADR-0113: litestream-entrypoint.sh behaviour with a stub litestream."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "terraform"
    / "cloud-init"
    / "compose"
    / "litestream-entrypoint.sh"
)
IDENTITY = "AGE-SECRET-KEY-1TESTTESTTESTTESTTESTTESTTESTTESTTESTTESTTESTTESTTEST"


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    data = tmp_path / "data"
    data.mkdir()
    (data / "budget.db").write_bytes(b"DB")
    (data / "budget.db-wal").write_bytes(b"WAL")
    meta = data / ".budget.db-litestream"
    (meta / "generations").mkdir(parents=True)
    (meta / "generation").write_text("abc\n")
    key = tmp_path / "age.key"
    key.write_text(f"# comment\n{IDENTITY}\n")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "litestream"
    stub.write_text(
        '#!/bin/sh\necho "args=$*" > "$STUB_OUT"\n'
        'echo "identity=$LITESTREAM_AGE_IDENTITY" >> "$STUB_OUT"\n'
    )
    stub.chmod(0o755)
    return {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "LITESTREAM_DATA_DIR": str(data),
        "LITESTREAM_AGE_KEY_FILE": str(key),
        "STUB_OUT": str(tmp_path / "out.txt"),
    }


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["/bin/sh", str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_first_start_resets_meta_dir_and_keeps_database(env: dict[str, str]) -> None:
    data = Path(env["LITESTREAM_DATA_DIR"])
    res = _run(env, "replicate", "-config", "/etc/litestream.yml")
    assert res.returncode == 0, res.stderr
    assert not (data / ".budget.db-litestream").exists()
    assert (data / ".litestream-age-generation").is_file()
    assert (data / "budget.db").read_bytes() == b"DB"
    assert (data / "budget.db-wal").read_bytes() == b"WAL"
    out = Path(env["STUB_OUT"]).read_text()
    assert "args=replicate -config /etc/litestream.yml" in out
    assert f"identity={IDENTITY}" in out


def test_second_start_keeps_the_new_generation(env: dict[str, str]) -> None:
    data = Path(env["LITESTREAM_DATA_DIR"])
    assert _run(env, "replicate").returncode == 0
    new_meta = data / ".budget.db-litestream"
    new_meta.mkdir(exist_ok=True)
    (new_meta / "generation").write_text("def\n")
    assert _run(env, "replicate").returncode == 0
    assert (new_meta / "generation").read_text() == "def\n"


def test_fresh_host_without_meta_dir_just_writes_the_marker(env: dict[str, str]) -> None:
    data = Path(env["LITESTREAM_DATA_DIR"])
    shutil.rmtree(data / ".budget.db-litestream")
    assert _run(env, "replicate").returncode == 0
    assert (data / ".litestream-age-generation").is_file()


def test_non_replicate_commands_never_reset(env: dict[str, str]) -> None:
    data = Path(env["LITESTREAM_DATA_DIR"])
    assert _run(env, "generations").returncode == 0
    assert (data / ".budget.db-litestream" / "generation").is_file()
    assert not (data / ".litestream-age-generation").exists()


def test_missing_identity_refuses_and_touches_nothing(env: dict[str, str]) -> None:
    data = Path(env["LITESTREAM_DATA_DIR"])
    Path(env["LITESTREAM_AGE_KEY_FILE"]).write_text("# no key\n")
    res = _run(env, "replicate")
    assert res.returncode == 1
    assert "no AGE-SECRET-KEY" in res.stderr
    assert (data / ".budget.db-litestream" / "generation").is_file()
    assert not Path(env["STUB_OUT"]).exists()
