"""Shared fixtures for visual-regression tests (ADR-0027 §4).

The suite is excluded from the default `pytest` run via the `-m "not visual"`
default marker expression, so laptop runs never compare macOS rendering. It runs
in `.github/workflows/visual.yml` and, locally, through `just visual` (pinned
Playwright container, ADR-0027 amendment 2026-11-22, T-Q251). `just visual-update`
regenerates the baselines inside the same container.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Browser, sync_playwright

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.web.auth_cookies import SESSION_DEV_COOKIE_NAME
from tests.auth_support import issue_session, seed_login_user
from tests.visual import handoff
from tests.visual.frozen_server import HANDOFF_FIXTURE_DATE
from tests.visual.handoff_seed import build_seed

VISUAL_ROOT = Path(__file__).parent
# Linux baselines, generated only in the pinned Playwright container (ADR-0027, T-Q251).
BASELINES = VISUAL_ROOT / "__snapshots__"
REPO_ROOT = VISUAL_ROOT.parents[1]
DEMO_DB = REPO_ROOT / "data" / "demo.sqlite"
# demo.sqlite's newest transaction is 2026-10-31; pin the server clock there so
# "today"-relative UI (fiscal period, days left, overdue tint) is stable (T-VIS5).
FROZEN_DATE = HANDOFF_FIXTURE_DATE


# Deterministic text raster: no GPU tiling, no LCD/subpixel glyph positioning,
# no hinting drift between runs (T-VIS2 flake fix).
CHROMIUM_STABLE_ARGS = [
    "--disable-gpu",
    "--disable-lcd-text",
    "--font-render-hinting=none",
    "--disable-font-subpixel-positioning",
    "--force-color-profile=srgb",
    "--disable-skia-runtime-opts",
]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--reference",
        default=None,
        choices=["handoff"],
        help="compare against the designer-handoff references (T-UT10, ADR-0106)",
    )
    parser.addoption(
        "--surface",
        default=None,
        help="limit --reference=handoff to one surface (today, ledger, plan, ...)",
    )
    parser.addoption(
        "--reference-shard",
        default=os.environ.get(handoff.SHARD_ENV),
        help="limit --reference=handoff to one '<viewport>:<theme>' shard, e.g. 1440:dark "
        f"(default: ${handoff.SHARD_ENV}; also the only shard the references are rendered for)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """With ``--reference=handoff`` run only the reference comparisons."""
    if config.getoption("--reference") != "handoff":
        return
    keep = [
        i
        for i in items
        if "test_reference" in i.nodeid
        and isinstance(i, pytest.Function)
        and hasattr(i, "callspec")
    ]
    only = handoff.parse_shard(config.getoption("--reference-shard"))
    if only:
        keep = [
            i
            for i in keep
            if isinstance(i, pytest.Function)
            and (i.callspec.params.get("viewport"), i.callspec.params.get("theme")) == only
        ]
    config.hook.pytest_deselected(items=[i for i in items if i not in keep])
    items[:] = keep


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _uses_handoff_seed(request: pytest.FixtureRequest) -> bool:
    """The handoff-reference comparison (test_reference.py) renders the handoff seed.

    Every other module (test_snapshots.py: old-UI route baselines, which go away per
    migrated surface) keeps the anonymized demo copy (ADR-0147 §3, T-UR00b).
    """
    return str(request.module.__name__).rsplit(".", 1)[-1] == "test_reference"


@pytest.fixture(scope="module")
def scratch_db(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> tuple[Path, str]:
    """A scratch DB plus a live session for user 1; never ``data/budget.sqlite`` (prod).

    ``test_reference.py``: the handoff base seed (`handoff_seed.build_seed`).
    Other modules: a copy of ``data/demo.sqlite`` (or empty), migrated, login user
    seeded (T-D02b). Returns ``(path, session id)``.
    """
    path = tmp_path_factory.mktemp("visual") / "visual.sqlite"
    if _uses_handoff_seed(request):
        return path, build_seed(path).session_token
    if DEMO_DB.exists():
        shutil.copyfile(DEMO_DB, path)
    settings = Settings(_env_file=None, database_url=f"sqlite:///{path.as_posix()}")
    conn = get_connection(settings)
    try:
        apply_migrations(conn)
        seed_login_user(conn)
        session_id = issue_session(conn)
    finally:
        conn.close()
    return path, session_id


SERVER_READY_TIMEOUT_S = float(os.environ.get("VISUAL_SERVER_READY_TIMEOUT_S", "120"))


def _wait_until_ready(url: str, proc: subprocess.Popen[bytes]) -> None:
    """Poll ``url`` until it answers 200; fail fast if the server process died (T-Q248 pattern)."""
    deadline = time.monotonic() + SERVER_READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"uvicorn exited with code {proc.returncode} before {url} was ready")
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"uvicorn did not become ready at {url} within {SERVER_READY_TIMEOUT_S}s")


@contextmanager
def serve_db(db_path: Path, extra_env: Mapping[str, str] | None = None) -> Iterator[str]:
    """Boot uvicorn (frozen clock) against the scratch DB at ``db_path``; yield its base URL.

    ``extra_env`` overrides the server's environment (first-run setup: env, setup token hash).

    Routes the server at `127.0.0.1:<free-port>`. Blocks until `/health` returns 200
    or raises after the ready timeout (cold `uv run` start can take >10 s).
    """
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "BUDGET_DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        # Plain HTTP → dev cookie names without ``Secure`` (ADR-0065/0070).
        "BUDGET_ENV": "dev",
        "BUDGET_VISUAL_FROZEN_DATE": FROZEN_DATE,
        # pragma: allowlist nextline secret
        "BUDGET_COOKIE_SECRET": "visual-dev-cookie-secret-not-a-real-secret",
        **(extra_env or {}),
    }
    cmd = ["uv", "run", "python", "-m", "tests.visual.frozen_server", str(port)]
    with subprocess.Popen(cmd, env=env) as proc:  # noqa: S603 — fixed args, local loopback port
        try:
            _wait_until_ready(f"{base}/health", proc)
            yield base
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


@pytest.fixture(scope="module")
def live_server(scratch_db: tuple[Path, str]) -> Iterator[str]:
    """The module's server: handoff seed for test_reference.py, demo copy otherwise."""
    with serve_db(scratch_db[0]) as base:
        yield base


