"""DRILL-2 helper scripts/drill/passkey_check.py against a local scratch instance.

Runs the script as a real subprocess (exactly as an operator does) so its sync
Playwright code is isolated from the test process's asyncio loop. Uses the e2e
``live_server`` fixture (temp SQLite, never ``data/budget.sqlite``) reached as
``http://localhost:<port>`` so the RP ID is a valid host name.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.auth_support import TEST_EMAIL, TEST_PASSWORD

pytestmark = pytest.mark.e2e

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "drill" / "passkey_check.py"
TIMEOUT_SECONDS = 120


def _run(base_url: str, password: str) -> subprocess.CompletedProcess[str]:
    port = urlsplit(base_url).port
    return subprocess.run(  # noqa: S603  (fixed argv, no shell)
        [
            sys.executable,
            str(SCRIPT),
            "--base-url",
            f"http://localhost:{port}",
            "--username",
            TEST_EMAIL,
        ],
        input=f"{password}\n",
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )


def test_script_registers_and_signs_in_with_passkey(live_server: tuple[str, Path]) -> None:
    base_url, _ = live_server
    result = _run(base_url, TEST_PASSWORD)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("PASS:")
    assert "passkey sign-in" in result.stdout
    assert TEST_PASSWORD not in result.stdout + result.stderr


def test_script_fails_cleanly_on_wrong_password(live_server: tuple[str, Path]) -> None:
    base_url, _ = live_server
    wrong = "definitely-not-the-password"
    result = _run(base_url, wrong)
    assert result.returncode == 1
    assert "rejected" in result.stderr
    assert wrong not in result.stdout + result.stderr
