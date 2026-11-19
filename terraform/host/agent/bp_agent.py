#!/usr/bin/env python3
"""bp-agent: converge this host to the Terraform-declared state (ADR-0111).

Runs as root from ``bp-converge.service`` (systemd timer, every 30 s). The
loader fetches this file from the Scaleway metadata key ``bp-agent``; the agent
then reads ``bp-config`` (one JSON document rendered by Terraform), and:

1. exits early when the config generation is already applied and the app
   container runs the desired image;
2. installs the pinned cosign binary (checksum verified) and verifies the app
   image signature; on failure nothing on the host changes;
3. writes the managed files atomically, runs ``docker compose pull`` +
   ``up -d`` and restarts services whose mounted files changed;
4. probes ``/ready`` through Caddy and writes ``status.json``, which Caddy
   serves at ``/.well-known/bp-deploy-status.json`` for the CI monitor. The
   status carries ``restore``: how this host's database came to be, from the
   report ``litestream-restore`` writes (T-D156, ADR-0127).

Drain (T-D157, ADR-0127 amendment): before a release replaces the VM, CI sets
the metadata key ``bp-drain`` to a request id. While it is set the agent does
not converge: it stops ``app`` (writes end; Caddy keeps serving the status),
checks ``litestream`` runs before and after three sync intervals, and reports
``state: "drained"``. The ``drained`` marker is written before the app stops;
while it exists the converged shortcut is skipped, so once CI deletes the key
the next run re-applies (``compose up``) and the app comes back.

A failed generation is retried with exponential back-off. The agent never
changes the desired state; CI decides (re-apply with the previous ref).

Stdlib only: it runs on Ubuntu's ``python3`` with no packages installed.
"""

from __future__ import annotations

import dataclasses
import grp
import hashlib
import http.client
import json
import os
import pwd
import random
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

METADATA_HOST = "169.254.42.42"
CONFIG_KEY = "bp-config"
DRAIN_KEY = "bp-drain"
SCHEMA = 1

STATE_DIR = Path("/var/lib/budget-planner")
STATUS_FILE = STATE_DIR / "status" / "status.json"
APPLIED_FILE = STATE_DIR / "applied-generation"
FAILURE_FILE = STATE_DIR / "failure.json"
DRAINED_FILE = STATE_DIR / "drained"
DOCKER_CONFIG_DIR = STATE_DIR / "docker"
COSIGN_DIR = Path("/usr/local/lib/bp-agent")
# Written by litestream-restore.sh on the /data bind mount (T-D156, ADR-0127).
RESTORE_REPORT_FILE = Path("/data/restore-report.json")
RESTORE_RESULTS = frozenset({"restored", "empty", "skipped-db-present"})
RESTORE_FIELD_MAX = 64
# T-D157: three Litestream sync intervals (litestream.yml: sync-interval 10s).
DRAIN_SETTLE_S = 30
DRAIN_REQUEST_MAX = 64
DRAIN_REQUEST_CHARS = frozenset("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ._-")
LITESTREAM_CONTAINER = "budget-planner-litestream"

BACKOFF_BASE_S = 30
BACKOFF_MAX_S = 900
READY_ATTEMPTS = 40
READY_SLEEP_S = 3
PRIVILEGED_PORT_TRIES = 20
HTTP_OK = 200
HTTP_NOT_FOUND = 404

Runner = Callable[[Sequence[str], Mapping[str, str] | None], "subprocess.CompletedProcess[str]"]


