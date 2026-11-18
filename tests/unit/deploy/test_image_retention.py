"""T-D126 / ADR-0099: GHCR retention workflow + selection logic. No network."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
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
_TOK = "tok"


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


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://ghcr.io/x", code, "err", None, io.BytesIO(b"{}"))  # type: ignore[arg-type]


def test_fetch_children_accepts_oci_manifest_types(monkeypatch: Any) -> None:
    seen: dict[str, str] = {}

    def fake_urlopen(req: Any, timeout: int) -> Any:
        seen["accept"] = req.get_header("Accept")
        return io.BytesIO(json.dumps({"layers": []}).encode())

    monkeypatch.setattr(ret.urllib.request, "urlopen", fake_urlopen)
    assert ret.fetch_children("o", "gh", "sha256:a", token=_TOK) == []
    assert "application/vnd.oci.image.manifest.v1+json" in seen["accept"]
    assert "application/vnd.oci.image.index.v1+json" in seen["accept"]


def test_fetch_children_404_returns_none_other_errors_raise(monkeypatch: Any) -> None:
    def raise_404(req: Any, timeout: int) -> Any:
        raise _http_error(404)

    monkeypatch.setattr(ret.urllib.request, "urlopen", raise_404)
    assert ret.fetch_children("o", "gh", "sha256:a", token=_TOK) is None

    def raise_500(req: Any, timeout: int) -> Any:
        raise _http_error(500)

    monkeypatch.setattr(ret.urllib.request, "urlopen", raise_500)
    try:
        ret.fetch_children("o", "gh", "sha256:a", token=_TOK)
    except urllib.error.HTTPError as exc:
        assert exc.code == 500
    else:
        raise AssertionError("expected HTTPError")


def test_unknown_children_keep_untagged_but_still_delete_old_sha() -> None:
    kept = _v(1, 30, "v1.0.0", "sha-1111111")
    untagged = _v(2, 30)
    old_sha = _v(3, 30, "sha-3333333")
    plan = ret.select(
        [kept, untagged, old_sha], {}, NOW, keep_sha=0, unknown_children={kept.digest}
    )
    assert _deleted(plan) == {3}
    assert "undetermined" in {v.id: why for v, why in plan.keep}[2]


def test_protected_images_and_their_signatures_survive_unknown_children() -> None:
    release = _v(1, 60, "v3.0.1", "3.0.1", "sha-4532791")
    rollback = _v(2, 60, "sha-89ac3c2")
    child = _v(3, 60)
    sig = _v(4, 60, f"sha256-{rollback.digest.split(':')[1]}.sig")
    plan = ret.select(
        [release, rollback, child, sig],
        {},
        NOW,
        keep_sha=1,
        unknown_children={release.digest, rollback.digest},
    )
    # rollback is the single newest-sha slot only by tie order; release is a v* tag.
    assert _deleted(plan) <= {2, 4}
    assert 1 not in _deleted(plan) and 3 not in _deleted(plan)


def test_rollback_image_kept_when_within_newest_sha_slots() -> None:
    rollback = _v(1, 60, "sha-89ac3c2")
    sig = _v(2, 60, f"sha256-{rollback.digest.split(':')[1]}.sig")
    plan = ret.select([rollback, sig], {}, NOW, keep_sha=1, unknown_children={rollback.digest})
    assert _deleted(plan) == set()
