"""Host agent ``terraform/host/agent/bp_agent.py`` (T-D129, ADR-0111). No network.

The agent runs as root on the VM; here it runs against temp paths, a fake
command runner (docker / cosign / curl) and a fake metadata fetch.
"""

from __future__ import annotations

import grp
import hashlib
import importlib.util
import json
import os
import pwd
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
AGENT = ROOT / "terraform" / "host" / "agent" / "bp_agent.py"

REF = "ghcr.io/o/budget-planner:sha-89ac3c2@sha256:" + "a" * 64
OLD_REF = "ghcr.io/o/budget-planner:sha-075f986@sha256:" + "b" * 64
USER = pwd.getpwuid(os.getuid()).pw_name
GROUP = grp.getgrgid(os.getgid()).gr_name


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bp_agent", AGENT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["bp_agent"] = module
    spec.loader.exec_module(module)
    return module


agent = _load()


def _doc(tmp: Path, **overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema": 1,
        "generation": "gen-1",
        "compose_file": str(tmp / "etc" / "docker-compose.yml"),
        "image": {"ref": REF, "previous_ref": OLD_REF, "container": "budget-planner-app"},
        "ready": {"url": "https://h.example/ready", "resolve": "h.example:443:127.0.0.1"},
        "docker_config_json": '{"auths": {}}',
        "cosign": {
            "version": "v3.1.4",
            "url": "https://example.invalid/cosign",
            "sha256": "0" * 64,
            "identity_regexp": "^https://github\\.com/o/r/",
            "issuer": "https://token.actions.githubusercontent.com",
        },
        "ancestry": {"enabled": False, "repo": "o/r", "branch": "main"},
        "files": [
            {
                "path": str(tmp / "etc" / "docker-compose.yml"),
                "mode": "0640",
                "owner": USER,
                "group": GROUP,
                "content": f"image: {REF}\n",
                "restart": [],
            },
            {
                "path": str(tmp / "etc" / "Caddyfile"),
                "mode": "0644",
                "owner": USER,
                "group": GROUP,
                "content": "h.example {}\n",
                "restart": ["caddy"],
            },
        ],
    }
    doc.update(overrides)
    return doc


