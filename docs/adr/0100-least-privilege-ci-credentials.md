# ADR-0100: Least-Privilege CI Credentials per Environment, Separate Drill State Bucket, Key-Expiry Monitor

- **Status**: Accepted
- **Date**: 2026-11-07
- **Amends**: [ADR-0096](0096-terraform-state-bootstrap-stack.md) (adds the drill state bucket and a second bootstrap root)
- **Related**: ADR-0099 (prod releases only via GitHub Actions from main), [ADR-0091](0091-bucket-policy-allow-list-per-env-isolation.md), [ADR-0092](0092-drill-in-separate-scaleway-project.md), [ADR-0093](0093-ci-terraform-inputs-via-tf-var-environment-secrets.md), [ADR-0098](0098-keep-rendered-user-data-secrets-out-of-plan-output.md), T-D92

## Context

1. CI and the laptop shared one org-admin Scaleway key (`SCW_ACCESS_KEY`/`SCW_SECRET_KEY`). It leaked in plan output earlier and must be rotated.
2. ADR-0099 makes "prod changes only through GitHub Actions on main" a property of credentials, not of discipline: the only prod-write credential must live in the GitHub `prod` environment, and the laptop must hold none.
3. The drill and prod environments share one state bucket and one key, so a drill workflow (runnable from PR branches) can read and write prod state and prod resources.

## Decision

### 1. Three CI IAM applications (bootstrap/ci stack)

