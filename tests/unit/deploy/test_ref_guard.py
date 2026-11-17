"""Unit tests for scripts/ci/ref_guard.py (ADR-0109). No network, no git remote."""

# ruff: noqa: S603, S607
from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ci" / "ref_guard.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ref_guard", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load()


@pytest.mark.parametrize("tag", ["v0.0.1", "v1.2.3", "v10.20.30"])
def test_semver_tags_accepted(tag: str) -> None:
    assert guard.is_semver_tag(tag)


@pytest.mark.parametrize(
    "tag", ["1.2.3", "v1.2", "v1.2.3-rc1", "v01.2.3", "v1.2.3.4", "V1.2.3", "v1.2.3\n", ""]
)
def test_non_semver_tags_rejected(tag: str) -> None:
    assert not guard.is_semver_tag(tag)


def test_main_ref_allowed_without_ancestry_probe() -> None:
    def boom(_sha: str) -> bool:
        raise AssertionError("must not be called")

    assert guard.check_ref("refs/heads/main", boom) == "main"


def test_tag_on_main_allowed() -> None:
    assert "v1.2.3" in guard.check_ref("refs/tags/v1.2.3", lambda _s: True, "abc")


def test_tag_off_main_refused() -> None:
    with pytest.raises(guard.GuardError, match="not an ancestor"):
        guard.check_ref("refs/tags/v1.2.3", lambda _s: False, "abc")


def test_non_semver_tag_refused_before_ancestry() -> None:
    with pytest.raises(guard.GuardError, match="SemVer"):
        guard.check_ref("refs/tags/nightly", lambda _s: True)


@pytest.mark.parametrize("ref", ["refs/heads/feature", "refs/heads/main2", "refs/pull/1/merge", ""])
def test_other_refs_refused(ref: str) -> None:
    with pytest.raises(guard.GuardError, match="only from main"):
        guard.check_ref(ref, lambda _s: True)


@pytest.mark.parametrize("tag", ["sha-abcdef0", "sha-" + "a" * 40, "v1.2.3"])
def test_deploy_tag_accepted(tag: str) -> None:
    assert guard.validate_deploy_tag(tag) == tag


@pytest.mark.parametrize(
    "tag", ["main", "sha-abc", "sha-ABCDEF0", "latest", "v1.2", "sha-" + "a" * 41]
)
def test_deploy_tag_rejected(tag: str) -> None:
    with pytest.raises(guard.GuardError):
        guard.validate_deploy_tag(tag)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("v1.2.3", "v1.2.3"),
        ("sha-abcdef0", "sha-abcdef0"),
        ("abcdef0123456", "sha-abcdef0"),
    ],
)
def test_rollback_target_normalised(value: str, expected: str) -> None:
    assert guard.resolve_rollback_target(value) == expected


@pytest.mark.parametrize("value", ["", "latest", "v1.2", "xyz1234", "abc12", "$(id)", "v1.2.3;ls"])
def test_rollback_target_rejected(value: str) -> None:
    with pytest.raises(guard.GuardError):
        guard.resolve_rollback_target(value)


def test_main_cli_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    assert guard.main(["deploy-tag", "v1.0.0"]) == 0
    assert capsys.readouterr().out.strip() == "v1.0.0"
    assert guard.main(["deploy-tag", "nope"]) == 1
    assert "::error::" in capsys.readouterr().err
    assert guard.main(["ref", "--ref", "refs/heads/dev"]) == 1


def test_git_ancestry_against_a_local_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # pre-commit exports GIT_DIR/GIT_INDEX_FILE; they would point git at the outer repo.
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}

    def git(cwd: Path, *args: str) -> str:
        out = subprocess.run(
            [
                "git",
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=cwd,
            env=clean_env,
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()

    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    git(origin, "commit", "-q", "--allow-empty", "-m", "a")
    on_main = git(origin, "rev-parse", "HEAD")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(origin), "clone")
    git(clone, "checkout", "-q", "-b", "side")
    git(clone, "commit", "-q", "--allow-empty", "-m", "b")
    off_main = git(clone, "rev-parse", "HEAD")

    monkeypatch.chdir(clone)
    for key in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(key)
    assert guard.git_is_ancestor_of_main(on_main)
    assert not guard.git_is_ancestor_of_main(off_main)