class FakeRunner:
    """Records commands; answers docker inspect, cosign, compose and curl."""

    def __init__(
        self,
        running: str = "",
        verify_ok: bool = True,
        ready_ok: bool = True,
        litestream: list[bool] | None = None,
        stop_ok: bool = True,
        *,
        network_rm_ok: bool = True,
        compose_error: str = "",
        caddy_mode: str = "host",
        up_failures: int = 0,
    ) -> None:
        self.running = running
        self.verify_ok = verify_ok
        self.ready_ok = ready_ok
        # T-D157: answers to `docker inspect {{.State.Running}} litestream`, in order.
        self.litestream = list(litestream) if litestream is not None else []
        self.stop_ok = stop_ok
        self.network_rm_ok = network_rm_ok
        self.compose_error = compose_error
        self.caddy_mode = caddy_mode
        self.up_failures = up_failures
        self.calls: list[list[str]] = []

    def __call__(
        self, cmd: Sequence[str], env: Mapping[str, str] | None
    ) -> subprocess.CompletedProcess[str]:
        args = list(cmd)
        self.calls.append(args)
        rc, out = 0, ""
        if args[:2] == ["docker", "inspect"] and "{{.HostConfig.NetworkMode}}" in args:
            out = self.caddy_mode + "\n"
        elif args[:2] == ["docker", "inspect"] and "{{.State.Running}}" in args:
            up = self.litestream.pop(0) if self.litestream else True
            out = "true\n" if up else "false\n"
        elif args[:2] == ["docker", "inspect"]:
            rc, out = (0, self.running + "\n") if self.running else (1, "")
        elif args[:3] == ["docker", "network", "rm"]:
            rc = 0 if self.network_rm_ok else 1
        elif args[:3] == ["docker", "compose", "-f"] and "up" in args and self.up_failures > 0:
            self.up_failures -= 1
            return subprocess.CompletedProcess(args, 1, "", "not connected to the network")
        elif args[:3] == ["docker", "compose", "-f"] and self.compose_error and "up" in args:
            return subprocess.CompletedProcess(args, 1, "", self.compose_error)
        elif args[:3] == ["docker", "compose", "-f"] and "stop" in args:
            rc = 0 if self.stop_ok else 1
        elif "verify" in args:
            rc = 0 if self.verify_ok else 1
        elif args[:3] == ["docker", "compose", "-f"] and args[3:4] and "up" in args:
            self.running = REF
        elif args[0] == "curl":
            rc = 0 if self.ready_ok else 7
        return subprocess.CompletedProcess(args, rc, out, "boom" if rc else "")

    def kinds(self) -> list[str]:
        out = []
        for c in self.calls:
            if c[:2] == ["docker", "compose"]:
                out.append("compose " + c[4])
            elif c[:3] == ["docker", "network", "rm"]:
                out.append("network rm")
            elif "verify" in c:
                out.append("verify")
            else:
                out.append(c[0] if c[0] != "docker" else "inspect")
        return out


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Any]:
    """Point the agent's state at tmp_path; return a function running one converge."""
    state = tmp_path / "state"
    monkeypatch.setattr(agent, "STATE_DIR", state)
    monkeypatch.setattr(agent, "STATUS_FILE", state / "status" / "status.json")
    monkeypatch.setattr(agent, "APPLIED_FILE", state / "applied-generation")
    monkeypatch.setattr(agent, "FAILURE_FILE", state / "failure.json")
    monkeypatch.setattr(agent, "DRAINED_FILE", state / "drained")
    monkeypatch.setattr(agent, "DOCKER_CONFIG_DIR", state / "docker")
    monkeypatch.setattr(agent, "RESTORE_REPORT_FILE", tmp_path / "data" / "restore-report.json")
    monkeypatch.setattr(agent, "ensure_cosign", lambda _policy: tmp_path / "cosign")
    monkeypatch.setattr(os, "chown", lambda *_a, **_k: None)

    def converge(
        doc: dict[str, Any], runner: FakeRunner, now: float = 1000.0, drain: str | None = None
    ) -> int:
        monkeypatch.setattr(agent, "fetch_metadata", lambda _key: json.dumps(doc).encode())
        raw = drain.encode() if drain is not None else None
        monkeypatch.setattr(agent, "fetch_optional", lambda _key: raw)
        rc: int = agent.converge(runner=runner, now=lambda: now, sleep=lambda _s: None)
        return rc

    return converge


def _status(tmp_path: Path) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((tmp_path / "state" / "status" / "status.json").read_text())
    return result


# --- pure functions -------------------------------------------------------


def test_parse_config_reads_files_and_modes(tmp_path: Path) -> None:
    cfg = agent.parse_config(json.dumps(_doc(tmp_path)).encode())

    assert cfg.image_ref == REF
    assert cfg.files[0].mode == 0o640
    assert cfg.files[1].restart == ("caddy",)


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema": 2},
        {"image": {"ref": "ghcr.io/o/budget-planner:sha-1234567", "container": "c"}},
        {
            "files": [
                {"path": "relative", "mode": "0644", "owner": "u", "group": "g", "content": ""}
            ]
        },
        {"cosign": {}},
    ],
)
def test_parse_config_rejects_invalid(tmp_path: Path, overrides: dict[str, Any]) -> None:
    with pytest.raises(agent.AgentError) as err:
        agent.parse_config(json.dumps(_doc(tmp_path, **overrides)).encode())

    assert err.value.code == "config_invalid"


def test_parse_config_rejects_duplicate_paths(tmp_path: Path) -> None:
    doc = _doc(tmp_path)
    doc["files"].append(doc["files"][0])

    with pytest.raises(agent.AgentError):
        agent.parse_config(json.dumps(doc).encode())