| Application | GitHub environment | Permission sets and scope |
|---|---|---|
| `budget-planner-ci-prod` | `prod` | prod project: `InstancesFullAccess`, `ObjectStorageFullAccess`, `DomainsDNSFullAccess`; organization: `IAMManager` |
| `budget-planner-ci-drill` | `drill` | drill project: `InstancesFullAccess`, `ObjectStorageFullAccess`; prod project: `DomainsDNSFullAccess` (drill DNS records live in the prod project's zone); organization: `IAMManager` |
| `budget-planner-ci-plan` | `prod-plan` | prod project: `InstancesReadOnly`, `ObjectStorageReadOnly`, `DomainsDNSReadOnly`; organization: `IAMReadOnly` |

Why these sets: the env stacks create instances, IPs and security groups (Instances), the durability bucket (Object Storage), DNS records (Domains/DNS), and IAM applications, API keys and policies (IAM). `ProjectManager`, `AllProductsFullAccess`, `OrganizationManager` and billing sets are deliberately not granted.

Each key sets `default_project_id` (S3 calls resolve buckets against the key's default project, ADR-0092) and an `expires_at` of 1 year (`ci_key_ttl_hours`, default 8760), with `ignore_changes = [expires_at]` as in T-D74.

`prod-plan` exists because ADR-0093 made PR plans read an ungated environment that any PR branch can reach. It must not hold a write key.

### 2. Residual privilege (stated honestly)

- **`IAMManager` is effectively high privilege.** Scaleway offers IAM management only at organization scope. A holder can create an application with `AllProductsFullAccess`, mint a key for it and use it. So `ci-drill` can in principle reach prod, and `ci-prod` can reach anything. Isolation between drill and prod is therefore enforced by the state-bucket policies, GitHub environment gating and key expiry, not by a hard IAM boundary.
- Mitigations: the keys exist only as environment secrets; `prod` requires a reviewer and deploys only from `main` (runbooks/github-settings.md); keys expire yearly and are monitored; plans use a read-only key; the IAM audit trail lists every application and policy creation (review during rotation).
- `DomainsDNSFullAccess` cannot be scoped to one zone: it covers all DNS in the prod project.
- Closing the gap later: a pre-created application per env with a fixed policy and an env stack that no longer manages IAM (the IAM resources would move into bootstrap/ci). Out of scope for v1; revisit if Scaleway adds project-scoped IAM management.

### 3. Separate drill state bucket

`budget-planner-tfstate-drill-pl-waw` is created in the **drill project** by the bootstrap stack (`terraform/bootstrap/drill_bucket.tf`): versioned, private ACL, 90-day noncurrent expiry, `prevent_destroy`. `terraform/envs/drill/backend.hcl` points at it. Drill state is empty (drill was destroyed), so no migration is needed; run `terraform init -reconfigure`.

Bucket policies (allow-list, ADR-0091 semantics; attached by bootstrap/ci because they need the application ids):
- drill bucket: `ci-drill` read/write + `state_admin_principals` (`s3:*`). Always applied (new, empty bucket).
- prod bucket: `ci-prod` read/write, `ci-plan` read plus put/delete on `prod/terraform.tfstate.tflock` only, `state_admin_principals`. Behind `restrict_prod_state_bucket` (default false) because the bucket already holds the only copy of prod state and a wrong allow-list locks the owner out; enable after the CI keys are verified.
- `state_admin_principals` (required, validated non-empty) keeps the break-glass admin able to reach both buckets.
- Unverified: whether a read-only IAM key can write the lock object through a bucket-policy grant alone. If the first prod-plan fails to lock, run the plan with `-lock=false` for that job (plan is read-only) rather than widening the key.

### 4. Second bootstrap root, not committed

The CI keys' secrets land in Terraform state. ADR-0096 commits the bootstrap state because it holds no secrets, so the identities live in **`terraform/bootstrap/ci/`** with local state that is **not committed** (`terraform/.gitignore` already ignores `*.tfstate`; only `bootstrap/terraform.tfstate` is un-ignored). Keep the ci state file in the operator's password manager or an encrypted backup; if lost, re-create the keys by tainting them (the applications and policies can be imported).

### 5. Key expiry and rotation cadence

- CI keys: 1 year, rotated every 11 months or on the expiry alert, whichever first. Org-admin break-glass key: rotated yearly and after every use.
- `.github/workflows/key-expiry.yml` runs weekly (and on demand) with the read-only `ci-plan` key, lists all organization API keys that have an expiry (CI keys and the Litestream app keys) and fails plus opens/updates one issue when any has fewer than 30 days left. It performs no writes in Scaleway.

### 6. Break-glass

The org-admin key lives only in the operator's password manager, never in `terraform/.env` or GitHub. Allowed only for: GitHub outage, a stuck state lock, broken CI credentials, or applying bootstrap stacks. Procedure and the record-keeping duty (CHANGELOG entry, rotate after use) are in `runbooks/break-glass.md`.

### 7. Remains manual

GitHub settings (environments, required reviewers, deployment branch rules, branch protection, secrets) per `runbooks/github-settings.md`; separate Tailscale OAuth clients per environment (Tailscale admin console has no Terraform path in this repo); the one-time local applies of both bootstrap roots after plan review (ADR-0096 exception).

## Alternatives considered

- **Keep one org-admin key, rotate it (rejected).** Does not satisfy ADR-0099 and keeps drill/prod and PR/prod coupled.
- **Per-env keys but a single state bucket (rejected).** A drill credential would still read prod state, which contains secrets.
- **Put the CI applications in the committed bootstrap state (rejected).** API secret keys would be committed.
- **Pre-created IAM and no IAMManager for CI (deferred).** Cleaner boundary but requires restructuring the env stacks (`terraform/modules/iam`), which is outside this item.

## Consequences

- After rotation the laptop has no prod-write key; prod applies happen in the `prod` environment only (ADR-0099).
- Workflows keep the same secret names (`SCW_ACCESS_KEY`, `SCW_SECRET_KEY`) but with environment-scoped, different values. Repo-level copies of these secrets must be deleted so a missing environment secret fails loudly instead of falling back to a stronger key.
- `terraform/bootstrap/ci` is not covered by the existing `terraform.yml` validate step (it validates `terraform/bootstrap` only). Follow-up: add a validate line for it.
