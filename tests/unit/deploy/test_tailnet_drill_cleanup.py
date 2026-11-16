"""T-D124 / ADR-0101: every drill destroy path removes the drill's tailnet node. No network."""

from __future__ import annotations

import importlib.util
import sys
import urllib.error
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
SCRIPT = ROOT / "scripts" / "tailnet_drill_cleanup.py"
# (workflow, destroy job that the cleanup job must follow)
DESTROY_PATHS = [
    ("drill.yml", "teardown"),
    ("drill-destroy.yml", "destroy"),
    ("drill-sweeper.yml", "destroy"),
]


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tailnet_drill_cleanup", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cleanup = _load_script()


def _job(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text())
    job: dict[str, Any] = loaded["jobs"]["tailnet-cleanup"]
    return job


@pytest.mark.parametrize(("name", "destroy_job"), DESTROY_PATHS)
def test_destroy_path_has_cleanup_after_destroy(name: str, destroy_job: str) -> None:
    job = _job(name)

    assert job["needs"] == destroy_job
    # Runs even when destroy failed (the node may exist) but not when destroy never ran.
    condition = " ".join(str(job["if"]).split())
    assert "always()" in condition
    assert f"needs.{destroy_job}.result != 'skipped'" in condition
    assert job["environment"] == "drill-teardown"
    assert job["permissions"] == {"contents": "read"}
    # No terraform.yml reusable call: a plain job that runs the shared script.
    runs = "\n".join(str(s.get("run", "")) for s in job["steps"])
    assert "scripts/tailnet_drill_cleanup.py" in runs
    env = {k: v for s in job["steps"] for k, v in (s.get("env") or {}).items()}
    assert env["TS_CLEANUP_CLIENT_ID"] == "${{ secrets.TS_CLEANUP_CLIENT_ID }}"
    assert env["TS_CLEANUP_SECRET"] == "${{ secrets.TS_CLEANUP_SECRET }}"  # noqa: S105
    uses = [str(s["uses"]) for s in job["steps"] if "uses" in s]
    assert all("@" in u and len(u.split("@")[1].split()[0]) == 40 for u in uses)


def test_script_filters_on_tag_drill_and_hostname() -> None:
    text = SCRIPT.read_text()

    assert 'DRILL_TAG = "tag:drill"' in text
    assert "budget-planner-drill(-[0-9]+)?" in text
    assert "print(token" not in text


def _device(hostname: str, tags: list[str] | None) -> dict[str, Any]:
    return {"id": hostname, "hostname": hostname, "tags": tags}


@pytest.mark.parametrize(
    ("hostname", "tags", "expected"),
    [
        ("budget-planner-drill", ["tag:drill"], True),
        ("budget-planner-drill-1", ["tag:drill"], True),
        ("budget-planner-drill-12", ["tag:drill", "tag:other"], True),
        ("budget-planner-drill", ["tag:ci"], False),
        ("budget-planner-drill", [], False),
        ("budget-planner-drill", None, False),
        ("budget-planner", ["tag:drill"], False),
        ("budget-planner-drill-x", ["tag:drill"], False),
        ("budget-planner-drill-1-extra", ["tag:drill"], False),
        ("my-laptop", ["tag:drill"], False),
    ],
)
def test_is_drill_device(hostname: str, tags: list[str] | None, expected: bool) -> None:
    assert cleanup.is_drill_device(_device(hostname, tags)) is expected


def test_never_selects_non_drill_tags() -> None:
    devices = [
        _device("budget-planner-drill", ["tag:drill"]),
        _device("budget-planner", ["tag:other"]),
        _device("budget-planner-drill-1", ["tag:ci"]),
        _device("laptop", None),
    ]

    assert [d["id"] for d in cleanup.select_drill_devices(devices)] == ["budget-planner-drill"]


def test_hostname_falls_back_to_first_label_of_name() -> None:
    device = {"id": "1", "name": "budget-planner-drill-2.tail1234.ts.net", "tags": ["tag:drill"]}

    assert cleanup.is_drill_device(device) is True


def test_main_warns_and_succeeds_without_secrets(capsys: pytest.CaptureFixture[str]) -> None:
    assert cleanup.main({}) == 0
    assert "::warning::" in capsys.readouterr().out


def test_cleanup_deletes_only_matches_and_hides_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, str]] = []

    def fake(method: str, url: str, **kwargs: Any) -> Any:
        calls.append((method, url))
        if url.endswith("/oauth/token"):
            return {"access_token": "SECRET-TOKEN"}
        if method == "GET":
            return {
                "devices": [
                    {"id": "a1", "hostname": "budget-planner-drill", "tags": ["tag:drill"]},
                    {"id": "b2", "hostname": "budget-planner-drill-1", "tags": ["tag:drill"]},
                    {"id": "c3", "hostname": "budget-planner-drill", "tags": ["tag:ci"]},
                ]
            }
        return {}

    monkeypatch.setattr(cleanup, "_request", fake)

    assert cleanup.main({"TS_CLEANUP_CLIENT_ID": "id", "TS_CLEANUP_SECRET": "sec"}) == 0
    deletes = [u for m, u in calls if m == "DELETE"]
    assert deletes == [f"{cleanup.API}/device/a1", f"{cleanup.API}/device/b2"]
    assert "SECRET-TOKEN" not in capsys.readouterr().out


def test_cleanup_is_idempotent_when_nothing_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(method: str, url: str, **kwargs: Any) -> Any:
        assert method != "DELETE"
        return {"access_token": "t"} if url.endswith("/oauth/token") else {"devices": []}

    monkeypatch.setattr(cleanup, "_request", fake)

    assert cleanup.cleanup("id", "sec") == 0


def test_failed_delete_is_a_warning_not_an_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake(method: str, url: str, **kwargs: Any) -> Any:
        if url.endswith("/oauth/token"):
            return {"access_token": "t"}
        if method == "GET":
            return {"devices": [_device("budget-planner-drill", ["tag:drill"])]}
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(cleanup, "_request", fake)

    assert cleanup.main({"TS_CLEANUP_CLIENT_ID": "id", "TS_CLEANUP_SECRET": "sec"}) == 0
    assert "::warning::" in capsys.readouterr().out
