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
    ("restore-drill.yml", "destroy"),
    ("replace-rehearsal.yml", "teardown"),
]


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tailnet_drill_cleanup", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cleanup = _load_script()


def _job(name: str) -> dict[str, Any]:  # caller-side cleanup job
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
    assert job["permissions"] == {"contents": "read"}
    # T-D133: one reusable workflow serves every destroy path.
    assert job["uses"] == "./.github/workflows/tailnet-cleanup.yml"


def test_reusable_cleanup_workflow_runs_the_shared_script_ungated() -> None:
    loaded: dict[Any, Any] = yaml.safe_load((WORKFLOWS / "tailnet-cleanup.yml").read_text())
    job = loaded["jobs"]["cleanup"]

    # T-D156: drill by default; prod mode uses its own ungated environment.
    assert job["environment"] == "${{ inputs.env == 'prod' && 'prod-tailnet' || 'drill-teardown' }}"
    inputs = loaded[True]["workflow_call"]["inputs"]  # PyYAML reads `on:` as True
    assert inputs["env"]["default"] == "drill"
    assert job["permissions"] == {"contents": "read"}
    runs = "\n".join(str(s.get("run", "")) for s in job["steps"])
    assert 'scripts/tailnet_drill_cleanup.py --env "${CLEANUP_ENV}"' in runs
    env = {k: v for s in job["steps"] for k, v in (s.get("env") or {}).items()}
    assert env["TS_CLEANUP_CLIENT_ID"] == "${{ secrets.TS_CLEANUP_CLIENT_ID }}"
    assert env["TS_CLEANUP_SECRET"] == "${{ secrets.TS_CLEANUP_SECRET }}"  # noqa: S105
    # Anything but "prod" falls back to the drill mode.
    assert env["CLEANUP_ENV"] == "${{ inputs.env == 'prod' && 'prod' || 'drill' }}"
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


# --- prod mode (T-D156, ADR-0122) --------------------------------------------


def _prod(
    dev_id: str, name: str, online: bool | None, tags: list[str] | None = None
) -> dict[str, Any]:
    device: dict[str, Any] = {
        "id": dev_id,
        "hostname": "budget-planner-prod",
        "name": f"{name}.tail1234.ts.net",
        "tags": ["tag:prod"] if tags is None else tags,
    }
    if online is not None:
        device["connectedToControl"] = online
    return device


OLD = _prod("old", "budget-planner-prod", online=False)
NEW = _prod("new", "budget-planner-prod-1", online=True)


def test_prod_selects_only_offline_tag_prod_nodes() -> None:
    devices = [
        OLD,
        NEW,
        _prod("unknown", "budget-planner-prod-2", online=None),  # no field: keep
        _prod("drill", "budget-planner-prod-3", online=False, tags=["tag:drill"]),
        {
            "id": "lap",
            "name": "laptop.tail1234.ts.net",
            "hostname": "laptop",
            "tags": ["tag:prod"],
            "connectedToControl": False,
        },
    ]

    assert [d["id"] for d in cleanup.select_stale_prod_devices(devices)] == ["old"]
    assert cleanup.select_drill_devices(devices) == []


def test_prod_rename_target_is_the_single_online_node_with_a_suffix() -> None:
    assert cleanup.prod_rename_target([OLD, NEW]) is NEW
    assert cleanup.prod_rename_target([_prod("n", "budget-planner-prod", online=True)]) is None
    assert (
        cleanup.prod_rename_target([NEW, _prod("n2", "budget-planner-prod-2", online=True)]) is None
    )
    assert cleanup.prod_rename_target([OLD]) is None


def _fake_api(
    devices: list[dict[str, Any]], calls: list[tuple[str, str, Any]], fail: str = ""
) -> Any:
    def fake(method: str, url: str, **kwargs: Any) -> Any:
        calls.append((method, url, kwargs.get("json_body")))
        if url.endswith("/oauth/token"):
            return {"access_token": "SECRET-TOKEN"}
        if method == "GET":
            return {"devices": devices}
        if method == fail:
            raise urllib.error.URLError("boom")
        return {}

    return fake


def test_prod_deletes_old_node_then_renames_new_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, str, Any]] = []
    monkeypatch.setattr(cleanup, "_request", _fake_api([OLD, NEW], calls))

    env = {"TS_CLEANUP_CLIENT_ID": "id", "TS_CLEANUP_SECRET": "sec"}
    assert cleanup.main(env, ["--env", "prod"]) == 0

    writes = [(m, u, b) for m, u, b in calls if m in {"DELETE", "POST"} and "oauth" not in u]
    assert writes == [
        ("DELETE", f"{cleanup.API}/device/old", None),
        ("POST", f"{cleanup.API}/device/new/name", {"name": "budget-planner-prod"}),
    ]
    out = capsys.readouterr().out
    assert "SECRET-TOKEN" not in out
    assert "::warning::" not in out


def test_prod_never_deletes_an_online_node(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, Any]] = []
    plain = _prod("live", "budget-planner-prod", online=True)
    monkeypatch.setattr(cleanup, "_request", _fake_api([plain], calls))

    assert cleanup.cleanup("id", "sec", "prod") == 0
    assert [m for m, _u, _b in calls if m in {"DELETE", "POST"} and "oauth" not in _u] == []


def test_prod_does_not_rename_while_the_old_node_remains(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, str, Any]] = []
    monkeypatch.setattr(cleanup, "_request", _fake_api([OLD, NEW], calls, fail="DELETE"))

    assert (
        cleanup.main({"TS_CLEANUP_CLIENT_ID": "id", "TS_CLEANUP_SECRET": "sec"}, ["--env", "prod"])
        == 0
    )
    assert not any(u.endswith("/name") for _m, u, _b in calls)
    assert "Not renaming" in capsys.readouterr().out


