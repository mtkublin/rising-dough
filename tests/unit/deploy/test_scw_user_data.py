"""scripts/ci/scw_user_data.py: the drain request key (T-D157, ADR-0127 amendment). No network."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "scw_user_data", ROOT / "scripts/ci/scw_user_data.py"
)
assert _spec is not None
assert _spec.loader is not None
ud = importlib.util.module_from_spec(_spec)
sys.modules["scw_user_data"] = ud
_spec.loader.exec_module(ud)

SERVER = "pl-waw-2/0e39bbe5-f2e5-4991-9740-1c3c8022b232"
URL = (
    "https://api.scaleway.com/instance/v1/zones/pl-waw-2/servers/"
    "0e39bbe5-f2e5-4991-9740-1c3c8022b232/user_data/bp-drain"
)
TOKEN = "scw-secret-TOKEN"  # noqa: S105  # pragma: allowlist secret


class _Api:
    def __init__(self, status: int = 204) -> None:
        self.status = status
        self.calls: list[tuple[str, str, bytes | None, dict[str, str]]] = []

    def __call__(
        self, method: str, url: str, body: bytes | None, headers: Mapping[str, str]
    ) -> int:
        self.calls.append((method, url, body, dict(headers)))
        return self.status


def test_set_patches_only_the_drain_key_as_text() -> None:
    api = _Api()

    assert (
        ud.main(
            ["set", "--server", SERVER, "--value", "44513330068-1"], {"SCW_SECRET_KEY": TOKEN}, api
        )
        == 0
    )

    assert api.calls == [
        (
            "PATCH",
            URL,
            b"44513330068-1",
            {"X-Auth-Token": TOKEN, "Content-Type": "text/plain"},
        )
    ]


def test_delete_tolerates_a_missing_key() -> None:
    for status in (204, 404):
        api = _Api(status)
        assert ud.main(["delete", "--server", SERVER], {"SCW_SECRET_KEY": TOKEN}, api) == 0
        assert api.calls[0][:3] == ("DELETE", URL, None)


@pytest.mark.parametrize(("cmd", "status"), [("set", 403), ("set", 404), ("delete", 500)])
def test_api_errors_fail_without_printing_the_token(
    cmd: str, status: int, capsys: pytest.CaptureFixture[str]
) -> None:
    args = [cmd, "--server", SERVER] + (["--value", "r1"] if cmd == "set" else [])

    assert ud.main(args, {"SCW_SECRET_KEY": TOKEN}, _Api(status)) == 1

    out = capsys.readouterr()
    assert f"HTTP {status}" in out.err
    assert TOKEN not in out.out + out.err


@pytest.mark.parametrize(
    "server", ["0e39bbe5-f2e5-4991-9740-1c3c8022b232", "pl-waw-2/../bp-config", "x/y"]
)
def test_server_must_be_zone_and_uuid(server: str) -> None:
    api = _Api()
    assert ud.main(["delete", "--server", server], {"SCW_SECRET_KEY": TOKEN}, api) == 1
    assert api.calls == []


@pytest.mark.parametrize("value", ["", "a b", "x;rm -rf /", "a" * 65])
def test_value_must_be_a_request_id(value: str) -> None:
    api = _Api()
    assert (
        ud.main(["set", "--server", SERVER, "--value", value], {"SCW_SECRET_KEY": TOKEN}, api) == 1
    )
    assert api.calls == []


def test_missing_token_is_refused() -> None:
    api = _Api()
    assert ud.main(["delete", "--server", SERVER], {}, api) == 1
    assert api.calls == []


def test_only_the_drain_key_is_reachable() -> None:
    assert ud.KEY == "bp-drain"
    assert ud.key_url(SERVER).endswith("/user_data/bp-drain")