def test_backoff_doubles_and_caps() -> None:
    assert [agent.backoff_seconds(n) for n in (1, 2, 3, 6, 10)] == [30, 60, 120, 900, 900]


def test_next_failure_counts_per_generation(tmp_path: Path) -> None:
    cfg = agent.parse_config(json.dumps(_doc(tmp_path)).encode())
    first = agent.next_failure(cfg, None, 100.0)
    second = agent.next_failure(cfg, first, 200.0)
    other = agent.next_failure(cfg, agent.Failure("gen-0", 5, 0.0), 300.0)

    assert (first.attempts, first.next_attempt_at) == (1, 130.0)
    assert (second.attempts, second.next_attempt_at) == (2, 260.0)
    assert other.attempts == 1
    assert agent.in_backoff(cfg, second, 259.0)
    assert not agent.in_backoff(cfg, second, 260.0)


def test_file_needs_write_compares_content_mode_and_owner() -> None:
    f = agent.ManagedFile("/x", 0o644, "u", "g", "abc", ())

    assert agent.file_needs_write(f, None, 0, 0)
    assert not agent.file_needs_write(f, (b"abc", 0o644, 0, 0), 0, 0)
    assert agent.file_needs_write(f, (b"abd", 0o644, 0, 0), 0, 0)
    assert agent.file_needs_write(f, (b"abc", 0o600, 0, 0), 0, 0)
    assert agent.file_needs_write(f, (b"abc", 0o644, 1, 0), 0, 0)


def test_status_never_contains_file_content_or_registry_auth(tmp_path: Path) -> None:
    doc = _doc(tmp_path, docker_config_json='{"auths": {"ghcr.io": {"auth": "SECRET"}}}')
    cfg = agent.parse_config(json.dumps(doc).encode())

    body = json.dumps(agent.build_status(cfg, "ok", REF, "", 0.0))

    assert "SECRET" not in body
    assert "h.example {}" not in body
    assert str(tmp_path) not in body


# --- converge -------------------------------------------------------------


def test_fresh_host_verifies_writes_composes_and_reports_ok(
    tmp_path: Path, host: Callable[..., int]
) -> None:
    runner = FakeRunner()

    rc = host(_doc(tmp_path), runner)

    assert rc == 0
    assert runner.kinds() == [
        "inspect",
        "verify",
        "compose pull",
        "inspect",
        "compose up",
        "network rm",
        "compose restart",
        "curl",
        "inspect",
    ]
    assert (tmp_path / "etc" / "Caddyfile").read_text() == "h.example {}\n"
    assert (tmp_path / "etc" / "docker-compose.yml").stat().st_mode & 0o777 == 0o640
    assert (tmp_path / "state" / "applied-generation").read_text() == "gen-1"
    assert _status(tmp_path) | {"updated_at": ""} == {
        "schema": 1,
        "state": "ok",
        "generation": "gen-1",
        "desired_ref": REF,
        "previous_ref": OLD_REF,
        "running_ref": REF,
        "error": "",
        "error_detail": "",
        "restore": None,
        "drain": None,
        "updated_at": "",
    }


def test_verify_runs_with_the_policy_and_agent_docker_config(
    tmp_path: Path, host: Callable[..., int]
) -> None:
    runner = FakeRunner()

    host(_doc(tmp_path), runner)

    verify = next(c for c in runner.calls if "verify" in c)
    assert verify[-1] == REF
    assert "--certificate-identity-regexp" in verify
    assert "--certificate-oidc-issuer" in verify
    assert (tmp_path / "state" / "docker" / "config.json").read_text() == '{"auths": {}}'


def test_converged_host_does_nothing(tmp_path: Path, host: Callable[..., int]) -> None:
    host(_doc(tmp_path), FakeRunner())
    runner = FakeRunner(running=REF)

    rc = host(_doc(tmp_path), runner)

    assert rc == 0
    assert runner.kinds() == ["inspect"]


