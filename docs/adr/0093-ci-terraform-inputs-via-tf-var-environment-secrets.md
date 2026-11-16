# ADR-0093: CI Terraform Inputs via TF_VAR_* from Environment Secrets; No tfvars in Git

- **Status**: Accepted
- **Date**: 2026-11-06
- **Amends**: [ADR-0092](0092-drill-in-separate-scaleway-project.md) §4 (repo secret `SCW_DRILL_PROJECT_ID` replaced), [ADR-0078](0078-v3-data-protection-quick-wins.md) §3 (`LITESTREAM_AGE_RECIPIENT` becomes a secret)
- **Related**: [ADR-0035](0035-v3-infrastructure-as-code-terraform.md), [ADR-0037](0037-v3-github-actions-deploy-pipeline.md), T-D70

## Context

1. `terraform.yml` and `restore-drill.yml` passed `-var-file=envs/<env>/terraform.tfvars`. Those files are gitignored (operator-local), so they do not exist in CI and every plan, apply and monthly drill failed.
2. Operator decision (2026-11-06): commit no tfvars at all, not even non-secret per-env files. Values live in GitHub secrets.
3. A missing secret expands to an empty string; Terraform then fails with an opaque validation error. Unset (not empty) variables would hang on an interactive prompt.
4. The `prod` GitHub environment has required reviewers (ADR-0037). Using it on the PR plan job would gate every plan.

## Decision

1. **No `-var-file` in CI.** Every root variable arrives as `TF_VAR_<name>` in the job `env`. Local operator runs keep the gitignored `terraform/envs/<env>/terraform.tfvars`.
2. **Same secret name per env, scoped by GitHub environment.** Per-env values (`SCW_DEFAULT_PROJECT_ID`, `BUCKET_ADMIN_PRINCIPALS`, `MANAGED_DNS_ZONE`, ...) are environment secrets with identical names in `drill` and `prod`. Values common to both (Scaleway key, org id, SSH keys, age keys) are repo secrets. An environment secret overrides a repo secret of the same name.
3. **Plan job environments.** The plan matrix sets `environment:` to `drill` (ungated) for the drill leg and to a new ungated `prod-plan` environment for the prod leg. `prod-plan` holds the same secret names with prod values, so no gate hits PRs and no differently named secrets are needed. `apply-prod` keeps `environment: prod` (approval). `restore-drill` keeps `environment: drill`.
4. **Secrets, not variables.** `LITESTREAM_AGE_RECIPIENT` (was a variable, T-D56) and the drill project id (was repo secret `SCW_DRILL_PROJECT_ID`, T-D69) move to the scheme above. `APP_DOMAIN` is read as a secret everywhere (including `DRILL_HOST`).
5. **List and bool inputs** are strings parsed by Terraform: `BUCKET_ADMIN_PRINCIPALS` / `BUCKET_READONLY_PRINCIPALS` hold an HCL/JSON list, e.g. `["user_id:00000000-0000-0000-0000-000000000000"]`; `MANAGED_DNS_ZONE` holds `true` or `false`. When unset, workflows fall back to `[]` / `false` (the variable defaults).
6. **Guard.** `terraform/scripts/check_tf_vars.py` parses `terraform/variables.tf`, finds every variable without a `default` and fails with one `::error::` line per empty `TF_VAR_<name>`. It runs before `terraform init` in each terraform job. All terraform commands also use `-input=false` (and `TF_INPUT=0`).
7. **Test.** `tests/architecture/test_ci_terraform_inputs.py` asserts no `-var-file` in workflows, every required variable has a `TF_VAR_` entry in each terraform job, the guard step is present, and terraform runs non-interactively.

## Consequences

- The operator must create the secrets listed in `docs/plans/v3/operator-checklist.md` A5 (including environments `drill`, `prod`, `prod-plan`) before CI can plan or apply.
- Adding a required root variable now fails the architecture test until a `TF_VAR_` entry is added to every terraform job.
- `prod-plan` duplicates prod values; they are not more sensitive than what `prod` already holds. Rotate in both places.
- Secrets are masked in logs, so values such as the domain print as `***` in CI output.
