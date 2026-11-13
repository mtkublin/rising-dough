"""T-D78: read-only Terraform preflight. All HTTP mocked; no network, no real secrets."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("preflight", ROOT / "terraform/scripts/preflight.py")
assert _spec is not None and _spec.loader is not None
pf: Any = importlib.util.module_from_spec(_spec)
sys.modules["preflight"] = pf
_spec.loader.exec_module(pf)

NOW = datetime(2026, 11, 6, 12, 0, 0, tzinfo=UTC)
SECRETS = {
    "SCW_ACCESS_KEY": "SCWFAKE",
    "SCW_SECRET_KEY": "fake-scw-secret-value-aaaa",  # pragma: allowlist secret
    "TF_VAR_tailscale_oauth_client_id": "fakeclientid",
    "TF_VAR_tailscale_oauth_client_secret": "tskey-client-FAKE",  # pragma: allowlist secret
    "TF_VAR_litestream_age_identity": "# created\nAGE-SECRET-KEY-1FAKEFAKEFAKE",
    "TF_VAR_litestream_age_recipient": "age1fakerecipient",
    "TF_VAR_ghcr_pull_pat": "ghp_FAKEPATVALUE",
    "TF_VAR_app_scw_access_key": "SCWFAKEAPP",
    "TF_VAR_app_scw_secret_key": "fake-app-secret-value-bbbb",  # pragma: allowlist secret
}
PROJECT = "11111111-1111-1111-1111-111111111111"
ENVIRON = {**SECRETS, "SCW_DEFAULT_PROJECT_ID": PROJECT}
TFVARS = {
    "scaleway_project_id": PROJECT,
    "github_owner": "acme",
    "app_image_tag": "main",
}


def ok(body: object = "") -> Any:
    return pf.HttpResponse(200, body if isinstance(body, str) else json.dumps(body))


class FakeHttp:
    """Routes by (method, url-substring); records every call."""

    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method: str, url: str, headers: Any, data: bytes | None) -> Any:
        self.calls.append((method, url))
        for (m, fragment), resp in self.routes.items():
            if m == method and fragment in url:
                return resp
        return pf.HttpResponse(0, "")


def ts_routes(create: Any, delete: Any | None = None) -> dict[tuple[str, str], Any]:
    return {
        ("POST", "/oauth/token"): ok({"access_token": "tok"}),
        ("POST", "/tailnet/-/keys"): create,
        ("DELETE", "/keys/k123"): delete or pf.HttpResponse(200, ""),
    }


# --- inputs ----------------------------------------------------------------


def test_inputs_all_good() -> None:
    results = pf.check_inputs(ENVIRON)
    assert {r.status for r in results} == {"PASS"}
    assert len(results) == 9


@pytest.mark.parametrize(
    ("name", "value", "fragment"),
    [
        ("SCW_ACCESS_KEY", "", "unset"),
        ("SCW_SECRET_KEY", "<your-secret>", "placeholder"),
        ("TF_VAR_tailscale_oauth_client_secret", "wrongprefix", "tskey-client-"),
        ("TF_VAR_litestream_age_identity", "age1notanidentity", "AGE-SECRET-KEY-1"),
        ("TF_VAR_litestream_age_recipient", "AGE-SECRET-KEY-1x", "age1"),
        ("TF_VAR_ghcr_pull_pat", "gho_nope", "ghp_ or github_pat_"),
    ],
)
def test_input_fails(name: str, value: str, fragment: str) -> None:
    results = pf.check_inputs({**ENVIRON, name: value})
    bad = [r for r in results if r.status == "FAIL"]
    assert [r.name for r in bad] == [name]
    assert fragment in bad[0].detail
    assert value == "" or value not in bad[0].detail


def test_input_accepts_github_pat_prefix() -> None:
    env = {**ENVIRON, "TF_VAR_ghcr_pull_pat": "github_pat_FAKE"}
    assert {r.status for r in pf.check_inputs(env)} == {"PASS"}


# --- project ---------------------------------------------------------------


def test_project_pass_and_tfvar_env_fallback() -> None:
    assert pf.check_project("drill", TFVARS, ENVIRON).status == "PASS"
    env = {**ENVIRON, "TF_VAR_scaleway_project_id": PROJECT}
    assert pf.check_project("drill", {}, env).status == "PASS"


def test_project_mismatch_fails() -> None:
    env = {**ENVIRON, "SCW_DEFAULT_PROJECT_ID": "other"}
    result = pf.check_project("drill", TFVARS, env)
    assert result.status == "FAIL"
    assert "differs" in result.detail
    assert "other" not in result.detail


def test_project_unset_hints_drill_var() -> None:
    result = pf.check_project("drill", TFVARS, {})
    assert result.status == "FAIL"
    assert "SCW_DRILL_PROJECT_ID" in result.detail
    assert "SCW_DRILL_PROJECT_ID" not in pf.check_project("prod", TFVARS, {}).detail


def test_project_expected_missing_fails() -> None:
    assert pf.check_project("prod", {}, ENVIRON).status == "FAIL"


# --- image -----------------------------------------------------------------


def image_http(manifest: Any) -> FakeHttp:
    return FakeHttp(
        {("GET", "ghcr.io/token"): ok({"token": "bearer"}), ("GET", "/manifests/main"): manifest}
    )


def test_image_pass() -> None:
    http = image_http(ok("{}"))
    result = pf.check_image(TFVARS, ENVIRON, http)
    assert result.status == "PASS"
    assert "ghcr.io/acme/budget-planner:main" in result.detail


def test_image_missing_reports_name_unknown() -> None:
    body = json.dumps({"errors": [{"code": "NAME_UNKNOWN"}]})
    result = pf.check_image(TFVARS, ENVIRON, image_http(pf.HttpResponse(404, body)))
    assert result.status == "FAIL"
    assert "NAME_UNKNOWN" in result.detail


def test_image_missing_with_unparseable_body() -> None:
    result = pf.check_image(TFVARS, ENVIRON, image_http(pf.HttpResponse(404, "not json")))
    assert result.status == "FAIL"
    assert "HTTP 404" in result.detail


def test_image_token_failure_and_missing_inputs() -> None:
    http = FakeHttp({("GET", "ghcr.io/token"): pf.HttpResponse(401, "")})
    assert "HTTP 401" in pf.check_image(TFVARS, ENVIRON, http).detail
    assert pf.check_image({}, {}, http).status == "FAIL"


# --- tailscale -------------------------------------------------------------


def test_tailscale_pass_deletes_key_and_requests_no_tags_on_token() -> None:
    http = FakeHttp(ts_routes(ok({"id": "k123", "key": "tskey-auth-SECRETKEY"})))
    result = pf.check_tailscale("drill", ENVIRON, http)
    assert result.status == "PASS"
    assert ("DELETE", "https://api.tailscale.com/api/v2/tailnet/-/keys/k123") in http.calls
    assert "SECRETKEY" not in result.detail


def test_tailscale_payload_shape() -> None:
    payload = json.loads(pf._mint_payload("tag:prod"))
    create = payload["capabilities"]["devices"]["create"]
    assert create == {
        "reusable": False,
        "ephemeral": True,
        "preauthorized": True,
        "tags": ["tag:prod"],
    }
    assert payload["expirySeconds"] == 300
    assert payload["description"] == "preflight-delete-me"


def test_tailscale_tag_error_gives_automation_hint() -> None:
    body = "requested tags [tag:drill] are invalid or not permitted"
    http = FakeHttp(ts_routes(pf.HttpResponse(400, body)))
    result = pf.check_tailscale("drill", ENVIRON, http)
    assert result.status == "FAIL"
    assert "tag:automation" in result.detail
    assert not any(m == "DELETE" for m, _ in http.calls)


def test_tailscale_other_create_failure() -> None:
    http = FakeHttp(ts_routes(pf.HttpResponse(500, "boom")))
    assert "HTTP 500" in pf.check_tailscale("drill", ENVIRON, http).detail


def test_tailscale_delete_failure_is_reported() -> None:
    http = FakeHttp(ts_routes(ok({"id": "k123"}), pf.HttpResponse(500, "")))
    result = pf.check_tailscale("prod", ENVIRON, http)
    assert result.status == "FAIL"
    assert "preflight-delete-me" in result.detail
    assert "tag:prod" in result.detail


def test_tailscale_key_deleted_even_if_later_step_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    http = FakeHttp(ts_routes(ok({"id": "k123"})))

    class BoomError(Exception):
        pass

    def explode(*_a: Any, **_k: Any) -> Any:
        raise BoomError

    monkeypatch.setattr(pf, "CheckResult", explode)
    with pytest.raises(BoomError):
        pf.check_tailscale("drill", ENVIRON, http)
    assert ("DELETE", "https://api.tailscale.com/api/v2/tailnet/-/keys/k123") in http.calls


def test_tailscale_oauth_failures() -> None:
    http = FakeHttp({("POST", "/oauth/token"): pf.HttpResponse(401, "")})
    assert "HTTP 401" in pf.check_tailscale("drill", ENVIRON, http).detail
    assert pf.check_tailscale("drill", {}, http).status == "FAIL"


# --- backend ---------------------------------------------------------------


def make_tf_dir(tmp_path: Path, hcl: str | None) -> Path:
    env_dir = tmp_path / "envs" / "drill"
    env_dir.mkdir(parents=True)
    if hcl is not None:
        (env_dir / "backend.hcl").write_text(hcl)
    return tmp_path


HCL = (
    'bucket = "state-bucket"\nregion = "pl-waw"\n'
    'endpoints = { s3 = "https://s3.pl-waw.scw.cloud" }\n'
)


def test_backend_pass_signs_head_without_leaking_secret(tmp_path: Path) -> None:
    sent: list[Any] = []

    def http(method: str, url: str, headers: Any, data: bytes | None) -> Any:
        sent.append((method, url, dict(headers)))
        return ok()

    result = pf.check_backend("drill", ENVIRON, http, lambda: NOW, make_tf_dir(tmp_path, HCL))
    assert result.status == "PASS"
    method, url, headers = sent[0]
    assert (method, url) == ("HEAD", "https://s3.pl-waw.scw.cloud/state-bucket")
    assert headers["x-amz-date"] == "20261106T120000Z"
    assert (
        "Credential=SCWFAKE/20261106/pl-waw/s3/aws4_request"  # pragma: allowlist secret
        in headers["Authorization"]
    )
    assert ENVIRON["SCW_SECRET_KEY"] not in json.dumps(headers)


def test_backend_forbidden_fails(tmp_path: Path) -> None:
    http = FakeHttp({("HEAD", "state-bucket"): pf.HttpResponse(403, "")})
    result = pf.check_backend("drill", ENVIRON, http, lambda: NOW, make_tf_dir(tmp_path, HCL))
    assert result.status == "FAIL"
    assert "403" in result.detail


def test_backend_config_problems(tmp_path: Path) -> None:
    http = FakeHttp({})
    no_file = make_tf_dir(tmp_path / "a", None)
    assert pf.check_backend("drill", ENVIRON, http, lambda: NOW, no_file).status == "FAIL"
    bad = make_tf_dir(tmp_path / "b", 'region = "pl-waw"\n')
    assert "missing" in pf.check_backend("drill", ENVIRON, http, lambda: NOW, bad).detail
    good = make_tf_dir(tmp_path / "c", HCL)
    assert "unset" in pf.check_backend("drill", {}, http, lambda: NOW, good).detail
    assert http.calls == []


def test_real_backend_hcl_files_parse() -> None:
    for env in ("drill", "prod"):
        text = (ROOT / f"terraform/envs/{env}/backend.hcl").read_text()
        assert pf.parse_string_assignments(text)["bucket"]
        assert pf.parse_s3_endpoint(text).startswith("https://")


# --- parsing and runner ----------------------------------------------------


def test_read_tfvars_missing_file(tmp_path: Path) -> None:
    assert pf.read_tfvars("drill", tmp_path) == {}


def test_run_checks_and_main_output_never_contains_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    tf_dir = make_tf_dir(tmp_path, HCL)
    (tf_dir / "envs/drill/terraform.tfvars").write_text(
        f'scaleway_project_id = "{PROJECT}"\ngithub_owner = "acme"\napp_image_tag = "main"\n'
    )
    http = FakeHttp(
        {
            ("GET", "ghcr.io/token"): ok({"token": "bearer"}),
            ("GET", "/manifests/main"): ok("{}"),
            **ts_routes(ok({"id": "k123", "key": "tskey-auth-LEAK"})),
            ("HEAD", "state-bucket"): ok(),
        }
    )
    results = pf.run_checks("drill", ENVIRON, http, lambda: NOW, tf_dir)
    assert {r.status for r in results} == {"PASS"}

    monkeypatch.setattr(pf, "run_checks", lambda *_a: results)
    assert pf.main(["preflight.py", "drill"]) == 0
    out = capsys.readouterr().out
    for secret in [*SECRETS.values(), "tskey-auth-LEAK", "bearer"]:
        assert secret not in out
    assert "PASS" in out


def test_main_exit_codes(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert pf.main(["preflight.py"]) == 2
    assert pf.main(["preflight.py", "staging"]) == 2
    failing = (pf.CheckResult("x", "FAIL", "nope"),)
    monkeypatch.setattr(pf, "run_checks", lambda *_a: failing)
    assert pf.main(["preflight.py", "prod"]) == 1
    assert "FAIL x: nope" in capsys.readouterr().out