def test_unchanged_mounted_file_is_not_restarted(tmp_path: Path, host: Callable[..., int]) -> None:
    host(_doc(tmp_path), FakeRunner())
    doc = _doc(tmp_path, generation="gen-2")
    doc["image"]["ref"] = OLD_REF
    doc["files"][0]["content"] = f"image: {OLD_REF}\n"
    runner = FakeRunner(running=REF)

    host(doc, runner)

    assert "compose restart" not in runner.kinds()
    assert "compose up" in runner.kinds()


def test_signature_failure_changes_nothing_and_backs_off(
    tmp_path: Path, host: Callable[..., int]
) -> None:
    runner = FakeRunner(verify_ok=False)

    rc = host(_doc(tmp_path), runner)

    assert rc == 1
    assert not (tmp_path / "etc").exists()
    assert not any(k.startswith("compose") for k in runner.kinds())
    assert _status(tmp_path)["state"] == "failed"
    assert _status(tmp_path)["error"] == "cosign_verify"
    failure = json.loads((tmp_path / "state" / "failure.json").read_text())
    assert failure["attempts"] == 1

    retry = FakeRunner(verify_ok=False)
    host(_doc(tmp_path), retry, now=1010.0)
    assert retry.kinds() == ["inspect"]

    later = FakeRunner()
    assert host(_doc(tmp_path), later, now=1031.0) == 0
    assert not (tmp_path / "state" / "failure.json").exists()


def test_ready_timeout_reports_failed(tmp_path: Path, host: Callable[..., int]) -> None:
    runner = FakeRunner(ready_ok=False)

    rc = host(_doc(tmp_path), runner)

    assert rc == 1
    assert runner.kinds().count("curl") == agent.READY_ATTEMPTS
    assert _status(tmp_path)["error"] == "ready_timeout"
    assert not (tmp_path / "state" / "applied-generation").exists()


def test_invalid_config_reports_failed_without_generation(
    tmp_path: Path, host: Callable[..., int]
) -> None:
    rc = host(_doc(tmp_path, schema=9), FakeRunner())

    assert rc == 1
    assert _status(tmp_path)["error"] == "config_invalid"
    assert _status(tmp_path)["generation"] == ""


def test_unexpected_error_is_reported_as_internal(tmp_path: Path, host: Callable[..., int]) -> None:
    doc = _doc(tmp_path)
    doc["files"][0]["owner"] = "no-such-user-bp-agent"

    rc = host(doc, FakeRunner())

    assert rc == 1
    assert _status(tmp_path)["error"] == "internal"


# --- cosign install -------------------------------------------------------


class _Resp:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self.data


def _policy(sha: str, url: str = "https://example.invalid/cosign") -> Any:
    return agent.CosignPolicy("v3.1.4", url, sha, "^x", "https://issuer")


def test_cosign_install_checks_checksum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "COSIGN_DIR", tmp_path)
    monkeypatch.setattr(os, "chown", lambda *_a, **_k: None)
    monkeypatch.setattr(agent.urllib.request, "urlopen", lambda *_a, **_k: _Resp(b"bin"))
    good = hashlib.sha256(b"bin").hexdigest()

    path = agent.ensure_cosign(_policy(good))

    assert path.read_bytes() == b"bin"
    assert path.stat().st_mode & 0o777 == 0o755
    with pytest.raises(agent.AgentError, match="checksum"):
        agent.ensure_cosign(agent.CosignPolicy("v9", "https://x", "0" * 64, "^x", "i"))


def test_cosign_install_reuses_verified_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "cosign-v3.1.4").write_bytes(b"bin")
    monkeypatch.setattr(agent, "COSIGN_DIR", tmp_path)

    def no_download(_url: str, timeout: int) -> _Resp:
        raise AssertionError("must not download")

    monkeypatch.setattr(agent.urllib.request, "urlopen", no_download)

    assert agent.ensure_cosign(_policy(hashlib.sha256(b"bin").hexdigest())).name == "cosign-v3.1.4"


