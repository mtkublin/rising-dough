# ADR-0117: One Source for Shared GitHub Workflow Logic

- **Status**: Accepted
- **Date**: 2026-11-18
- **Relates to**: ADR-0099 (release and environment policy), ADR-0100, ADR-0101, ADR-0111, ADR-0112, ADR-0115, ADR-0116
- **Task**: T-D133

## Context

The same logic had grown in several workflows and drifted:

- `terraform.yml` repeated ~25 `TF_VAR_*` mappings in `plan` and `apply`; `restore-drill.yml` carried a third copy plus its own Terraform init/apply/destroy.
- The tailnet cleanup job existed three times (`drill.yml`, `drill-destroy.yml`, `drill-sweeper.yml`) and a fourth time in `restore-drill.yml`.
- Tag to digest resolution was inline in `rollback.yml` and `restore-drill.yml`.
- Action pins differed per file (`setup-uv` floating `@v3`, a mislabelled SHA, v4.1.0; two `setup-buildx-action` SHAs; unpinned `checkout`, `setup-node`, `setup-just`, `upload-artifact`). Dependabot is off (T-D130).

Workflow-level `env:` cannot read environment secrets, so the `TF_VAR_*` list could not simply move up.

## Decision

1. **TF_VAR mapping**: `scripts/ci/tf_env.py` holds the one list (secret or variable name, default, drill-only or prod-only rule). The composite action `.github/actions/terraform-env` passes `toJSON(secrets)` and `toJSON(vars)` to it, and it appends the `TF_VAR_*` values to `$GITHUB_ENV`. `terraform.yml` calls the action once in `plan` and once in `apply`. Drill-only inputs (`ci_ssh_pubkey` (T-D137), `tailnet_dns_name`, `drill_run_id` (ADR-0116), the restore keys) are empty on prod; the rule is now unit-tested instead of grepped. Credentials (`SCW_*`, `AWS_*`), the apply-only drill knobs and the image refs stay in the job and step `env:` as before.
2. **Restore drill on `terraform.yml`**: `restore-drill.yml` becomes `drill-lock` -> `image` (resolve) -> `apply` (reusable, environment `drill`; reviewers are optional and none are configured today) -> `restore-drill` (tailnet, SSH, restore, verify, evidence; environment `drill`, the only one holding `DEPLOY_SSH_PRIVATE_KEY`) -> `destroy` (reusable, always once apply was attempted) -> `verify-destroy` / `tailnet-cleanup` / `report`. Gates, concurrency group `drill`, the lock-first rule (ADR-0115) and the per-run name (ADR-0116) are unchanged. The unused Scaleway CLI install is dropped.
3. **Tailnet cleanup**: reusable `tailnet-cleanup.yml` (environment `drill-teardown`, `contents: read`); all four drill workflows call it with `secrets: inherit`.
4. **Ref resolution**: `host_release.py resolve-ref --image I --tag T` prints `ref=<tag>@sha256:<digest>`; `rollback.yml` and `restore-drill.yml` use it.
5. **Pins**: one 40-hex SHA per action across `.github/workflows` and `.github/actions`, with a version comment; `tests/unit/deploy/test_action_pins.py` enforces both.

## Consequences

- Adding a Terraform input is one entry in `tf_env.py` (a test fails when a required root variable has none).
- `toJSON(secrets)` is held in one step's environment inside jobs that already hold those secrets; only the listed names are exported.
- The restore drill is now several jobs, so a failure can leave a drill VM if `destroy` is skipped; it runs `always()` once `apply` was attempted, as `drill.yml` does.
- Proof needs one gate drill and one restore drill after merge (T-D133 done-definition).
- Rejected: a composite action with one input per secret (still repeats the list per caller); `secrets: inherit` plus a matrix (does not fix the restore drill).