def test_prod_rename_failure_is_a_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, str, Any]] = []
    monkeypatch.setattr(cleanup, "_request", _fake_api([OLD, NEW], calls, fail="POST"))

    assert (
        cleanup.main({"TS_CLEANUP_CLIENT_ID": "id", "TS_CLEANUP_SECRET": "sec"}, ["--env", "prod"])
        == 0
    )
    assert "::warning::Could not rename" in capsys.readouterr().out


def test_prod_without_secrets_warns(capsys: pytest.CaptureFixture[str]) -> None:
    assert cleanup.main({}, ["--env", "prod"]) == 0
    out = capsys.readouterr().out
    assert "::warning::" in out
    assert "prod" in out


# --- drill rehearsal of a replacement (ADR-0122 §7) --------------------------

RUN_NAME = "budget-planner-drill-4242"
CREDS = {"TS_CLEANUP_CLIENT_ID": "id", "TS_CLEANUP_SECRET": "sec"}


def _drill(dev_id: str, name: str, online: bool) -> dict[str, Any]:
    return {
        "id": dev_id,
        "hostname": RUN_NAME,
        "name": f"{name}.tail1234.ts.net",
        "tags": ["tag:drill"],
        "connectedToControl": online,
    }


def test_replaced_drill_deletes_old_renames_new_and_settles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, Any]] = []
    devices = [
        _drill("old", RUN_NAME, online=False),
        _drill("new", f"{RUN_NAME}-1", online=True),
        # Another run's drill must never match.
        {**_drill("other", "budget-planner-drill-42421", online=False), "hostname": "x"},
    ]
    monkeypatch.setattr(cleanup, "_request", _fake_api(devices, calls))

    rc = cleanup.main(CREDS, ["--env", "drill", "--replaced-name", RUN_NAME, "--require"])

    assert rc == 0
    writes = [(m, u, b) for m, u, b in calls if m in {"DELETE", "POST"} and "oauth" not in u]
    assert writes == [
        ("DELETE", f"{cleanup.API}/device/old", None),
        ("POST", f"{cleanup.API}/device/new/name", {"name": RUN_NAME}),
    ]


@pytest.mark.parametrize(
    "devices",
    [
        [],  # new VM not joined yet
        [_drill("old", RUN_NAME, online=True), _drill("new", f"{RUN_NAME}-1", online=True)],
    ],
)
def test_require_fails_until_settled(monkeypatch: pytest.MonkeyPatch, devices: list[Any]) -> None:
    monkeypatch.setattr(cleanup, "_request", _fake_api(devices, []))

    assert cleanup.main(CREDS, ["--replaced-name", RUN_NAME, "--require"]) == 1
    assert cleanup.main(CREDS, ["--replaced-name", RUN_NAME]) == 0


def test_require_settled_when_plain_name_already_held(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, Any]] = []
    monkeypatch.setattr(cleanup, "_request", _fake_api([_drill("n", RUN_NAME, True)], calls))

    assert cleanup.main(CREDS, ["--replaced-name", RUN_NAME, "--require"]) == 0
    assert not [m for m, _u, _b in calls if m in {"DELETE", "POST"} and "oauth" not in _u]


def test_require_fails_on_rename_error_and_without_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    devices = [_drill("old", RUN_NAME, False), _drill("new", f"{RUN_NAME}-1", True)]
    monkeypatch.setattr(cleanup, "_request", _fake_api(devices, [], fail="POST"))

    assert cleanup.main(CREDS, ["--replaced-name", RUN_NAME, "--require"]) == 1
    assert cleanup.main({}, ["--replaced-name", RUN_NAME, "--require"]) == 1


@pytest.mark.parametrize(
    "argv",
    [["--env", "prod", "--replaced-name", RUN_NAME], ["--replaced-name", "budget-planner-prod"]],
)
def test_replaced_name_is_drill_only(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        cleanup.main(CREDS, argv)


AFTER = "2026-11-18T20:00:00Z"


def test_old_node_alone_never_counts_as_settled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review finding: old node still online, new VM not registered yet."""
    old = {**_drill("old", RUN_NAME, online=True), "created": "2026-11-18T19:00:00Z"}
    monkeypatch.setattr(cleanup, "_request", _fake_api([old], []))

    argv = ["--replaced-name", RUN_NAME, "--require", "--created-after", AFTER]
    assert cleanup.main(CREDS, argv) == 1


def test_new_node_created_after_settles(monkeypatch: pytest.MonkeyPatch) -> None:
    old = {**_drill("old", RUN_NAME, online=False), "created": "2026-11-18T19:00:00Z"}
    new = {**_drill("new", f"{RUN_NAME}-1", online=True), "created": "2026-11-18T20:05:00Z"}
    monkeypatch.setattr(cleanup, "_request", _fake_api([old, new], []))

    argv = ["--replaced-name", RUN_NAME, "--require", "--created-after", AFTER]
    assert cleanup.main(CREDS, argv) == 0


@pytest.mark.parametrize("created", [None, "not a date", 5])
def test_unknown_creation_time_is_not_settled(
    monkeypatch: pytest.MonkeyPatch, created: object
) -> None:
    node = {**_drill("n", RUN_NAME, online=True), "created": created}
    monkeypatch.setattr(cleanup, "_request", _fake_api([node], []))

    argv = ["--replaced-name", RUN_NAME, "--require", "--created-after", AFTER]
    assert cleanup.main(CREDS, argv) == 1