def test_cosign_install_requires_https(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "COSIGN_DIR", tmp_path)

    with pytest.raises(agent.AgentError, match="https"):
        agent.ensure_cosign(_policy("0" * 64, url="http://example.invalid/cosign"))


# --- restore report (T-D156, ADR-0127) -------------------------------------

GEN = "2901fbd3873a6696"  # pragma: allowlist secret


def test_parse_restore_report_keeps_only_the_public_fields() -> None:
    raw = json.dumps(
        {"result": "restored", "generation": GEN, "at": "2026-11-18T10:00:00Z", "extra": "x"}
    ).encode()

    assert agent.parse_restore_report(raw) == {
        "result": "restored",
        "generation": GEN,
        "at": "2026-11-18T10:00:00Z",
    }


@pytest.mark.parametrize(
    "raw",
    [
        None,
        b"",
        b"not json",
        b"[]",
        b'{"result": "maybe", "generation": "", "at": "t"}',
        b'{"result": "restored", "generation": 5, "at": "t"}',
        b'{"result": "restored", "at": "t"}',
        json.dumps({"result": "restored", "generation": "a" * 65, "at": "t"}).encode(),
    ],
)
def test_parse_restore_report_rejects_anything_else(raw: bytes | None) -> None:
    assert agent.parse_restore_report(raw) is None


def test_status_publishes_the_restore_report(tmp_path: Path, host: Callable[..., int]) -> None:
    report = tmp_path / "data" / "restore-report.json"
    report.parent.mkdir()
    report.write_text(f'{{"result":"restored","generation":"{GEN}","at":"t"}}\n')

    assert host(_doc(tmp_path), FakeRunner()) == 0

    assert _status(tmp_path)["restore"] == {"result": "restored", "generation": GEN, "at": "t"}


def test_failed_status_still_carries_the_restore_report(
    tmp_path: Path, host: Callable[..., int]
) -> None:
    report = tmp_path / "data" / "restore-report.json"
    report.parent.mkdir()
    report.write_text('{"result":"empty","generation":"","at":"t"}')

    assert host(_doc(tmp_path), FakeRunner(ready_ok=False)) == 1

    status = _status(tmp_path)
    assert status["state"] == "failed"
    assert status["restore"] == {"result": "empty", "generation": "", "at": "t"}


# --- drain (T-D157, ADR-0127 amendment) ------------------------------------

REQ = "44513330068-1"


def _drained_host(tmp_path: Path, host: Callable[..., int]) -> FakeRunner:
    host(_doc(tmp_path), FakeRunner())
    runner = FakeRunner(running=REF)
    assert host(_doc(tmp_path), runner, drain=REQ) == 0
    return runner


def test_drain_stops_only_the_app_and_reports_drained(
    tmp_path: Path, host: Callable[..., int]
) -> None:
    runner = _drained_host(tmp_path, host)

    stops = [c for c in runner.calls if c[:2] == ["docker", "compose"] and "stop" in c]
    assert [c[4:] for c in stops] == [["stop", "app"]]
    assert "compose up" not in runner.kinds() and "verify" not in runner.kinds()
    checks = [c for c in runner.calls if "{{.State.Running}}" in c]
    assert [c[-1] for c in checks] == ["budget-planner-litestream"] * 2
    status = _status(tmp_path)
    assert status["state"] == "drained"
    assert status["drain"] == {"request": REQ, "at": "1970-01-01T00:16:40Z"}
    assert status["generation"] == "gen-1"
    assert (tmp_path / "state" / "drained").read_text() == REQ


