"""Single source of the `TF_VAR_*` mapping for terraform.yml (T-D133, T-D70, ADR-0093).

Every Terraform input reaches CI as a `TF_VAR_*` variable taken from the job's
GitHub secrets or variables. Workflow-level `env:` cannot read environment
secrets, and a job `env:` block per job repeated ~25 lines (plan and apply), so
the mapping lives here once. The composite action `.github/actions/terraform-env`
passes `toJSON(secrets)` and `toJSON(vars)`; this script appends one `NAME=value`
entry per input to `$GITHUB_ENV`.

Each `Entry(var, source, name, default, only_env)`:
  source     "secret" | "var" | "env" (the target env) | "owner" | "run_id"
  default    used when the value is empty (replaces `secrets.X || 'default'`)
  only_env   the value is emitted only for that env, otherwise it is empty
             (replaces `env == 'drill' && vars.X || ''`; keeps drill-only inputs
             out of prod, T-D137)
  restore_only  the value is emitted only with `--restore-source` (ADR-0132): the
             prod replica read key reaches a drill only from the restore drill's
             apply, which runs in the gated `prod-restore-read` environment

Usage: python3 tf_env.py --env drill|prod [--restore-source]. Reads SECRETS_JSON, VARS_JSON,
GITHUB_REPOSITORY_OWNER, GITHUB_RUN_ID and GITHUB_ENV from the environment.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

ENVS = ("drill", "prod")


@dataclass(frozen=True)
class Entry:
    var: str
    source: str
    name: str = ""
    default: str = ""
    only_env: str = ""
    restore_only: bool = False


# Order follows the old `env:` blocks. `var` is the Terraform variable name;
# tests/architecture/test_ci_terraform_inputs.py checks that every required
# root variable has an entry.
ENTRIES: tuple[Entry, ...] = (
    Entry("env", "env"),
    Entry("scaleway_project_id", "secret", "SCW_DEFAULT_PROJECT_ID"),
    Entry("scaleway_organization_id", "secret", "SCW_DEFAULT_ORG_ID"),
    Entry("admin_email", "secret", "ADMIN_EMAIL"),
    Entry("domain", "secret", "APP_DOMAIN"),
    Entry("github_owner", "owner"),
    Entry("operator_ssh_pubkey", "secret", "OPERATOR_SSH_PUBKEY"),
    # T-D137: public CI key, drill only (main.tf drops it on any other env too).
    Entry("ci_ssh_pubkey", "var", "CI_SSH_PUBKEY", only_env="drill"),
    Entry("ghcr_pull_pat", "secret", "GHCR_PULL_PAT"),
    Entry("litestream_age_identity", "secret", "LITESTREAM_AGE_IDENTITY"),
    Entry("litestream_age_recipient", "secret", "LITESTREAM_AGE_RECIPIENT"),
    # Optional inputs; fall back to the variables.tf defaults when unset.
    # T-D159 / ADR-0093 amendment: a variable, not a secret. A secret `true` makes
    # GitHub mask every `true` in the logs and drop job outputs equal to it.
    Entry("managed_dns_zone", "var", "MANAGED_DNS_ZONE", default="false"),
    Entry("bucket_admin_principals", "secret", "BUCKET_ADMIN_PRINCIPALS", default="[]"),
    Entry("bucket_readonly_principals", "secret", "BUCKET_READONLY_PRINCIPALS", default="[]"),
    # ADR-0105: ci-plan may read the bucket configuration.
    Entry("bucket_plan_principals", "secret", "BUCKET_PLAN_PRINCIPALS", default="[]"),
    # T-D97 / ADR-0101: tailnet MagicDNS suffix (environment variable); drill only.
    Entry("tailnet_dns_name", "var", "TAILNET_DNS_NAME", only_env="drill"),
    # T-D139 / ADR-0116: unique tailnet name (and TLS certificate name) per drill run.
    Entry("drill_run_id", "run_id", only_env="drill"),
    # ADR-0132: prod replica read key, restore drill only (H4-03).
    Entry("scw_access_key_restore", "secret", "PROD_REPLICA_RO_ACCESS_KEY", "", "drill", True),
    Entry("scw_secret_key_restore", "secret", "PROD_REPLICA_RO_SECRET_KEY", "", "drill", True),
    # T-D103 / ADR-0104: IAM identities from terraform/bootstrap/ci (per-env values).
    Entry("app_application_id", "secret", "APP_APPLICATION_ID"),
    Entry("app_scw_access_key", "secret", "APP_SCW_ACCESS_KEY"),
    Entry("app_scw_secret_key", "secret", "APP_SCW_SECRET_KEY"),
    Entry("restore_reader_application_id", "secret", "RESTORE_READER_APPLICATION_ID", "", "prod"),
    # T-D67 / ADR-0094: Tailscale provider (auth key minting).
    Entry("tailscale_oauth_client_id", "secret", "TS_OAUTH_CLIENT_ID"),
    Entry("tailscale_oauth_client_secret", "secret", "TS_OAUTH_SECRET"),
)


class EnvError(ValueError):
    """Raised for an unusable target env or malformed context JSON."""


def build_env(
    target: str,
    secret_values: Mapping[str, str],
    variables: Mapping[str, str],
    *,
    owner: str,
    run_id: str,
    restore_source: bool = False,
) -> dict[str, str]:
    """`TF_VAR_*` name -> value for `target` (pure; no I/O)."""
    if target not in ENVS:
        raise EnvError(f"env must be drill or prod; got '{target}'")
    sources: dict[str, Mapping[str, str]] = {"secret": secret_values, "var": variables}
    fixed = {"env": target, "owner": owner, "run_id": run_id}
    out: dict[str, str] = {}
    for entry in ENTRIES:
        if (entry.only_env and entry.only_env != target) or (
            entry.restore_only and not restore_source
        ):
            value = ""
        elif entry.source in fixed:
            value = fixed[entry.source]
        else:
            value = sources[entry.source].get(entry.name, "") or entry.default
        out[f"TF_VAR_{entry.var}"] = value
    return out


def format_github_env(values: Mapping[str, str]) -> str:
    """`$GITHUB_ENV` file text; multi-line values use a random heredoc delimiter."""
    lines: list[str] = []
    for name, value in values.items():
        if "\n" not in value and "\r" not in value:
            lines.append(f"{name}={value}")
            continue
        delimiter = f"ghadelim_{secrets.token_hex(16)}"
        while delimiter in value:  # pragma: no cover - 128-bit collision
            delimiter = f"ghadelim_{secrets.token_hex(16)}"
        lines.extend([f"{name}<<{delimiter}", value, delimiter])
    return "\n".join(lines) + "\n"


def _parse(label: str, raw: str) -> dict[str, str]:
    try:
        loaded = json.loads(raw or "{}")
    except ValueError as exc:
        raise EnvError(f"{label} is not valid JSON") from exc
    if not isinstance(loaded, dict):
        raise EnvError(f"{label} must be a JSON object")
    return {str(k): str(v) for k, v in loaded.items() if v is not None}


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    environ = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", required=True, choices=ENVS)
    parser.add_argument(
        "--restore-source",
        action="store_true",
        help="emit the prod replica read key (restore drill apply only, ADR-0132)",
    )
    args = parser.parse_args(argv)
    try:
        values = build_env(
            args.env,
            _parse("SECRETS_JSON", environ.get("SECRETS_JSON", "")),
            _parse("VARS_JSON", environ.get("VARS_JSON", "")),
            owner=environ.get("GITHUB_REPOSITORY_OWNER", ""),
            run_id=environ.get("GITHUB_RUN_ID", ""),
            restore_source=args.restore_source,
        )
        target = environ.get("GITHUB_ENV", "")
        if not target:
            raise EnvError("GITHUB_ENV is not set")
    except EnvError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    with Path(target).open("a", encoding="utf-8") as handle:
        handle.write(format_github_env(values))
    print(f"exported {len(values)} TF_VAR_* inputs for {args.env}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
