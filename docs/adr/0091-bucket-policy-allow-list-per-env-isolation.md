# ADR-0091: Bucket Policy Is an Explicit Allow-List; It Provides Per-Env Isolation

- **Status**: Accepted
- **Date**: 2026-11-06
- **Amends**: [ADR-0035](0035-v3-infrastructure-as-code-terraform.md) §3 (storage hardening), [ADR-0032](0032-v3-hosting-scaleway-poland.md) §3
- **Related**: [ADR-0034](0034-v3-backups-litestream-to-object-storage.md) §5 (restore drill), [ADR-0088](0088-dns-zone-not-owned-by-env-state.md), T-D21 (storage module), T-D26 / T-D41 (drill teardown, monthly restore drill), T-D68 (this change)

## Context

1. `modules/storage` attached a bucket policy with `Version = "2023-04-17"` and one `Deny` statement (`DenyUnencryptedTransport`, `aws:SecureTransport = false`). Scaleway docs (bucket-policy page): with version `2023-04-17` "only actions explicitly allowed by the bucket policy are permitted, if the principal is also allowed by an IAM policy. Deny statements are therefore useless." and "You will lose access to your bucket if you are not the owner of the Organization, and if you are not explicitly allowed by the bucket policy." The combining-IAM page adds that once a bucket policy restricts principals, every other principal that needs access must be granted explicitly in the policy.
   Effect: the env's IAM application (Litestream) was locked out of its own bucket (403, no backups), and the TLS-only Deny did nothing.
2. Drill and prod share one Scaleway project. Each env's IAM application holds `ObjectStorageFullAccess` for the whole project (`modules/iam`), so a drill VM key could read, overwrite or delete prod backups.
3. `force_destroy = false` blocks `terraform destroy` of drill (T-D26, monthly T-D41) as soon as the bucket holds Litestream objects.

## Decision

1. **Allow-list, no Deny.** The policy is `2023-04-17` with only `Allow` statements. The TLS-only Deny is removed (S3 endpoints are HTTPS; the Deny was inert). Policy JSON is built in a provider-free module `modules/bucket_policy` so it can be tested without cloud access.
2. **Per-env isolation via the bucket policy** (operator chose this over separate Scaleway projects). Because the policy is allow-only, any principal not listed is denied even though its IAM policy is project-wide. Statements per bucket:
   - `AllowEnvApplication`: the env's own IAM application (`application_id:<module.iam.application_id>`) gets the minimal Litestream 0.3.14 set: `s3:ListBucket`, `s3:GetBucketLocation`, `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:AbortMultipartUpload`, `s3:ListBucketMultipartUploads`, `s3:ListMultipartUploadParts` on the bucket and `bucket/*`. Versioned-object actions are not granted (Litestream does not request version ids; lifecycle expiry of noncurrent versions is server-side).
   - `AllowOperators` (only if `bucket_admin_principals` is non-empty): `s3:*` for the operator's user and/or application. Needed because Terraform itself (refresh, `force_destroy` on drill) and manual inspection act as the operator, and the Organization owner is the only principal that bypasses the policy.
   - `AllowReadOnly` (only if `bucket_readonly_principals` is non-empty): `s3:ListBucket`, `s3:GetBucketLocation`, `s3:GetObject`, `s3:GetObjectVersion`, `s3:ListBucketVersions`. Meant for the prod bucket only.
3. **Cross-env wiring is by input variable, not resource reference.** Drill and prod are separate states, so prod cannot reference the drill's or the restore key's IAM application. The read-only restore key (ADR-0034 §5, T-D41a: `scw_access_key_restore`) belongs to an operator-created IAM application. Its id goes into prod's `bucket_readonly_principals` as `application_id:<id>`. The same application must also have an IAM policy allowing object-storage read in the project (the bucket policy narrows, it does not grant IAM permissions). Drill leaves the list empty and so allows only its own application. The drill VM key therefore cannot touch the prod bucket, and prod's write key cannot touch the drill bucket.
4. **Lockout guard.** `env_application_id` is required and validated as a UUID. Principal strings are validated against `(user|application)_id:<uuid>`. Recovery from a mistaken policy: the Organization owner re-puts the policy (console or `terraform apply` as owner).
5. **`force_destroy` is a module variable.** Root sets `force_destroy = (var.env == "drill")`. Prod stays `false`, so `terraform destroy` on prod fails while the bucket is non-empty. Drill teardown then needs the operator in `bucket_admin_principals` (or Organization owner credentials) so Terraform may delete the objects and versions.

## Consequences

- First apply on an env creates the IAM application, then the bucket and policy in one run; no ordering problem since the application id is a resource attribute.
- If `bucket_admin_principals` is empty and Terraform runs as a non-owner, later plans and `destroy` can fail with 403. Operator checklist now asks for it before T-D25.
- Rotating the restore key to a new IAM application requires updating `bucket_readonly_principals` in prod and applying.
- Residual risk: project-wide IAM stays broad; isolation relies on the bucket policy. Separate Scaleway projects remain the stronger option if ever needed (would supersede this ADR).
- Not verified against a live bucket. The first drill apply (T-D25) must confirm Litestream writes succeed and that `s3:GetBucketLocation`/multipart actions are sufficient. If Scaleway rejects an action name, check the S3 IAM permissions equivalence page.