def test_drain_waits_three_sync_intervals(
    tmp_path: Path, host: Callable[..., int], monkeypatch: pytest.MonkeyPatch
) -> None:
    host(_doc(tmp_path), FakeRunner())
    slept: list[float] = []
    monkeypatch.setattr(agent, "fetch_metadata", lambda _key: json.dumps(_doc(tmp_path)).encode())
    monkeypatch.setattr(agent, "fetch_optional", lambda _key: REQ.encode())

    agent.converge(runner=FakeRunner(running=REF), now=lambda: 1.0, sleep=slept.append)

    assert slept == [agent.DRAIN_SETTLE_S] == [30]


def test_repeated_drain_for_the_same_request_does_nothing(
    tmp_path: Path, host: Callable[..., int]
) -> None:
    _drained_host(tmp_path, host)
    runner = FakeRunner(running=REF)

    assert host(_doc(tmp_path), runner, drain=REQ) == 0
    assert runner.calls == []


def test_new_request_drains_again(tmp_path: Path, host: Callable[..., int]) -> None:
    _drained_host(tmp_path, host)
    runner = FakeRunner(running=REF)

    assert host(_doc(tmp_path), runner, drain="44513330068-2") == 0
    assert "compose stop" in runner.kinds()
    assert _status(tmp_path)["drain"]["request"] == "44513330068-2"


@pytest.mark.parametrize(("litestream", "detail"), [([False], "before"), ([True, False], "during")])
def test_drain_fails_when_litestream_is_not_running(
    tmp_path: Path, host: Callable[..., int], litestream: list[bool], detail: str
) -> None:
    host(_doc(tmp_path), FakeRunner())

    rc = host(_doc(tmp_path), FakeRunner(running=REF, litestream=litestream), drain=REQ)

    assert rc == 1
    status = _status(tmp_path)
    assert (status["state"], status["error"]) == ("failed", "drain_litestream")
    assert status["drain"] == {"request": REQ, "at": ""}
    # No back-off for drain failures; the marker stays so the undrain re-applies.
    assert not (tmp_path / "state" / "failure.json").exists()
    assert (tmp_path / "state" / "drained").exists()


def test_drain_fails_when_the_app_does_not_stop(tmp_path: Path, host: Callable[..., int]) -> None:
    host(_doc(tmp_path), FakeRunner())

    assert host(_doc(tmp_path), FakeRunner(running=REF, stop_ok=False), drain=REQ) == 1
    assert _status(tmp_path)["error"] == "drain_stop"


def test_undrain_reapplies_and_clears_the_marker(tmp_path: Path, host: Callable[..., int]) -> None:
    _drained_host(tmp_path, host)
    runner = FakeRunner(running=REF)  # a stopped container still reports its image

    assert host(_doc(tmp_path), runner) == 0

    assert "compose up" in runner.kinds() and "curl" in runner.kinds()
    assert not (tmp_path / "state" / "drained").exists()
    status = _status(tmp_path)
    assert (status["state"], status["drain"]) == ("ok", None)


def test_undrain_after_a_failed_drain_reapplies(tmp_path: Path, host: Callable[..., int]) -> None:
    host(_doc(tmp_path), FakeRunner())
    host(_doc(tmp_path), FakeRunner(running=REF, litestream=[True, False]), drain=REQ)
    runner = FakeRunner(running=REF)

    assert host(_doc(tmp_path), runner, now=1001.0) == 0
    assert "compose up" in runner.kinds()


@pytest.mark.parametrize(
    ("raw", "expected"), [(None, None), (b"", None), (b" \n", None), (b"r-1\n", "r-1")]
)
def test_parse_drain_request(raw: bytes | None, expected: str | None) -> None:
    assert agent.parse_drain_request(raw) == expected


@pytest.mark.parametrize("raw", [b"a b", b"x;rm", b"a" * 65])
def test_parse_drain_request_rejects_anything_else(raw: bytes) -> None:
    with pytest.raises(agent.AgentError, match="drain_request"):
        agent.parse_drain_request(raw)


