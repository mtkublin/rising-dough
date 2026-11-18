"""DRILL-2 helper scripts/drill/passkey_check.py against a local scratch instance.

Uses the e2e ``live_server`` fixture (temp SQLite, never ``data/budget.sqlite``)
reached as ``http://localhost:<port>`` so the RP ID is a valid host name.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType
from urllib.parse import urlsplit

import pytest

from tests.auth_support import TEST_EMAIL, TEST_PASSWORD

pytestmark = pytest.mark.e2e

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "drill" / "passkey_check.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("passkey_check", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pc = _load()


def test_script_registers_and_signs_in_with_passkey(
    live_server: tuple[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    base_url, _ = live_server
    port = urlsplit(base_url).port
    rc = pc.main(
        ["--base-url", f"http://localhost:{port}", "--username", TEST_EMAIL],
        stdin=io.StringIO(f"{TEST_PASSWORD}\n"),
    )
    out = capsys.readouterr()
    assert rc == 0, out.err
    assert out.out.startswith("PASS:")
    assert "passkey sign-in" in out.out
    assert TEST_PASSWORD not in out.out + out.err


def test_script_fails_cleanly_on_wrong_password(
    live_server: tuple[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    base_url, _ = live_server
    port = urlsplit(base_url).port
    rc = pc.main(
        ["--base-url", f"http://localhost:{port}", "--username", TEST_EMAIL],
        stdin=io.StringIO("definitely-not-the-password\n"),
    )
    out = capsys.readouterr()
    assert rc == 1
    assert "rejected" in out.err
    assert "definitely-not-the-password" not in out.out + out.err
