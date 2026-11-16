# ADR-0105: CI Identities in the Durability Bucket Policies

- **Status**: Accepted
- **Date**: 2026-11-16
- **Relates to**: ADR-0091, ADR-0099, ADR-0100, ADR-0104, T-D117
- **Amends**: ADR-0091 (statement set of the per-env bucket policy), ADR-0100 (bucket access of the CI identities). Nothing is superseded.

## Context

ADR-0091 attaches an allow-list policy to each env's durability bucket: anything not explicitly allowed is denied, whatever the caller's project-level IAM permissions. The policy allows the env's app identity, `bucket_admin_principals` (the operator's `user_id`) and `bucket_readonly_principals` (prod: the restore-reader). ADR-0100 then moved Terraform runs to per-env CI identities (`ci-prod`, `ci-drill`, `ci-plan`) but did not add them to these policies.

The first PR plan with the CI keys (2026-11-16) failed: `ci-plan` got `403 AccessDenied` on `GetBucketCors` while refreshing `module.storage.scaleway_object_bucket.durability`. The same applies to `ci-prod` (the release apply) and `ci-drill` (it can create the drill bucket, but once the policy is attached it can no longer refresh or destroy it, so a drill teardown would fail and leave the VM behind).

## Decision

### 1. Apply identities are bucket admins

`ci-prod` and `ci-drill` manage the bucket (versioning, lifecycle, ACL, policy), so they need the existing admin statement (`s3:*`). Their ids go into `BUCKET_ADMIN_PRINCIPALS` of their own environments, next to the operator: prod and prod-plan get `application_id:<ci-prod>`; the three drill environments get `application_id:<ci-drill>`. No code change; prod and prod-plan hold the same value so PR plans render the same policy as the release.

### 2. The plan identity reads bucket configuration only

New input `bucket_plan_principals` (root) → `plan_principals` (storage, bucket_policy) → statement `AllowTerraformPlanRead` with the reads a refresh of the bucket and its ACL performs: `s3:ListBucket`, `s3:GetBucketLocation`, `s3:GetBucketCORS`, `s3:GetBucketVersioning`, `s3:GetLifecycleConfiguration`, `s3:GetBucketTagging`, `s3:GetBucketAcl`, `s3:GetBucketObjectLockConfiguration`, `s3:GetEncryptionConfiguration`. No object reads (`GetObject`), no writes, no deletes. Prod and prod-plan set `BUCKET_PLAN_PRINCIPALS = ["application_id:<ci-plan>"]`; drill leaves it empty (`drill-plan` uses the `ci-drill` key, already an admin).

Only actions on Scaleway's supported bucket-policy list are allowed; anything else makes `PutBucketPolicy` fail with `400 MalformedPolicy` (first attempt included `s3:GetBucketPolicy`, which is not on the list). Reading the policy itself is therefore not grantable through the bucket policy; if `ci-plan` cannot refresh `scaleway_object_bucket_policy`, that is solved outside this statement. The list is derived from what the provider reads, not verified against a live refresh; if a plan hits another 403 on a supported action, it is added here.

### 3. One-time break-glass to break the deadlock (prod)

`ci-prod` cannot refresh the prod bucket until the policy lists it, and only an apply can change the policy. The operator therefore applies the new prod bucket policy once from the laptop with the break-glass key, targeted at `module.storage.scaleway_object_bucket_policy.durability` (`runbooks/break-glass.md`, reason "CI credentials broken"), logged in `docs/CHANGELOG.md`. The drill has no deadlock: its bucket is created by `ci-drill` with a policy that already lists it.

## Consequences

- PR plans, releases and drill teardowns can read the buckets; per-env isolation (ADR-0091) is unchanged: no identity of one env appears in the other env's policy.
- `ci-prod` and `ci-drill` can read and delete their env's backups. They could already rewrite the policy through `ObjectStorageFullAccess` plus Terraform, so this states an existing capability rather than adding one.
- `ci-plan`, reachable from PR branches, gets no access to backup data through the bucket policy.

## Alternatives considered

- **`ci-plan` as bucket admin.** No code change, but a PR-reachable key would get `s3:*` on prod backups, including `DeleteObjectVersion`.
- **Drop the bucket policies.** Removes the problem class but undoes ADR-0091's per-env isolation.