@pytest.fixture(scope="session")
def handoff_server(
    tmp_path_factory: pytest.TempPathFactory,
) -> Callable[[Iterable[str]], AbstractContextManager[tuple[str, str]]]:
    """Factory for per-state servers: ``with handoff_server(("empty-ledger",)) as (url, token)``.

    Builds the handoff base seed with the named modifiers (``handoff_seed.MODIFIER_NAMES``)
    in a fresh scratch DB and serves it at the frozen date; the token is the session id
    for the dev session cookie.
    """

    @contextmanager
    def _serve(modifiers: Iterable[str]) -> Iterator[tuple[str, str]]:
        path = tmp_path_factory.mktemp("handoff-state") / "handoff.sqlite"
        result = build_seed(path, modifiers=modifiers)
        with serve_db(path) as base:
            yield base, result.session_token

    return _serve


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        b = p.chromium.launch(args=CHROMIUM_STABLE_ARGS)
        try:
            yield b
        finally:
            b.close()


@pytest.fixture(scope="module")
def session_cookies(live_server: str, scratch_db: tuple[Path, str]) -> list[dict[str, str]]:
    """Playwright ``add_cookies`` payload that signs the browser in as user 1."""
    return [{"name": SESSION_DEV_COOKIE_NAME, "value": scratch_db[1], "url": live_server}]


@pytest.fixture()
def update_baseline() -> bool:
    return bool(os.environ.get("VISUAL_UPDATE"))


@pytest.fixture()
def baselines_dir() -> Path:
    return BASELINES