class AgentError(Exception):
    """A convergence step failed; ``code`` is the terse status error code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class ManagedFile:
    path: str
    mode: int
    owner: str
    group: str
    content: str
    restart: tuple[str, ...]


@dataclass(frozen=True)
class CosignPolicy:
    version: str
    url: str
    sha256: str
    identity_regexp: str
    issuer: str


@dataclass(frozen=True)
class Config:
    generation: str
    compose_file: str
    image_ref: str
    previous_ref: str
    app_container: str
    ready_url: str
    ready_resolve: str
    docker_config_json: str
    cosign: CosignPolicy
    files: tuple[ManagedFile, ...]


@dataclass(frozen=True)
class Failure:
    generation: str
    attempts: int
    next_attempt_at: float


# --------------------------------------------------------------------------
# Pure functions
# --------------------------------------------------------------------------


def parse_config(raw: bytes) -> Config:
    """Parse and validate the ``bp-config`` document."""
    try:
        doc = json.loads(raw)
        if doc["schema"] != SCHEMA:
            raise AgentError("config_invalid", f"schema {doc['schema']}")
        cosign = doc["cosign"]
        files = tuple(
            ManagedFile(
                path=f["path"],
                mode=int(f["mode"], 8),
                owner=f["owner"],
                group=f["group"],
                content=f["content"],
                restart=tuple(f.get("restart", [])),
            )
            for f in doc["files"]
        )
        cfg = Config(
            generation=doc["generation"],
            compose_file=doc["compose_file"],
            image_ref=doc["image"]["ref"],
            previous_ref=doc["image"].get("previous_ref", ""),
            app_container=doc["image"]["container"],
            ready_url=doc["ready"]["url"],
            ready_resolve=doc["ready"]["resolve"],
            docker_config_json=doc["docker_config_json"],
            cosign=CosignPolicy(
                version=cosign["version"],
                url=cosign["url"],
                sha256=cosign["sha256"],
                identity_regexp=cosign["identity_regexp"],
                issuer=cosign["issuer"],
            ),
            files=files,
        )
    except AgentError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise AgentError("config_invalid", repr(exc)) from exc
    paths = [f.path for f in cfg.files]
    if len(set(paths)) != len(paths) or not all(p.startswith("/") for p in paths):
        raise AgentError("config_invalid", "file paths must be absolute and unique")
    if "@sha256:" not in cfg.image_ref:
        raise AgentError("config_invalid", "image ref must be pinned by digest")
    return cfg


def backoff_seconds(attempts: int) -> int:
    """Delay before retrying a failed generation: 30 s doubling, capped at 15 min."""
    return int(min(BACKOFF_BASE_S * 2 ** max(attempts - 1, 0), BACKOFF_MAX_S))


def is_converged(cfg: Config, applied_generation: str, running_ref: str) -> bool:
    return applied_generation == cfg.generation and running_ref == cfg.image_ref


def in_backoff(cfg: Config, failure: Failure | None, now: float) -> bool:
    return (
        failure is not None
        and failure.generation == cfg.generation
        and now < failure.next_attempt_at
    )


def next_failure(cfg: Config, previous: Failure | None, now: float) -> Failure:
    attempts = previous.attempts + 1 if previous and previous.generation == cfg.generation else 1
    return Failure(cfg.generation, attempts, now + backoff_seconds(attempts))


def services_to_restart(changed: Sequence[ManagedFile]) -> tuple[str, ...]:
    return tuple(sorted({svc for f in changed for svc in f.restart}))


def parse_restore_report(raw: bytes | None) -> dict[str, str] | None:
    """The public ``restore`` object: only result, generation and time, or None.

    None when the report is missing or malformed, so CI can never read a value
    the restore script did not write.
    """
    if raw is None:
        return None
    try:
        doc = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(doc, dict):
        return None
    fields = {k: doc.get(k) for k in ("result", "generation", "at")}
    if fields["result"] not in RESTORE_RESULTS or not all(
        isinstance(v, str) and len(v) <= RESTORE_FIELD_MAX for v in fields.values()
    ):
        return None
    return {k: str(v) for k, v in fields.items()}


def parse_drain_request(raw: bytes | None) -> str | None:
    """The ``bp-drain`` request id, or None when the key is absent or empty."""
    if raw is None:
        return None
    request = raw.decode("utf-8", "replace").strip()
    if not request:
        return None
    if len(request) > DRAIN_REQUEST_MAX or not set(request) <= DRAIN_REQUEST_CHARS:
        raise AgentError("drain_request", "not a request id")
    return request


def utc(now: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))


def build_status(
    cfg: Config | None,
    state: str,
    running_ref: str,
    error: str,
    now: float,
    *,
    restore: Mapping[str, str] | None = None,
    drain: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """status.json body. No secrets and no paths: Caddy serves it publicly."""
    return {
        "schema": SCHEMA,
        "state": state,
        "generation": cfg.generation if cfg else "",
        "desired_ref": cfg.image_ref if cfg else "",
        "previous_ref": cfg.previous_ref if cfg else "",
        "running_ref": running_ref,
        "error": error,
        "restore": dict(restore) if restore is not None else None,
        "drain": dict(drain) if drain is not None else None,
        "updated_at": utc(now),
    }


def file_needs_write(
    f: ManagedFile, current: tuple[bytes, int, int, int] | None, uid: int, gid: int
) -> bool:
    """``current`` is (content, mode, uid, gid) of the file on disk, or None."""
    if current is None:
        return True
    content, mode, cur_uid, cur_gid = current
    return content != f.content.encode() or mode != f.mode or (cur_uid, cur_gid) != (uid, gid)


# --------------------------------------------------------------------------
# Side effects
# --------------------------------------------------------------------------


def run(
    cmd: Sequence[str], env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    merged = {**os.environ, **env} if env else None
    return subprocess.run(list(cmd), env=merged, capture_output=True, text=True, check=False)  # noqa: S603


def fetch_metadata(key: str) -> bytes:
    """GET a user-data key. The API only answers privileged (<1024) source ports."""
    last: OSError | None = None
    for port in random.sample(range(1, 1024), PRIVILEGED_PORT_TRIES):
        # Source port only; "" lets the kernel pick the outgoing address.
        conn = http.client.HTTPConnection(METADATA_HOST, 80, timeout=10, source_address=("", port))
        try:
            conn.request("GET", f"/user_data/{key}")
            resp = conn.getresponse()
            body = resp.read()
        except OSError as exc:  # port in use or transient network error: next port
            last = exc
            continue
        finally:
            conn.close()
        if resp.status != HTTP_OK:
            raise AgentError("config_fetch", f"HTTP {resp.status}")
        return body
    raise AgentError("config_fetch", repr(last))


def fetch_optional(key: str) -> bytes | None:
    """GET a user-data key that may be absent: None on 404."""
    try:
        return fetch_metadata(key)
    except AgentError as exc:
        if str(exc).endswith(f"HTTP {HTTP_NOT_FOUND}"):
            return None
        raise


def read_text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return ""


def write_atomic(path: Path, data: bytes, mode: int, uid: int = 0, gid: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        Path(tmp).chmod(mode)
        os.chown(tmp, uid, gid)
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_failure() -> Failure | None:
    try:
        doc = json.loads(FAILURE_FILE.read_text())
        return Failure(doc["generation"], int(doc["attempts"]), float(doc["next_attempt_at"]))
    except (FileNotFoundError, KeyError, ValueError):
        return None


def read_restore_report() -> dict[str, str] | None:
    try:
        return parse_restore_report(RESTORE_REPORT_FILE.read_bytes())
    except OSError:
        return None


def write_status(body: Mapping[str, object]) -> None:
    write_atomic(STATUS_FILE, (json.dumps(body, indent=2) + "\n").encode(), 0o644)


def container_running(runner: Runner, container: str) -> bool:
    res = runner(["docker", "inspect", "--format", "{{.State.Running}}", container], None)
    return res.returncode == 0 and res.stdout.strip() == "true"


def read_status() -> dict[str, object]:
    try:
        doc = json.loads(STATUS_FILE.read_text())
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def running_ref(runner: Runner, container: str) -> str:
    res = runner(["docker", "inspect", "--format", "{{.Config.Image}}", container], None)
    return res.stdout.strip() if res.returncode == 0 else ""


def ensure_cosign(policy: CosignPolicy) -> Path:
    binary = COSIGN_DIR / f"cosign-{policy.version}"
    if binary.exists() and hashlib.sha256(binary.read_bytes()).hexdigest() == policy.sha256:
        return binary
    if not policy.url.startswith("https://"):
        raise AgentError("cosign_install", "url must be https")
    try:
        with urllib.request.urlopen(policy.url, timeout=60) as resp:  # noqa: S310 (https enforced above)
            data = resp.read()
    except OSError as exc:
        raise AgentError("cosign_install", repr(exc)) from exc
    if hashlib.sha256(data).hexdigest() != policy.sha256:
        raise AgentError("cosign_install", "checksum mismatch")
    write_atomic(binary, data, 0o755)
    return binary


def verify_image(runner: Runner, cosign: Path, cfg: Config, env: Mapping[str, str]) -> None:
    res = runner(
        [
            str(cosign),
            "verify",
            "--certificate-identity-regexp",
            cfg.cosign.identity_regexp,
            "--certificate-oidc-issuer",
            cfg.cosign.issuer,
            cfg.image_ref,
        ],
        env,
    )
    if res.returncode != 0:
        raise AgentError("cosign_verify", res.stderr.strip()[-300:])


def write_files(files: Sequence[ManagedFile]) -> tuple[ManagedFile, ...]:
    """Write every file that differs; return the ones written."""
    changed: list[ManagedFile] = []
    for f in files:
        uid = pwd.getpwnam(f.owner).pw_uid
        gid = grp.getgrnam(f.group).gr_gid
        path = Path(f.path)
        try:
            st = path.stat()
            current: tuple[bytes, int, int, int] | None = (
                path.read_bytes(),
                st.st_mode & 0o7777,
                st.st_uid,
                st.st_gid,
            )
        except FileNotFoundError:
            current = None
        if file_needs_write(f, current, uid, gid):
            write_atomic(path, f.content.encode(), f.mode, uid, gid)
            changed.append(f)
    return tuple(changed)


def compose(runner: Runner, cfg: Config, env: Mapping[str, str], *args: str) -> None:
    res = runner(["docker", "compose", "-f", cfg.compose_file, *args], env)
    if res.returncode != 0:
        raise AgentError("compose", f"{args[0]}: {res.stderr.strip()[-300:]}")


def probe_ready(runner: Runner, cfg: Config, sleep: Callable[[float], None]) -> None:
    cmd = [
        "curl",
        "-fsS",
        "-o",
        "/dev/null",
        "--max-time",
        "5",
        "--resolve",
        cfg.ready_resolve,
        cfg.ready_url,
    ]
    for _ in range(READY_ATTEMPTS):
        if runner(cmd, None).returncode == 0:
            return
        sleep(READY_SLEEP_S)
    raise AgentError("ready_timeout")


def apply(cfg: Config, runner: Runner, sleep: Callable[[float], None]) -> None:
    """Verify, write, compose up, probe. Raises AgentError on any failure."""
    write_atomic(DOCKER_CONFIG_DIR / "config.json", cfg.docker_config_json.encode(), 0o600)
    env = {"DOCKER_CONFIG": str(DOCKER_CONFIG_DIR)}
    verify_image(runner, ensure_cosign(cfg.cosign), cfg, env)
    changed = write_files(cfg.files)
    compose(runner, cfg, env, "pull", "--quiet")
    compose(runner, cfg, env, "up", "-d", "--remove-orphans")
    restart = services_to_restart(changed)
    if restart:
        compose(runner, cfg, env, "restart", *restart)
    probe_ready(runner, cfg, sleep)


def drain(
    cfg: Config,
    request: str,
    runner: Runner,
    now: Callable[[], float],
    sleep: Callable[[float], None],
) -> int:
    """Stop the app and let Litestream ship the last frames; report ``drained``."""
    status = read_status()
    done = status.get("drain")
    if (
        read_text(DRAINED_FILE) == request
        and status.get("state") == "drained"
        and isinstance(done, dict)
        and done.get("request") == request
    ):
        return 0
    # Marker first: a drain that fails after the stop must still re-apply later.
    write_atomic(DRAINED_FILE, request.encode(), 0o644)
    restore = read_restore_report()
    current = running_ref(runner, cfg.app_container)
    write_status(
        build_status(
            cfg,
            "draining",
            current,
            "",
            now(),
            restore=restore,
            drain={"request": request, "at": ""},
        )
    )
    env = {"DOCKER_CONFIG": str(DOCKER_CONFIG_DIR)}
    try:
        compose(runner, cfg, env, "stop", "app")
    except AgentError as exc:
        raise AgentError("drain_stop", str(exc)) from exc
    if not container_running(runner, LITESTREAM_CONTAINER):
        raise AgentError("drain_litestream", "not running before the settle")
    sleep(DRAIN_SETTLE_S)
    if not container_running(runner, LITESTREAM_CONTAINER):
        raise AgentError("drain_litestream", "stopped during the settle")
    write_status(
        build_status(
            cfg,
            "drained",
            current,
            "",
            now(),
            restore=restore,
            drain={"request": request, "at": utc(now())},
        )
    )
    print(f"bp-agent: drained for request {request}")
    return 0


def converge(
    runner: Runner = run,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    cfg: Config | None = None
    try:
        cfg = parse_config(fetch_metadata(CONFIG_KEY))
        request = parse_drain_request(fetch_optional(DRAIN_KEY))
        if request is not None:
            return drain(cfg, request, runner, now, sleep)
        current = running_ref(runner, cfg.app_container)
        # A drained host's stopped app still reports its image: re-apply.
        if not DRAINED_FILE.exists() and is_converged(cfg, read_text(APPLIED_FILE), current):
            if not STATUS_FILE.exists():
                write_status(
                    build_status(cfg, "ok", current, "", now(), restore=read_restore_report())
                )
            return 0
        failure = read_failure()
        if in_backoff(cfg, failure, now()):
            return 0
        write_status(
            build_status(cfg, "applying", current, "", now(), restore=read_restore_report())
        )
        apply(cfg, runner, sleep)
    except Exception as exc:  # every failure must end in a failed status
        err = exc if isinstance(exc, AgentError) else AgentError("internal", repr(exc))
        print(f"bp-agent: {err}", file=sys.stderr)
        # A drain failure arms no back-off: the undrain re-apply must not wait.
        if cfg is not None and not err.code.startswith("drain_"):
            failure = next_failure(cfg, read_failure(), now())
            write_atomic(FAILURE_FILE, json.dumps(dataclasses.asdict(failure)).encode(), 0o600)
        write_status(
            build_status(
                cfg,
                "failed",
                running_ref(runner, cfg.app_container) if cfg else "",
                err.code,
                now(),
                restore=read_restore_report(),
            )
        )
        return 1
    write_atomic(APPLIED_FILE, cfg.generation.encode(), 0o644)
    FAILURE_FILE.unlink(missing_ok=True)
    DRAINED_FILE.unlink(missing_ok=True)
    write_status(
        build_status(
            cfg,
            "ok",
            running_ref(runner, cfg.app_container),
            "",
            now(),
            restore=read_restore_report(),
        )
    )
    print(f"bp-agent: applied generation {cfg.generation[:12]} ({cfg.image_ref})")
    return 0


if __name__ == "__main__":
    sys.exit(converge())