def test_fetch_optional_maps_404_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_key: str) -> bytes:
        raise agent.AgentError("config_fetch", "HTTP 404")

    def broken(_key: str) -> bytes:
        raise agent.AgentError("config_fetch", "HTTP 500")

    monkeypatch.setattr(agent, "fetch_metadata", missing)
    assert agent.fetch_optional("bp-drain") is None
    monkeypatch.setattr(agent, "fetch_metadata", broken)
    with pytest.raises(agent.AgentError, match="500"):
        agent.fetch_optional("bp-drain")


def test_undrain_ignores_an_earlier_back_off(tmp_path: Path, host: Callable[..., int]) -> None:
    """Review finding: a failure record for this generation must not keep the app down."""
    host(_doc(tmp_path), FakeRunner(ready_ok=False))  # failed apply: back-off armed
    assert (tmp_path / "state" / "failure.json").exists()
    host(_doc(tmp_path), FakeRunner(running=REF), drain=REQ)
    runner = FakeRunner(running=REF)

    assert host(_doc(tmp_path), runner) == 0  # same `now`: still inside the back-off
    assert "compose up" in runner.kinds()


# --- T-Q238: sha-* images must be ancestors of main -------------------------


def _ancestry_cfg(tmp_path: Path, ref: str = REF, enabled: bool = True) -> Any:
    doc = _doc(tmp_path, ancestry={"enabled": enabled, "repo": "o/r", "branch": "main"})
    doc["image"]["ref"] = ref
    return agent.parse_config(json.dumps(doc).encode())


@pytest.mark.parametrize(
    ("ref", "tag"),
    [(REF, "sha-89ac3c2"), ("ghcr.io/o/b:v3.0.5@sha256:" + "a" * 64, "v3.0.5")],
)
def test_image_tag(ref: str, tag: str) -> None:
    assert agent.image_tag(ref) == tag


@pytest.mark.parametrize(
    ("status", "ok"),
    [("behind", True), ("identical", True), ("ahead", False), ("diverged", False)],
)
def test_is_main_ancestor(status: str, ok: bool) -> None:
    assert agent.is_main_ancestor({"status": status}) is ok
    assert agent.is_main_ancestor([]) is False


def test_rollback_to_sha_off_main_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent, "fetch_compare", lambda *_a: {"status": "diverged"})
    with pytest.raises(agent.AgentError) as exc:
        agent.verify_main_ancestry(_ancestry_cfg(tmp_path))
    assert exc.value.code == "ancestry_not_main"


def test_rollback_to_sha_on_main_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, str, str]] = []

    def fake(repo: str, branch: str, sha: str) -> object:
        seen.append((repo, branch, sha))
        return {"status": "behind"}

    monkeypatch.setattr(agent, "fetch_compare", fake)
    agent.verify_main_ancestry(_ancestry_cfg(tmp_path))
    assert seen == [("o/r", "main", "89ac3c2")]


def test_ancestry_check_fails_closed_when_api_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: str) -> object:
        raise OSError("down")

    monkeypatch.setattr(agent, "fetch_compare", boom)
    with pytest.raises(agent.AgentError) as exc:
        agent.verify_main_ancestry(_ancestry_cfg(tmp_path))
    assert exc.value.code == "ancestry_check"


def test_ancestry_skipped_for_release_tag_and_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: str) -> object:
        raise AssertionError("must not be called")

    monkeypatch.setattr(agent, "fetch_compare", boom)
    agent.verify_main_ancestry(_ancestry_cfg(tmp_path, "ghcr.io/o/b:v3.0.5@sha256:" + "a" * 64))
    agent.verify_main_ancestry(_ancestry_cfg(tmp_path, enabled=False))


def test_apply_rejects_off_main_sha_before_touching_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: Callable[..., Any]
) -> None:
    doc = _doc(tmp_path, ancestry={"enabled": True, "repo": "o/r", "branch": "main"})
    monkeypatch.setattr(agent, "fetch_compare", lambda *_a: {"status": "diverged"})
    assert host(doc, FakeRunner()) == 1
    assert _status(tmp_path)["error"] == "ancestry_not_main"
    assert not (tmp_path / "etc" / "docker-compose.yml").exists()


