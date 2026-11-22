"""T-Q238 (Q-040): the prod cosign identity is pinned to main or a release tag. No network."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TF = (ROOT / "terraform" / "modules" / "compute" / "user_data.tf").read_text()
BASE = "https://github.com/o/r/.github/workflows/build.yml@"


def _local(name: str) -> str:
    raw = re.search(rf'{name}\s*=\s*"([^"]+)"', TF)
    assert raw, name
    return raw.group(1).replace("\\\\", "\\")


PREFIX = (
    _local("cosign_identity_prefix")
    .replace("${var.github_owner}", "o")
    .replace("${var.github_repo}", "r")
)
PROD = re.compile(PREFIX + _local("cosign_ref_regexp_prod"))
DRILL = re.compile(PREFIX + _local("cosign_ref_regexp_drill"))


@pytest.mark.parametrize("ref", ["refs/heads/main", "refs/tags/v3.0.5", "refs/tags/v3.1.0-rc.1"])
def test_prod_accepts_main_and_release_tags(ref: str) -> None:
    assert PROD.match(BASE + ref)


@pytest.mark.parametrize(
    "ref",
    [
        "refs/heads/attacker/evil-branch",
        "refs/heads/main-evil",
        "refs/heads/main/x",
        "refs/tags/nightly",
        "refs/pull/1/merge",
        "refs/heads/main@x",
    ],
)
def test_prod_rejects_every_other_ref(ref: str) -> None:
    assert not PROD.match(BASE + ref)


def test_prod_rejects_other_workflow_and_repo() -> None:
    assert not PROD.match("https://github.com/o/r/.github/workflows/evil.yml@refs/heads/main")
    assert not PROD.match("https://github.com/x/r/.github/workflows/build.yml@refs/heads/main")


def test_drill_accepts_branch_builds_of_the_same_workflow_only() -> None:
    assert DRILL.match(BASE + "refs/heads/feature/x")
    assert not DRILL.match("https://github.com/o/r/.github/workflows/evil.yml@refs/heads/x")


def test_identity_is_not_left_unpinned() -> None:
    assert re.search(r"identity_regexp\s*=\s*local\.cosign_identity_regexp", TF)
