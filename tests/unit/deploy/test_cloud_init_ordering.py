"""Init-stage ordering guards for the cloud-init template (T-D87, ADR-0094)."""

from __future__ import annotations

import re
from pathlib import Path

BOOTSTRAP = (
    Path(__file__).resolve().parents[3] / "terraform" / "cloud-init" / "bootstrap.yaml.tpl"
).read_text()

SYSTEM_GROUPS = frozenset(
    [
        "operator",
        "adm",
        "sudo",
        "users",
        "staff",
        "games",
        "man",
        "mail",
        "news",
        "proxy",
        "backup",
        "list",
        "irc",
        "src",
        "shadow",
        "utmp",
        "video",
        "audio",
        "plugdev",
        "netdev",
        "lxd",
        "docker",
    ]
)


def _section(name: str) -> str:
    match = re.search(rf"^{name}:\n(.*?)(?=^\S)", BOOTSTRAP, re.S | re.M)
    assert match, name
    return match.group(1)


def _entries(section: str) -> list[str]:
    return [e for e in re.split(r"(?m)^  - ", section) if e.strip()]


def test_non_root_owned_write_files_are_deferred() -> None:
    entries = [e for e in _entries(_section("write_files")) if e.startswith("path:")]
    assert entries
    for entry in entries:
        owner = re.search(r"(?m)^    owner: (\S+)", entry)
        if owner and set(owner.group(1).split(":")) != {"root"}:
            assert re.search(r"(?m)^    defer: true$", entry), entry.splitlines()[0]


def test_app_files_are_agent_managed_not_cloud_init() -> None:
    # ADR-0111: compose, Caddy, Litestream and secrets files come from bp-config.
    assert not any("/etc/budget-planner/" in e for e in _entries(_section("write_files")))


def test_users_named_like_system_groups_avoid_group_collision() -> None:
    entries = [e for e in _entries(_section("users")) if e.startswith("name:")]
    assert entries
    for entry in entries:
        match = re.match(r"name: (\S+)", entry)
        assert match
        if match.group(1) in SYSTEM_GROUPS:
            assert "no_user_group: true" in entry or "primary_group:" in entry, match.group(1)
