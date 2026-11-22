"""A compose network must not change under the same name (T-Q305, ADR-0133 amendment).

Compose cannot alter an existing network that has containers attached (the v3.1.0
`edge` ipam change failed on the live host; a drill is always a fresh host and did
not see it). Any changed network definition needs a new network name.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
TPL = "terraform/cloud-init/compose/docker-compose.yml.tpl"
AGENT = ROOT / "terraform" / "host" / "agent" / "bp_agent.py"
NETWORK_HEAD = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
TOP_LEVEL = re.compile(r"^[A-Za-z]")


def network_specs(text: str) -> dict[str, str]:
    """Top-level ``networks:`` entries -> their normalised body (comments dropped)."""
    specs: dict[str, list[str]] = {}
    current: str | None = None
    inside = False
    for raw in text.splitlines():
        if TOP_LEVEL.match(raw):
            inside = raw.startswith("networks:")
            current = None
            continue
        if not inside or not raw.strip() or raw.strip().startswith("#"):
            continue
        head = NETWORK_HEAD.match(raw)
        if head:
            current = head.group(1)
            specs[current] = []
        elif current is not None:
            specs[current].append(raw.split(" #", 1)[0].strip())
    return {name: "\n".join(lines) for name, lines in specs.items()}


def changed_same_name(old: str, new: str) -> list[str]:
    old_specs, new_specs = network_specs(old), network_specs(new)
    return sorted(n for n in old_specs.keys() & new_specs.keys() if old_specs[n] != new_specs[n])


def _git(*args: str) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    res = subprocess.run(  # noqa: S603  # fixed git args, no shell
        [git, *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return res.stdout if res.returncode == 0 else None


def _latest_release_template() -> tuple[str, str] | None:
    tags = _git("tag", "--list", "v[0-9]*", "--sort=-v:refname")
    if not tags or not tags.split():
        return None
    tag = tags.split()[0]
    text = _git("show", f"{tag}:{TPL}")
    return (tag, text) if text else None


def test_network_specs_parses_names_and_bodies() -> None:
    text = (
        "services:\n  a:\n    x: 1\nnetworks:\n  # c\n  n1:\n    driver: bridge\n"
        "  n2:\n    driver: bridge\nvolumes:\n  v:\n"
    )
    assert network_specs(text) == {"n1": "driver: bridge", "n2": "driver: bridge"}


def test_same_name_with_a_changed_definition_is_flagged() -> None:
    old = "networks:\n  edge:\n    driver: bridge\n"
    ipam = "networks:\n  edge:\n    driver: bridge\n    ipam:\n      config: []\n"
    renamed = "networks:\n  edge_v2:\n    driver: bridge\n    ipam:\n      config: []\n"
    assert changed_same_name(old, ipam) == ["edge"]
    assert changed_same_name(old, renamed) == []
    assert changed_same_name(old, old) == []


def test_prod_network_definitions_are_upgradeable_from_the_latest_release() -> None:
    release = _latest_release_template()
    if release is None:
        pytest.skip("no v* tag in this checkout (shallow clone)")
    tag, old = release
    new = (ROOT / TPL).read_text()
    changed = changed_same_name(old, new)
    assert not changed, (
        f"compose network(s) {changed} changed their definition since {tag} under the same "
        "name; an existing host cannot apply that in place (T-Q305, ADR-0133 amendment): "
        "rename the network and add the old name to LEGACY_NETWORKS in "
        "terraform/host/agent/bp_agent.py"
    )


def test_a_legacy_network_is_never_a_current_network() -> None:
    match = re.search(r"^LEGACY_NETWORKS = \((.*?)\)", AGENT.read_text(), re.M)
    assert match is not None
    legacy = set(re.findall(r'"([^"]+)"', match.group(1)))
    current = {f"budget-planner_{n}" for n in network_specs((ROOT / TPL).read_text())}
    assert legacy
    assert current.isdisjoint(legacy)
