"""T-Q238 / OQ-24: Tailscale ACL drift diff and the settings-check wiring. No network."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
OWNER = "me@example.org"


def _load(name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS))
    return module


drift = _load("tailscale_acl_drift")
settings = _load("check_github_settings")


def _runbook() -> dict[str, object]:
    acl: dict[str, object] = drift.load_runbook_acl(drift.RUNBOOK_ACL, OWNER)
    return acl


def test_runbook_copy_parses_and_substitutes_owner() -> None:
    acl = _runbook()
    assert acl["tagOwners"]["tag:prod"] == [OWNER, "tag:automation"]  # type: ignore[index]
    assert "you@example.com" not in json.dumps(acl)


def test_identical_acl_has_no_drift_even_reordered() -> None:
    live = json.loads(json.dumps(_runbook()))
    live["acls"].reverse()
    live["tagOwners"]["tag:ci"].reverse()
    assert drift.diff_acl(live, _runbook()) == []


def test_extra_live_rule_is_reported() -> None:
    live = json.loads(json.dumps(_runbook()))
    live["acls"].append({"action": "accept", "src": ["*"], "dst": ["*:*"]})
    out = drift.diff_acl(live, _runbook())
    assert len(out) == 1
    assert out[0].startswith("acls: live-only rule") and '"*:*"' in out[0]


def test_missing_live_rule_changed_owner_and_extra_key() -> None:
    live = json.loads(json.dumps(_runbook()))
    live["acls"].pop()
    live["tagOwners"]["tag:prod"].append("evil@example.org")
    live["ssh"] = []
    out = drift.diff_acl(live, _runbook())
    assert any(line.startswith("acls: runbook-only rule") for line in out)
    assert any(line.startswith("tagOwners: live") and "evil@example.org" in line for line in out)
    assert "ssh: present live, absent from the runbook copy" in out


def test_hujson_comments_and_trailing_commas_ignored_urls_kept() -> None:
    doc = drift.parse_hujson('{ // c\n "a": "http://x//y", /* b */ "b": [1, 2,], }')
    assert doc == {"a": "http://x//y", "b": [1, 2]}


def test_compare_live_uses_injected_fetch_and_token() -> None:
    seen: list[tuple[str, str]] = []

    def fetch(url: str, token: str) -> bytes:
        seen.append((url, token))
        return json.dumps(_runbook()).encode()

    assert drift.compare_live("tok", OWNER, fetch=fetch) == []
    assert seen == [(drift.API_URL, "tok")]


def test_cli_without_token_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(drift.TOKEN_ENV, raising=False)
    assert drift.main(["--owner", OWNER]) == 2


def test_settings_check_skips_without_token() -> None:
    assert settings.check_tailscale_acl({}).status == settings.SKIP


def test_settings_check_reports_drift_without_leaking_token() -> None:
    env = {drift.TOKEN_ENV: "tskey-secret-value", drift.OWNER_ENV: OWNER}
    res = settings.check_tailscale_acl(env, lambda _t, _o: ["acls: live-only rule x"])
    assert res.status == settings.FAIL
    assert "live-only" in res.detail
    assert "tskey-secret-value" not in res.detail


def test_settings_check_passes_when_identical() -> None:
    env = {drift.TOKEN_ENV: "t", drift.OWNER_ENV: OWNER}
    assert settings.check_tailscale_acl(env, lambda _t, _o: []).status == settings.PASS
