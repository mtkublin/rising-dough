"""Prod baseline for the upgrade drill gate: `scripts/ci/prod_baseline.py` (T-Q306a, ADR-0149)."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/ci"))  # prod_baseline imports its sibling host_release
_spec = importlib.util.spec_from_file_location(
    "prod_baseline", ROOT / "scripts/ci/prod_baseline.py"
)
assert _spec is not None
assert _spec.loader is not None
pb: Any = importlib.util.module_from_spec(_spec)
sys.modules["prod_baseline"] = pb
_spec.loader.exec_module(pb)

FIX = Path(__file__).parent / "fixtures" / "prod_baseline"
DEPLOYMENTS = json.loads((FIX / "deployments.json").read_text())
STATUSES = json.loads((FIX / "statuses.json").read_text())

IMAGE = "ghcr.io/o/budget-planner"
DIGEST = "sha256:" + "d" * 64


def _statuses(overrides: Mapping[str, object] | None = None) -> Callable[[int], object]:
    table = {**STATUSES, **(overrides or {})}
    return lambda dep_id: table[str(dep_id)]


def _resolve(
    deployments: object = DEPLOYMENTS,
    overrides: Mapping[str, object] | None = None,
    ancestor: bool = True,
    digest: str = DIGEST,
) -> Any:
    return pb.resolve_baseline(
        deployments,
        _statuses(overrides),
        image=IMAGE,
        main_ref="origin/main",
        is_ancestor=lambda _tag: ancestor,
        inspect=lambda _ref: f'"{digest}"\n',
    )


def test_newest_success_wins() -> None:
    got = _resolve(overrides={"3003": [{"state": "success"}]})
    assert got.output_lines() == (
        "tag=v3.1.3\nsha=3333333333333333333333333333333333333333\n"
        f"image_ref={IMAGE}:v3.1.3@{DIGEST}\n"
    )


@pytest.mark.parametrize("state", ["failure", "error", "inactive", "in_progress"])
def test_unfinished_newest_falls_back_to_v312(state: str) -> None:
    got = _resolve(overrides={"3003": [{"state": state}]})
    assert got.tag == "v3.1.2"
    assert got.image_ref == f"{IMAGE}:v3.1.2@{DIGEST}"


def test_v311_tagged_but_never_deployed_is_skipped() -> None:
    only = [d for d in DEPLOYMENTS if d["id"] in (3002, 3001)]
    assert _resolve(deployments=only).tag == "v3.1.2"


def test_only_latest_status_counts() -> None:
    # v3.0.8 once succeeded but its latest status is `inactive` (superseded).
    only_old = [d for d in DEPLOYMENTS if d["id"] == 3000]
    with pytest.raises(pb.BaselineError, match="no successful deployment"):
        _resolve(deployments=only_old)


def test_no_success_at_all() -> None:
    failed = {str(d["id"]): [{"state": "failure"}] for d in DEPLOYMENTS}
    with pytest.raises(pb.BaselineError, match="no successful deployment to the 'prod'"):
        _resolve(overrides=failed)


def test_empty_deployments_and_empty_statuses() -> None:
    with pytest.raises(pb.BaselineError, match="no successful deployment"):
        _resolve(deployments=[])
    with pytest.raises(pb.BaselineError, match="no successful deployment"):
        _resolve(overrides={str(d["id"]): [] for d in DEPLOYMENTS})


def test_tag_not_ancestor_of_main() -> None:
    with pytest.raises(
        pb.BaselineError, match=r"prod tag v3\.1\.2 is not an ancestor of origin/main"
    ):
        _resolve(ancestor=False)


@pytest.mark.parametrize("digest", ["", "null", "sha256:abc"])
def test_missing_digest(digest: str) -> None:
    with pytest.raises(pb.BaselineError, match="cannot resolve image digest"):
        _resolve(digest=digest)


def _api(path: str) -> object:
    if path.startswith("repos/O/r/deployments?environment=prod"):
        return DEPLOYMENTS
    dep_id = path.split("/deployments/")[1].split("/", maxsplit=1)[0]
    return STATUSES[dep_id]


def test_main_writes_github_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    rc = pb.main(
        ["--repo", "O/r"],
        api=_api,
        is_ancestor=lambda _t, _m: True,
        inspect=lambda _r: DIGEST,
    )
    assert rc == 0
    assert out.read_text() == (
        "tag=v3.1.2\nsha=2222222222222222222222222222222222222222\n"
        f"image_ref=ghcr.io/o/budget-planner:v3.1.2@{DIGEST}\n"
    )


def test_main_fails_closed(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    rc = pb.main(
        ["--repo", "O/r"],
        api=_api,
        is_ancestor=lambda _t, _m: False,
        inspect=lambda _r: DIGEST,
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == "prod_baseline: prod tag v3.1.2 is not an ancestor of origin/main\n"
