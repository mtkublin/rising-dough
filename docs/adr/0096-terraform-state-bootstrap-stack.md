# ADR-0096: Terraform State Bucket Bootstrapped by a Separate Terraform Root Stack

- **Status**: Accepted
- **Date**: 2026-11-06
- **Amends**: [ADR-0035](0035-v3-infrastructure-as-code-terraform.md) §4 (bootstrap script replaced)
- **Related**: [ADR-0091](0091-bucket-policy-allow-list-per-env-isolation.md), [ADR-0093](0093-ci-terraform-inputs-via-tf-var-environment-secrets.md), T-D20, T-D72

## Context

1. The state bucket `budget-planner-tfstate-pl-waw` (`pl-waw`) cannot live in the main stack, which stores its state in it.
2. ADR-0035 §4 created it with a one-shot script (`terraform/scripts/bootstrap-state.sh`, `aws s3api`). Problems: the project is otherwise all Terraform; `plan` cannot show drift on the bucket; the script calls `put-public-access-block`, which Scaleway Object Storage may not support (buckets are private by default); newer aws CLI versions send default checksums that Scaleway rejects.
3. Operator decision (2026-11-06): use a declarative bootstrap stack.

## Decision

1. **Separate root stack `terraform/bootstrap/`** with its own `versions.tf` (same Terraform and scaleway provider pins as the main stack), `providers.tf`, `variables.tf`, `main.tf`, `outputs.tf`. Inputs: `scaleway_project_id`, `scaleway_organization_id` (no hardcoded IDs), `bucket_name` (default `budget-planner-tfstate-pl-waw`), `region` (default `pl-waw`).
2. **Bucket**: `scaleway_object_bucket` with `versioning.enabled = true`, `force_destroy = false`, `lifecycle { prevent_destroy = true }`; `scaleway_object_bucket_acl` = `private`. No public-access-block call.
3. **Noncurrent-version expiry**: a lifecycle rule expires noncurrent state versions after 90 days (and aborts incomplete multipart uploads after 7). Older state history is not needed for rollback.
4. **No bucket policy (deferred).** A wrong Scaleway policy locks out the owner (see ADR-0091: allow-list semantics, Deny ignored). Access is limited by the private ACL and the credentials. A policy can be added later with its own ADR.
5. **Local state, committed.** The bootstrap stack uses the default local backend. Its `terraform.tfstate` holds only bucket metadata (no secrets) and is committed to git after the operator's first apply; `terraform/.gitignore` has one scoped negation (`!bootstrap/terraform.tfstate`).
6. **Applied once**; re-run `terraform plan` to check drift. Operator steps in `terraform/bootstrap/README.md` and `docs/plans/v3/operator-checklist.md` A7. CI only runs fmt, validate (`init -backend=false`) and tflint on it; it never plans or applies it.
7. `terraform/scripts/bootstrap-state.sh` is deleted.

## Alternatives considered

- **Keep the shell script (rejected).** No drift visibility, imperative, uses an API Scaleway may not support, and breaks with newer aws CLI checksum defaults.
- **Put the bucket in the main stack (rejected).** Chicken-and-egg: the backend must exist before `init`.
- **Remote state for the bootstrap stack (rejected).** Same chicken-and-egg; local state without secrets is small and safe to commit.

## Consequences

- The operator applies the stack once (a manual step, `plan` before `apply`), then commits `terraform/bootstrap/terraform.tfstate`.
- If the bucket already exists from the old script, `terraform import scaleway_object_bucket.tfstate pl-waw/budget-planner-tfstate-pl-waw` before the first apply.
- `prevent_destroy` means removing the bucket requires editing the code deliberately.
