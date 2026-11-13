# ADR-0090: Terraform >= 1.10 Minimum and CI Pin to 1.17.1

- **Status**: Accepted
- **Date**: 2026-11-06
- **Amends**: [ADR-0035](0035-v3-infrastructure-as-code-terraform.md) (Terraform version floor and CI pin)
- **Related**: T-D20 (state bootstrap, `use_lockfile`), T-D64 (this change)

## Context

1. `terraform/envs/*/backend.hcl` sets `use_lockfile = true` for the S3 backend. Native S3 state locking requires Terraform **1.10+**. On 1.9 there is no state lock, which is why `terraform/README.md` ran a one-writer invariant mode.
2. `terraform/versions.tf` still declares `required_version = ">= 1.9.0"`, so a 1.9 binary passes the constraint and then runs without locking.
3. CI pinned `1.9.4` (`terraform.yml`, three jobs) and `1.9.8` (`restore-drill.yml`). The operator's local Terraform is 1.17.1. CI and local runs therefore differ in version and in lock behaviour.

## Decision

- **Floor**: `terraform/versions.tf` declares `required_version = ">= 1.10.0"`. Any Terraform below 1.10 fails `init` instead of silently running without state locking.
- **CI pin**: every `terraform_version` in `.github/workflows/*.yml` is `1.17.1`. The same version is recorded in `terraform/.terraform-version`.
- **One version everywhere.** Operator, CI, and the version file use the same release. Bumping Terraform means changing these in one PR.

## Consequences

- Operators on 1.9 must upgrade before running `init` against the remote backend.
- The "one-writer invariant mode" note in `terraform/README.md` no longer applies and is removed.
- Historical ADRs and task records that mention 1.9 are left as written. They describe the state at their own date.

## Amendment 2026-11-06 (T-D79): module floors aligned

- Every `terraform/modules/*/versions.tf` and `terraform/bootstrap/versions.tf` now declares `required_version = ">= 1.10.0"`, the same floor as the root. Guarded by `tests/unit/deploy/test_tf_versions.py`.
