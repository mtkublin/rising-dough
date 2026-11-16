"""T-D15 — graceful shutdown via lifespan + SIGTERM observer.

Boot uvicorn in a subprocess, hit /health, send SIGTERM, and assert the
process exits cleanly within the deadline. Confirms the lifespan is
properly wired and the SIGTERM handler does not block the drain.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

# Windows does not support SIGTERM the same way; skip the whole module.
if sys.platform == "win32":  # pragma: no cover
    pytest.skip("SIGTERM semantics differ on Windows", allow_module_level=True)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_until_ready(base_url: str, deadline: float) -> None:
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/health", timeout=0.5)
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"server did not become ready at {base_url}")


def test_sigterm_leads_to_clean_exit(tmp_path: Path) -> None:
    port = _free_port()
    db_path = tmp_path / "shutdown.sqlite"
    env = os.environ.copy()
    env["BUDGET_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    env["BUDGET_BIND_HOST"] = "127.0.0.1"
    env["BUDGET_BIND_PORT"] = str(port)
    env["BUDGET_ENV"] = "test"
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
        [
            sys.executable,
            "-m",
            "uvicorn",
            "budget_planner.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_ready(base_url, deadline=time.monotonic() + 15)
        proc.send_signal(signal.SIGTERM)
        rc = proc.wait(timeout=10)
    except Exception:
        proc.kill()
        proc.wait(timeout=5)
        raise

    # Uvicorn's default is to drain cleanly then re-raise SIGTERM so the
    # process exits with signal 15 — the POSIX convention container
    # orchestrators treat as "clean exit via signal". Either outcome
    # proves the lifespan did not crash.
    assert rc in (0, -signal.SIGTERM), (
        f"uvicorn exited with an unexpected code on SIGTERM: {rc} (expected 0 or -SIGTERM)."
    )
