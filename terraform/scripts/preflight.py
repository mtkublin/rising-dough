#!/usr/bin/env python3
"""Read-only Terraform apply preflight (T-D78).

Checks, in seconds, everything that broke or nearly broke the first real drill
apply (2026-11-06): required inputs, project match, app image on GHCR, the
Tailscale OAuth client's tag ownership, and state backend reachability.

Every check prints PASS / FAIL with a one-line reason and never prints a secret
value (only lengths and prefix status). Exit 1 if any check FAILs.

Usage: python3 preflight.py {drill,prod}
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path

_TF_DIR = Path(__file__).resolve().parent.parent
_TIMEOUT_S = 15
_ARGC = 2
_TS_API = "https://api.tailscale.com/api/v2"
_KEY_DESCRIPTION = "preflight-delete-me"
_MANIFEST_ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)
_TAG_HINT = (
    "the Tailscale OAuth client must carry tag:automation, which owns the env tag "
    "(ADR-0094 amendment, T-D73)"
)

PASS = "PASS"  # noqa: S105
FAIL = "FAIL"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class HttpResponse:
    status: int  # 0 = transport failure
    body: str


Http = Callable[[str, str, Mapping[str, str], bytes | None], HttpResponse]
Now = Callable[[], datetime]


@dataclass(frozen=True)
class InputSpec:
    env_name: str
    prefixes: tuple[str, ...] = ()
    any_line: bool = False  # prefix may be on any line (multi-line age key files)


INPUT_SPECS: tuple[InputSpec, ...] = (
    InputSpec("SCW_ACCESS_KEY", ("SCW",)),
    InputSpec("SCW_SECRET_KEY"),
    InputSpec("TF_VAR_tailscale_oauth_client_id"),
    InputSpec("TF_VAR_tailscale_oauth_client_secret", ("tskey-client-",)),
    InputSpec("TF_VAR_litestream_age_identity", ("AGE-SECRET-KEY-1",), any_line=True),
    InputSpec("TF_VAR_litestream_age_recipient", ("age1",)),
    InputSpec("TF_VAR_ghcr_pull_pat", ("ghp_", "github_pat_")),
)


# --- parsing ---------------------------------------------------------------


def parse_string_assignments(text: str) -> dict[str, str]:
    """Top-level ``key = "value"`` pairs from a tfvars/backend.hcl file."""
    pairs: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r'^\s*([A-Za-z_][\w-]*)\s*=\s*"([^"]*)"', line)
        if match:
            pairs[match.group(1)] = match.group(2)
    return pairs


def parse_s3_endpoint(text: str) -> str | None:
    match = re.search(r'endpoints\s*=\s*\{[^}]*?s3\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else None


def read_tfvars(env: str, tf_dir: Path = _TF_DIR) -> dict[str, str]:
    path = tf_dir / "envs" / env / "terraform.tfvars"
    return parse_string_assignments(path.read_text()) if path.is_file() else {}


def resolve_var(name: str, tfvars: Mapping[str, str], environ: Mapping[str, str]) -> str:
    """tfvars value first (as with ``-var-file``), then ``TF_VAR_<name>``."""
    return tfvars.get(name) or environ.get(f"TF_VAR_{name}", "").strip()


# --- 1. inputs -------------------------------------------------------------


def check_input(spec: InputSpec, environ: Mapping[str, str]) -> CheckResult:
    value = environ.get(spec.env_name, "")
    name = spec.env_name
    if not value.strip():
        return CheckResult(name, FAIL, "unset or empty")
    if "<" in value:
        return CheckResult(name, FAIL, f"looks like a placeholder (has '<'), len {len(value)}")
    if not spec.prefixes:
        return CheckResult(name, PASS, f"set, len {len(value)}")
    lines = value.splitlines() if spec.any_line else [value]
    if any(line.strip().startswith(spec.prefixes) for line in lines):
        return CheckResult(name, PASS, f"set, len {len(value)}, prefix ok")
    wanted = " or ".join(spec.prefixes)
    return CheckResult(name, FAIL, f"len {len(value)}, expected prefix {wanted}")


def check_inputs(environ: Mapping[str, str]) -> tuple[CheckResult, ...]:
    return tuple(check_input(spec, environ) for spec in INPUT_SPECS)


# --- 2. project match ------------------------------------------------------


def check_project(env: str, tfvars: Mapping[str, str], environ: Mapping[str, str]) -> CheckResult:
    name = "project match"
    expected = resolve_var("scaleway_project_id", tfvars, environ)
    actual = environ.get("SCW_DEFAULT_PROJECT_ID", "").strip()
    if not actual:
        hint = " (drill: set SCW_DRILL_PROJECT_ID, the recipe maps it)" if env == "drill" else ""
        return CheckResult(name, FAIL, f"SCW_DEFAULT_PROJECT_ID is unset{hint}")
    if not expected:
        return CheckResult(name, FAIL, "scaleway_project_id not in tfvars or TF_VAR_")
    if actual != expected:
        return CheckResult(
            name,
            FAIL,
            "SCW_DEFAULT_PROJECT_ID differs from scaleway_project_id "
            "(the provider would use the env value)",
        )
    return CheckResult(name, PASS, "SCW_DEFAULT_PROJECT_ID equals scaleway_project_id")


# --- 3. GHCR image ---------------------------------------------------------


def _basic(user: str, secret: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{secret}".encode()).decode()


def _json_field(body: str, field: str) -> str | None:
    try:
        node = json.loads(body)
    except ValueError:
        return None
    value = node.get(field) if isinstance(node, dict) else None
    return value if isinstance(value, str) else None


def _error_code(body: str) -> str | None:
    try:
        node = json.loads(body)
    except ValueError:
        return None
    errors = node.get("errors") if isinstance(node, dict) else None
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        code = errors[0].get("code")
        return code if isinstance(code, str) else None
    return None


def check_image(tfvars: Mapping[str, str], environ: Mapping[str, str], http: Http) -> CheckResult:
    name = "ghcr image"
    owner = resolve_var("github_owner", tfvars, environ)
    tag = resolve_var("app_image_tag", tfvars, environ)
    pat = resolve_var("ghcr_pull_pat", tfvars, environ)
    if not (owner and tag and pat):
        return CheckResult(name, FAIL, "need github_owner, app_image_tag and ghcr_pull_pat")
    repo = f"{owner}/budget-planner"
    ref = f"ghcr.io/{repo}:{tag}"
    scope = urllib.parse.urlencode({"scope": f"repository:{repo}:pull"})
    tok = http("GET", f"https://ghcr.io/token?{scope}", {"Authorization": _basic(owner, pat)}, None)
    token = _json_field(tok.body, "token") if tok.status == HTTPStatus.OK else None
    if token is None:
        return CheckResult(name, FAIL, f"GHCR token request failed (HTTP {tok.status})")
    manifest = http(
        "GET",
        f"https://ghcr.io/v2/{repo}/manifests/{urllib.parse.quote(tag)}",
        {"Authorization": f"Bearer {token}", "Accept": _MANIFEST_ACCEPT},
        None,
    )
    if manifest.status == HTTPStatus.OK:
        return CheckResult(name, PASS, f"{ref} exists")
    code = _error_code(manifest.body)
    suffix = f" {code}" if code else ""
    return CheckResult(name, FAIL, f"{ref} not found (HTTP {manifest.status}{suffix})")


# --- 4. Tailscale ----------------------------------------------------------


def _mint_payload(tag: str) -> bytes:
    return json.dumps(
        {
            "capabilities": {
                "devices": {
                    "create": {
                        "reusable": False,
                        "ephemeral": True,
                        "preauthorized": True,
                        "tags": [tag],
                    }
                }
            },
            "expirySeconds": 300,
            "description": _KEY_DESCRIPTION,
        }
    ).encode()


def _create_failure(name: str, tag: str, created: HttpResponse) -> CheckResult:
    lowered = created.body.lower()
    if created.status == HTTPStatus.BAD_REQUEST and "tags" in lowered and "permitted" in lowered:
        return CheckResult(name, FAIL, f"{tag} not permitted: {_TAG_HINT}")
    return CheckResult(name, FAIL, f"key creation failed (HTTP {created.status})")


def check_tailscale(env: str, environ: Mapping[str, str], http: Http) -> CheckResult:
    name = "tailscale tag"
    tag = f"tag:{env}"
    client_id = environ.get("TF_VAR_tailscale_oauth_client_id", "").strip()
    client_secret = environ.get("TF_VAR_tailscale_oauth_client_secret", "").strip()
    if not (client_id and client_secret):
        return CheckResult(name, FAIL, "OAuth client id/secret unset")
    form = urllib.parse.urlencode(
        {"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"}
    ).encode()
    form_header = {"Content-Type": "application/x-www-form-urlencoded"}
    tok = http("POST", f"{_TS_API}/oauth/token", form_header, form)
    access = _json_field(tok.body, "access_token") if tok.status == HTTPStatus.OK else None
    if access is None:
        return CheckResult(name, FAIL, f"OAuth token request failed (HTTP {tok.status})")
    auth = {"Authorization": f"Bearer {access}"}
    created = http(
        "POST",
        f"{_TS_API}/tailnet/-/keys",
        {**auth, "Content-Type": "application/json"},
        _mint_payload(tag),
    )
    key_id = _json_field(created.body, "id") if created.status == HTTPStatus.OK else None
    if key_id is None:
        return _create_failure(name, tag, created)
    try:
        result = CheckResult(name, PASS, f"OAuth client can mint a key for {tag}; test key deleted")
    finally:
        deleted = http("DELETE", f"{_TS_API}/tailnet/-/keys/{key_id}", auth, None)
    if deleted.status not in (200, 204):
        return CheckResult(
            name,
            FAIL,
            f"minted a key for {tag} but deleting it failed (HTTP {deleted.status}); "
            f"remove '{_KEY_DESCRIPTION}' in the Tailscale admin console",
        )
    return result


# --- 5. state backend (SigV4 HEAD, stdlib only) -----------------------------


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sign_head_bucket(
    endpoint: str, bucket: str, region: str, *, access: str, secret: str, now: datetime
) -> tuple[str, dict[str, str]]:
    """SigV4-sign a path-style ``HEAD /<bucket>``; returns (url, headers)."""
    host = urllib.parse.urlparse(endpoint).netloc
    path = f"/{bucket}"
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    payload_hash = hashlib.sha256(b"").hexdigest()
    signed = "host;x-amz-content-sha256;x-amz-date"
    canonical = (
        f"HEAD\n{path}\n\nhost:{host}\nx-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n\n{signed}\n{payload_hash}"
    )
    scope = f"{day}/{region}/s3/aws4_request"
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{digest}"
    key = _hmac(("AWS4" + secret).encode(), day)
    for part in (region, "s3", "aws4_request"):
        key = _hmac(key, part)
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers = {
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={access}/{scope}, "
            f"SignedHeaders={signed}, Signature={signature}"
        ),
    }
    return endpoint.rstrip("/") + path, headers


def check_backend(
    env: str, environ: Mapping[str, str], http: Http, now: Now, tf_dir: Path = _TF_DIR
) -> CheckResult:
    name = "state backend"
    path = tf_dir / "envs" / env / "backend.hcl"
    if not path.is_file():
        return CheckResult(name, FAIL, f"backend.hcl not found for {env}")
    text = path.read_text()
    cfg = parse_string_assignments(text)
    bucket, endpoint = cfg.get("bucket"), parse_s3_endpoint(text)
    access, secret = environ.get("SCW_ACCESS_KEY", ""), environ.get("SCW_SECRET_KEY", "")
    if not (bucket and endpoint):
        return CheckResult(name, FAIL, "bucket or s3 endpoint missing in backend.hcl")
    if not (access and secret):
        return CheckResult(name, FAIL, "SCW_ACCESS_KEY / SCW_SECRET_KEY unset")
    region = cfg.get("region", "pl-waw")
    url, headers = sign_head_bucket(
        endpoint, bucket, region, access=access, secret=secret, now=now()
    )
    resp = http("HEAD", url, headers, None)
    if resp.status == HTTPStatus.OK:
        return CheckResult(name, PASS, f"bucket {bucket} reachable with the SCW keys")
    return CheckResult(name, FAIL, f"HEAD bucket {bucket} returned HTTP {resp.status}")


# --- runner ----------------------------------------------------------------


def http_request(
    method: str, url: str, headers: Mapping[str, str], data: bytes | None
) -> HttpResponse:  # pragma: no cover - real network
    if not url.startswith("https://"):
        return HttpResponse(0, "")
    request = urllib.request.Request(url, data=data, method=method, headers=dict(headers))  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as resp:  # noqa: S310
            return HttpResponse(resp.status, resp.read().decode(errors="replace"))
    except urllib.error.HTTPError as exc:
        return HttpResponse(exc.code, exc.read().decode(errors="replace"))
    except (urllib.error.URLError, TimeoutError, OSError):
        return HttpResponse(0, "")


def run_checks(
    env: str, environ: Mapping[str, str], http: Http, now: Now, tf_dir: Path = _TF_DIR
) -> tuple[CheckResult, ...]:
    tfvars = read_tfvars(env, tf_dir)
    return (
        *check_inputs(environ),
        check_project(env, tfvars, environ),
        check_image(tfvars, environ, http),
        check_tailscale(env, environ, http),
        check_backend(env, environ, http, now, tf_dir),
    )


def format_result(result: CheckResult) -> str:
    return f"{result.status:<4} {result.name}: {result.detail}"


def main(argv: list[str]) -> int:
    if len(argv) != _ARGC or argv[1] not in ("drill", "prod"):
        print("usage: preflight.py {drill,prod}", file=sys.stderr)
        return 2
    results = run_checks(argv[1], os.environ, http_request, lambda: datetime.now(UTC))
    for result in results:
        print(format_result(result))
    failed = sum(1 for r in results if r.status == FAIL)
    print(f"{len(results) - failed}/{len(results)} checks ok" + (", FAILED" if failed else ""))
    print("Also run `terraform fmt -check` and validate (or T-D77 tf-render-check when present).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
