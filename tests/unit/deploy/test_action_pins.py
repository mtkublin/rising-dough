"""T-D133: every third-party action is pinned to a commit SHA, one SHA per action. No network.

Dependabot is off (T-D130), so pins are reviewed by hand; a second SHA for the same
action means the workflows drifted (setup-uv and setup-buildx did before T-D133).
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FILES = sorted(
    [*(ROOT / ".github/workflows").glob("*.yml"), *(ROOT / ".github/actions").glob("**/*.yml")]
)
USES = re.compile(r"^\s*-?\s*uses:\s*(?P<ref>\S+)(?P<rest>.*)$")
PINNED = re.compile(r"^(?P<action>[\w.-]+/[\w./-]+)@(?P<sha>[0-9a-f]{40})$")


def _remote_uses() -> list[tuple[str, str]]:
    """(location, `owner/repo[/path]@ref`) for every non-local `uses:` line."""
    found = []
    for path in FILES:
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            match = USES.match(line)
            if match and not match["ref"].startswith("./"):
                found.append((f"{path.relative_to(ROOT)}:{number}", match["ref"]))
    return found


def test_finds_remote_actions() -> None:
    assert len(_remote_uses()) > 20


def test_every_action_is_pinned_to_a_40_hex_sha() -> None:
    unpinned = [f"{where}: {ref}" for where, ref in _remote_uses() if not PINNED.match(ref)]
    assert not unpinned, "pin to a full commit SHA:\n" + "\n".join(unpinned)


def test_each_action_uses_exactly_one_sha() -> None:
    shas: dict[str, set[str]] = defaultdict(set)
    for _, ref in _remote_uses():
        match = PINNED.match(ref)
        if match:
            shas[match["action"]].add(match["sha"])
    drifted = {action: sorted(found) for action, found in shas.items() if len(found) > 1}
    assert not drifted, f"align to one SHA per action: {drifted}"


def test_pins_carry_a_version_comment() -> None:
    bare = []
    for path in FILES:
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            match = USES.match(line)
            if match and PINNED.match(match["ref"]) and "#" not in match["rest"]:
                bare.append(f"{path.relative_to(ROOT)}:{number}")
    assert not bare, f"add a '# vX.Y.Z' comment: {bare}"
