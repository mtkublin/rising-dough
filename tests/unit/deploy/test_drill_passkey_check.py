"""Unit tests for the pure parts of scripts/drill/passkey_check.py (no browser)."""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "drill" / "passkey_check.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("passkey_check_unit", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pc = _load()


def test_reads_current_password_only() -> None:
    creds = pc.read_credentials(io.StringIO("hunter2-dummy\n"))
    assert creds.current == "hunter2-dummy"
    assert creds.new is None


def test_reads_optional_new_password() -> None:
    creds = pc.read_credentials(io.StringIO("old-dummy\nnew-dummy-password\n"))
    assert creds.new == "new-dummy-password"


def test_rejects_empty_stdin() -> None:
    with pytest.raises(pc.CheckError, match="no password"):
        pc.read_credentials(io.StringIO(""))


def test_rejects_short_new_password() -> None:
    with pytest.raises(pc.CheckError, match="at least"):
        pc.read_credentials(io.StringIO("old-dummy\nshort\n"))


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000", "https://[::1]/", "ftp://host", "nohost"])
def test_rejects_bad_base_url(url: str) -> None:
    with pytest.raises(pc.CheckError):
        pc.validate_base_url(url)


def test_normalises_base_url() -> None:
    assert (
        pc.validate_base_url("https://drill.example.ts.net/path") == "https://drill.example.ts.net"
    )


def test_password_is_not_an_argument() -> None:
    with pytest.raises(SystemExit):
        pc.parse_args(["--base-url", "https://h.test", "--username", "a@b.test", "--password", "x"])
