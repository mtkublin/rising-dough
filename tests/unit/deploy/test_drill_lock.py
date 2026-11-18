"""T-D138 / ADR-0115: the drill lock script and its place in the drill workflows. No network."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
SCRIPT = ROOT / "scripts" / "ci" / "drill_lock.py"
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
OWN_ID = 100


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("drill_lock", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


lock = _load_script()

ENV = {
    "GITHUB_TOKEN": "t",
    "GITHUB_REPOSITORY": "o/r",
    "GITHUB_RUN_ID": str(OWN_ID),
    "SCW_SECRET_KEY": "k",
    "SCW_DEFAULT_PROJECT_ID": "p",
    "TS_CLEANUP_CLIENT_ID": "c",
    "TS_CLEANUP_SECRET": "s",
}


def _run(rid: int, path: str, status: str, created: str, title: str = "") -> dict[str, Any]:
    return {
        "id": rid,
        "name": path.split(".", maxsplit=1)[0],
        "path": f".github/workflows/{path}",
        "status": status,
        "created_at": created,
        "display_title": title or path,
        "html_url": f"https://github.com/o/r/actions/runs/{rid}",
    }


class FakeApi:
    def __init__(
        self,
        runs: list[dict[str, Any]] | None = None,
        servers: list[dict[str, Any]] | None = None,
        fail: str | None = None,
    ) -> None:
        self.runs = runs or []
        self.servers = servers or []
        self.fail = fail

    def __call__(self, url: str, headers: Any) -> Any:
        if self.fail and self.fail in url:
            raise lock.LockError(f"GET {self.fail} failed: HTTP 500")
        if url.endswith(f"/runs/{OWN_ID}"):
            return {"created_at": "2026-11-18T11:00:00Z"}
        if "/actions/runs?status=" in url:
            status = url.split("status=")[1].split("&", maxsplit=1)[0]
            return {"workflow_runs": [r for r in self.runs if r["status"] == status]}
        if "/servers?" in url:
            return {"servers": self.servers}
        raise AssertionError(url)


def _tailnet(findings: list[str] | None = None) -> Any:
    return lambda _env: findings or []


def _acquire(api: FakeApi, env: dict[str, str] | None = None, tail: Any = None) -> Any:
    return lock.acquire({**ENV, **(env or {})}, get=api, now=NOW, tailnet_check=tail or _tailnet())


def _server(name: str = "budget-planner-drill", expires: str | None = None) -> dict[str, Any]:
    tags = [f"expires-at={expires}"] if expires else []
    return {"name": name, "tags": tags, "creation_date": "2026-11-18T10:00:00Z"}


def test_nothing_found_passes() -> None:
    code, lines = _acquire(FakeApi())

    assert code == 0
    assert lines == ["drill lock acquired: no drill VM, no other drill run"]


def test_expired_vm_fails_with_destroy_hint() -> None:
    code, lines = _acquire(FakeApi(servers=[_server(expires="2026-11-18T11:00:00Z")]))

    assert code == 1
    assert lines[0].startswith("::error::")
    assert "expired drill still up" in lines[0]
    assert "run drill-destroy.yml first" in lines[0]


def test_unexpired_vm_fails_with_expiry() -> None:
    code, lines = _acquire(FakeApi(servers=[_server(expires="2026-11-18T13:00:00Z")]))

    assert code == 1
    assert "drill VM budget-planner-drill is up until 2026-11-18T13:00:00Z" in lines[0]
    assert "kept explore drill?" in lines[0]
    assert "created 2026-11-18T10:00:00Z" in lines[0]


def test_vm_without_tag_still_holds() -> None:
    code, lines = _acquire(FakeApi(servers=[_server()]))

    assert code == 1
    assert "no usable expires-at tag" in lines[0]


def test_unrelated_server_is_ignored() -> None:
    code, _ = _acquire(FakeApi(servers=[_server(name="something-else")]))

    assert code == 0


def test_other_active_run_fails_with_name_id_url() -> None:
    runs = [_run(7, "drill.yml", "in_progress", "2026-11-18T10:30:00Z")]
    code, lines = _acquire(FakeApi(runs=runs))

    assert code == 1
    assert "run 7" in lines[0]
    assert "https://github.com/o/r/actions/runs/7" in lines[0]
    assert "drill" in lines[0]


def test_own_run_and_unrelated_workflows_are_ignored() -> None:
    runs = [
        _run(OWN_ID, "drill.yml", "in_progress", "2026-11-18T11:00:00Z"),
        _run(8, "ci.yml", "in_progress", "2026-11-18T10:30:00Z"),
    ]

    assert _acquire(FakeApi(runs=runs))[0] == 0


def test_run_queued_behind_us_is_not_a_holder_but_an_older_one_is() -> None:
    behind = _run(9, "drill.yml", "pending", "2026-11-18T11:30:00Z")
    older = _run(6, "restore-drill.yml", "queued", "2026-11-18T10:00:00Z")

    assert _acquire(FakeApi(runs=[behind]))[0] == 0
    code, lines = _acquire(FakeApi(runs=[behind, older]))
    assert code == 1
    assert len(lines) == 1 and "run 6" in lines[0]


def test_rollback_counts_for_drill_but_not_prod() -> None:
    drill = _run(5, "rollback.yml", "in_progress", "2026-11-18T10:00:00Z", "rollback (drill)")
    prod = _run(4, "rollback.yml", "in_progress", "2026-11-18T10:00:00Z", "rollback (prod)")

    assert _acquire(FakeApi(runs=[drill]))[0] == 1
    assert _acquire(FakeApi(runs=[prod]))[0] == 0


def test_online_tailnet_node_holds_the_lock() -> None:
    code, lines = _acquire(FakeApi(), tail=_tailnet(["tailnet node x (tag:drill) is online"]))

    assert code == 1
    assert "tailnet node" in lines[0]


def test_evaluate_devices_ignores_offline_and_untagged() -> None:
    cleanup = lock._load_cleanup()
    devices = [
        {"hostname": "budget-planner-drill", "tags": ["tag:drill"], "connectedToControl": True},
        {"hostname": "budget-planner-drill-1", "tags": ["tag:drill"], "connectedToControl": False},
        {"hostname": "budget-planner-drill", "tags": [], "connectedToControl": True},
    ]

    findings = lock.evaluate_devices(devices, cleanup)

    assert len(findings) == 1 and "budget-planner-drill (tag:drill)" in findings[0]


def test_force_skips_vm_checks_but_never_run_check() -> None:
    api = FakeApi(servers=[_server(expires="2026-11-18T13:00:00Z")])
    code, lines = _acquire(api, {"DRILL_LOCK_FORCE": "true"})
    assert code == 0
    assert lines[0].startswith("::warning::FORCE")

    runs = [_run(7, "drill.yml", "in_progress", "2026-11-18T10:30:00Z")]
    code, _ = _acquire(FakeApi(runs=runs), {"DRILL_LOCK_FORCE": "true"})
    assert code == 1


def test_check_vm_false_skips_vm_but_not_runs() -> None:
    api = FakeApi(servers=[_server(expires="2026-11-18T13:00:00Z")])
    code, lines = _acquire(api, {"DRILL_LOCK_CHECK_VM": "false"})
    assert code == 0 and "no other drill run" in lines[0]

    runs = [_run(7, "drill.yml", "waiting", "2026-11-18T10:30:00Z")]
    assert _acquire(FakeApi(runs=runs), {"DRILL_LOCK_CHECK_VM": "false"})[0] == 1


@pytest.mark.parametrize("fail", ["/actions/runs", "/servers"])
def test_api_errors_fail_closed(fail: str) -> None:
    code, lines = _acquire(FakeApi(fail=fail))

    assert code == 2
    assert lines[0].startswith("::error::drill lock cannot be evaluated")


@pytest.mark.parametrize("missing", ["GITHUB_TOKEN", "SCW_SECRET_KEY", "SCW_DEFAULT_PROJECT_ID"])
def test_missing_inputs_fail_closed(missing: str) -> None:
    env = {k: v for k, v in ENV.items() if k != missing}
    code, lines = lock.acquire(env, get=FakeApi(), now=NOW, tailnet_check=_tailnet())

    assert code == 2 and "must be set" in lines[0]


def test_missing_tailnet_credentials_fail_closed() -> None:
    with pytest.raises(lock.LockError):
        lock.check_tailnet({})


# --- workflow wiring -----------------------------------------------------------------


def _jobs(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text())
    jobs: dict[str, Any] = loaded["jobs"]
    return jobs


def _needs(job: dict[str, Any]) -> set[str]:
    needs = job.get("needs") or []
    return {needs} if isinstance(needs, str) else set(needs)


def _reaches(
    jobs: dict[str, Any], job: str, target: str, seen: frozenset[str] = frozenset()
) -> bool:
    if job in seen:
        return False
    return any(n == target or _reaches(jobs, n, target, seen | {job}) for n in _needs(jobs[job]))


@pytest.mark.parametrize(
    "name",
    [
        "drill.yml",
        "restore-drill.yml",
        "drill-destroy.yml",
        "drill-sweeper.yml",
        "replace-rehearsal.yml",
    ],
)
def test_every_job_depends_on_drill_lock(name: str) -> None:
    jobs = _jobs(name)

    assert "drill-lock" in jobs
    assert not _needs(jobs["drill-lock"])
    assert next(iter(jobs)) == "drill-lock"
    for job in jobs:
        if job != "drill-lock":
            assert _reaches(jobs, job, "drill-lock"), f"{name}:{job} does not need drill-lock"


@pytest.mark.parametrize("name", ["drill.yml", "restore-drill.yml"])
def test_force_input_defaults_false(name: str) -> None:
    loaded: dict[Any, Any] = yaml.safe_load((WORKFLOWS / name).read_text())
    triggers = loaded[True] if True in loaded else loaded["on"]
    force = triggers["workflow_dispatch"]["inputs"]["force"]

    assert force["type"] == "boolean" and force["default"] is False


@pytest.mark.parametrize(
    ("name", "check_vm"),
    [
        ("drill.yml", None),
        ("restore-drill.yml", None),
        ("drill-destroy.yml", "false"),
        ("drill-sweeper.yml", "false"),
    ],
)
def test_lock_job_shape(name: str, check_vm: str | None) -> None:
    job = _jobs(name)["drill-lock"]

    assert job["environment"] == "drill-teardown"
    assert job["permissions"] == {"contents": "read", "actions": "read"}
    run = " ".join(str(s.get("run", "")) for s in job["steps"])
    assert "python3 scripts/ci/drill_lock.py" in run
    assert job["env"].get("DRILL_LOCK_CHECK_VM") == check_vm
