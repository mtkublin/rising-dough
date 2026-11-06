# ADR-0092: Drill Runs in Its Own Scaleway Project; Stable Restore-Reader Principal

- **Status**: Accepted
- **Date**: 2026-11-06
- **Supersedes**: the "drill and prod share one project" assumption in [ADR-0091](0091-bucket-policy-allow-list-per-env-isolation.md) context 2 (the allow-list stays as defence in depth)
- **Related**: [ADR-0035](0035-v3-infrastructure-as-code-terraform.md) §3, [ADR-0088](0088-dns-zone-not-owned-by-env-state.md), [ADR-0034](0034-v3-backups-litestream-to-object-storage.md) §5, T-D69

## Context

1. ADR-0091 isolated drill from prod with the bucket policy only, because both envs sat in project `rising-dough` and each env's IAM application held project-wide `ObjectStorageFullAccess`.
2. The operator created project `rising-dough-drill` (`f2facf0d-f2c9-40cc-8bcb-5b212dc44648`, 2026-11-06). IAM policies scoped to a project are the stronger boundary.
3. The DNS zone (`rising-dough.eu`, Scaleway Domains) belongs to the prod project. Provider docs for `scaleway_domain_record` (and its data source) list `project_id` ("Defaults to the Project ID specified in the provider configuration"; the ID of the Project associated with the domain). Without it, drill records would be looked up and created in the drill project, where the zone does not exist.
4. The drill IAM application is re-created on every monthly drill (new id), so it cannot be listed in prod's bucket policy or granted anything in prod by id.

## Decision

1. **One project per env.** `scaleway_project_id` is already a per-env tfvar and feeds the provider block (instance, IPs, security group, bucket) and `modules/iam` (policy `project_ids`). Drill uses the drill project, prod uses `rising-dough`. No resource sets its own `project_id`, so all honour the provider value.
2. **DNS in the zone's project.** New variable `dns_zone_project_id` (default: prod project `53175dd0-b944-489b-b05d-3f55d65d79af`, set explicitly in both tfvars examples) is passed to `modules/dns` and set as `project_id` on both `scaleway_domain_record` resources. Zone is still referenced by name and never owned (ADR-0088). Operator is Organization owner, so Terraform may write into both projects.
3. **Stable `restore-reader` principal in the PROD state** (`modules/restore_reader`, `count = env == "prod" ? 1 : 0`): `scaleway_iam_application`, a `scaleway_iam_policy` with `ObjectStorageReadOnly` on the prod project only, and a `scaleway_iam_api_key`. Sensitive prod outputs `restore_reader_access_key` / `restore_reader_secret_key`. Root merges `application_id:<restore-reader>` into the prod bucket policy `AllowReadOnly` statement together with `bucket_readonly_principals` (now optional extras). Drill gets none of this.
4. **Credential path.** Existing names kept: the operator copies the two outputs into GitHub `drill`-environment secrets `PROD_REPLICA_RO_ACCESS_KEY` / `PROD_REPLICA_RO_SECRET_KEY`; `restore-drill.yml` already maps them to `TF_VAR_scw_access_key_restore` / `_secret_key_restore`, rendered into `restore-source.env` by cloud-init (T-D41a). The `drill` environment secret `SCW_DEFAULT_PROJECT_ID` is the drill project and now also feeds `TF_VAR_scaleway_project_id`. `terraform.yml` plan matrix uses repo secret `SCW_DRILL_PROJECT_ID` for the drill leg. <!-- pragma: allowlist secret -->
5. **Ordering.** Prod must be applied before the first automated restore drill (the restore-reader key and the prod bucket policy come from it). The T-D25 manual drill apply does not need the key (restore helper aborts on empty creds).

## Consequences

- A leaked drill VM key (or its IAM app) has no rights in the prod project; it cannot read or delete prod backups even if the bucket policy were wrong.
- The restore-reader key is long-lived and read-only; rotate with `terraform apply -replace='module.restore_reader[0].scaleway_iam_api_key.restore_reader'` on prod, then update the two GitHub secrets.
- Bucket-policy `bucket_admin_principals` remains needed for operators that are not Organization owner.
- The state bucket stays in the prod project (outside Terraform).