# --- T-Q305: legacy network cleanup and scrubbed failure detail ------------


def test_up_removes_the_legacy_network_without_down_or_volumes(
    tmp_path: Path, host: Callable[..., int]
) -> None:
    runner = FakeRunner()

    host(_doc(tmp_path), runner)

    assert ["docker", "network", "rm", "budget-planner_edge"] in runner.calls
    assert not any("down" in c or "-v" in c for c in runner.calls)


def test_legacy_network_removal_failure_is_ignored(
    tmp_path: Path, host: Callable[..., int]
) -> None:
    runner = FakeRunner(network_rm_ok=False)

    rc = host(_doc(tmp_path), runner)

    assert rc == 0
    assert _status(tmp_path)["state"] == "ok"


def test_compose_failure_publishes_a_scrubbed_one_line_detail(
    tmp_path: Path, host: Callable[..., int]
) -> None:
    stderr = (
        " Container budget-planner-app  Recreate\n"
        "Error response from daemon: network budget-planner_edge has active "
        "endpoints BUDGET_COOKIE_SECRET=hunter2 SCW_SECRET_KEY=abc\n"
        "second error line\n"
    )
    runner = FakeRunner(compose_error=stderr)

    rc = host(_doc(tmp_path), runner)

    status = _status(tmp_path)
    assert rc == 1
    assert status["error"] == "compose"
    detail = status["error_detail"]
    assert detail.startswith("Error response from daemon: network budget-planner_edge")
    assert "hunter2" not in detail
    assert "abc" not in detail
    assert "BUDGET_COOKIE_SECRET=<redacted>" in detail
    assert "\n" not in detail


def test_scrub_detail_caps_length_and_handles_empty() -> None:
    assert agent.scrub_detail("") == ""
    assert len(agent.scrub_detail("error " + "x" * 500)) == agent.DETAIL_MAX_CHARS
    assert agent.scrub_detail("pulling\ndone") == "done"


def test_non_compose_failures_carry_no_detail(tmp_path: Path, host: Callable[..., int]) -> None:
    host(_doc(tmp_path), FakeRunner(ready_ok=False))

    assert _status(tmp_path)["error_detail"] == ""


def test_bridged_caddy_is_removed_before_up_to_free_80_and_443(
    tmp_path: Path, host: Callable[..., int]
) -> None:
    runner = FakeRunner(caddy_mode="edge")

    host(_doc(tmp_path), runner)

    rm = runner.calls.index(["docker", "rm", "--force", "budget-planner-caddy"])
    up = next(i for i, c in enumerate(runner.calls) if "up" in c)
    assert rm < up


def test_host_networked_caddy_is_left_alone(tmp_path: Path, host: Callable[..., int]) -> None:
    runner = FakeRunner(caddy_mode="host")

    host(_doc(tmp_path), runner)

    assert not any(c[:3] == ["docker", "rm", "--force"] for c in runner.calls)


def test_failed_up_recreates_containers_once_and_retries(
    tmp_path: Path, host: Callable[..., int]
) -> None:
    runner = FakeRunner(up_failures=1)

    rc = host(_doc(tmp_path), runner)

    assert rc == 0
    rm = [c for c in runner.calls if "rm" in c and "compose" in c]
    assert len(rm) == 1
    assert "-v" not in rm[0]
    assert "--volumes" not in rm[0]
    assert sum(1 for c in runner.calls if "up" in c) == 2


def test_second_up_failure_is_reported(tmp_path: Path, host: Callable[..., int]) -> None:
    rc = host(_doc(tmp_path), FakeRunner(up_failures=2))

    assert rc == 1
    assert _status(tmp_path)["error"] == "compose"
