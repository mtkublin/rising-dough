"""T-D126 / ADR-0099: GHCR retention workflow + selection logic. No network."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "image-retention.yml"
_spec = importlib.util.spec_from_file_location(
    "ghcr_retention", ROOT / "scripts" / "ghcr_retention.py"
)
assert _spec and _spec.loader
ret = importlib.util.module_from_spec(_spec)
sys.modules["ghcr_retention"] = ret
_spec.loader.exec_module(ret)

NOW = datetime(2026, 12, 1, tzinfo=UTC)


def _wf() -> dict[Any, Any]:
    loaded: dict[Any, Any] = yaml.safe_load(WORKFLOW.read_text())
    return loaded


def _v(i: int, age_days: float, *tags: str, digest: str | None = None) -> Any:
    return ret.Version(i, digest or f"sha256:{i:064x}", NOW - timedelta(days=age_days), tags)


def _deleted(plan: Any) -> set[int]:
    return {v.id for v, _ in plan.delete}


def test_dry_run_input_defaults_true() -> None:
    triggers = _wf()[True]
    assert triggers["workflow_dispatch"]["inputs"]["dry_run"]["default"] is True
    assert triggers["schedule"]


def test_permissions_minimal() -> None:
    assert _wf()["permissions"] == {"contents": "read", "packages": "write"}


def test_actions_pinned_and_scheduled_runs_gated_by_variable() -> None:
    text = WORKFLOW.read_text()
    for line in text.splitlines():
        if "uses:" in line:
            assert "@" in line and len(line.split("@")[1].split()[0]) == 40
    assert "IMAGE_RETENTION_ENABLED" in text
    assert "--apply" in text


def test_workflow_states_keep_rules() -> None:
    text = WORKFLOW.read_text()
    assert "newest 20" in text and "main or v*" in text


def test_keeps_newest_20_sha_and_deletes_older() -> None:
    versions = [_v(i, 10 + i, f"sha-{i:07x}") for i in range(1, 26)]
    plan = ret.select(versions, {}, NOW)
    assert _deleted(plan) == {21, 22, 23, 24, 25}


def test_main_and_v_tags_always_kept() -> None:
    versions = [_v(1, 400, "main"), _v(2, 400, "v1.2.0", "sha-aaaaaaa"), _v(3, 400, "sha-bbbbbbb")]
    plan = ret.select(versions, {}, NOW, keep_sha=0)
    assert _deleted(plan) == {3}


def test_recent_versions_never_deleted() -> None:
    versions = [_v(1, 1), _v(2, 2, "sha256-" + "a" * 64 + ".sig")]
    assert _deleted(ret.select(versions, {}, NOW)) == set()


def test_old_untagged_deleted_but_children_of_kept_index_survive() -> None:
    index = _v(1, 30, "sha-1111111")
    child = _v(2, 30)
    stray = _v(3, 30)
    plan = ret.select([index, child, stray], {index.digest: [child.digest]}, NOW)
    assert _deleted(plan) == {3}


def test_signature_of_kept_image_kept_orphan_deleted() -> None:
    kept = _v(1, 30, "main")
    gone = _v(2, 30, "sha-2222222")
    sig_kept = _v(3, 30, f"sha256-{kept.digest.split(':')[1]}.sig")
    sig_orphan = _v(4, 30, f"sha256-{gone.digest.split(':')[1]}.sig")
    sig_unknown = _v(5, 30, "sha256-" + "f" * 64 + ".att")
    plan = ret.select([kept, gone, sig_kept, sig_orphan, sig_unknown], {}, NOW, keep_sha=0)
    assert _deleted(plan) == {2, 4, 5}


def test_unrecognised_tags_are_kept() -> None:
    assert _deleted(ret.select([_v(1, 90, "latest")], {}, NOW, keep_sha=0)) == set()


def test_parse_versions_reads_tags_and_digest() -> None:
    raw = [
        {
            "id": 7,
            "name": "sha256:abc",
            "created_at": "2026-11-01T00:00:00Z",
            "metadata": {"container": {"tags": ["main"]}},
        },
        {"id": 8, "name": "sha256:def", "created_at": "2026-11-01T00:00:00Z"},
    ]
    parsed = ret.parse_versions(raw)
    assert parsed[0].tags == ("main",) and parsed[1].tags == ()


def test_format_plan_marks_dry_run() -> None:
    plan = ret.select([_v(1, 30)], {}, NOW)
    assert "DRY RUN" in ret.format_plan(plan, apply=False)
