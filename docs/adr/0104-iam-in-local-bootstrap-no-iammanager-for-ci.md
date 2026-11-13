# ADR-0104: Env-Stack IAM Moves to the Local Bootstrap; CI Loses IAMManager

- **Status**: Accepted
- **Date**: 2026-11-13
- **Relates to**: ADR-0035, ADR-0091, ADR-0092, ADR-0096, ADR-0098, ADR-0099, ADR-0101, T-D103
- **Amends**: ADR-0100 section 1 (CI permission sets) and section 2 (residual privilege); takes up the "Pre-created IAM and no IAMManager for CI" alternative that ADR-0100 deferred. Nothing is superseded.

## Context

The env stacks (`terraform/`, one state per env) create IAM resources: the app identity used by Litestream (`module.iam`: application, `ObjectStorageFullAccess` policy on the env project, API key) for prod and drill, and the prod `restore-reader` identity (`module.restore_reader`). For CI to apply them, `ci-prod` and `ci-drill` hold **organization-scoped `IAMManager`** (Scaleway offers IAM management only at that scope). ADR-0100 section 2 states the consequence: a holder can create an application with `AllProductsFullAccess`, mint a key for it and use it. A leaked CI key or a compromised workflow is effectively full organization takeover.

## Decision

### 1. IAM lives in `terraform/bootstrap/ci`

- `terraform/modules/iam` moves to `terraform/bootstrap/ci/modules/app_iam` (code unchanged) and is instantiated twice: `module.app_prod` (prod project) and `module.app_drill` (drill project). `terraform/modules/restore_reader` moves to `terraform/bootstrap/ci/modules/restore_reader` (code unchanged), `module.restore_reader` (prod project).
- `bootstrap/ci` is applied locally with the break-glass key (ADR-0100 section 4, ADR-0099 exception (c)). Its state stays local and uncommitted, because it holds API secret keys.
- The drill app identity becomes long-lived. It used to be re-created on every drill apply; now the drill bucket policy names a stable principal.

### 2. Env stacks take the identities as inputs

- New root variables: `app_application_id` (required), `app_scw_access_key` and `app_scw_secret_key` (required, sensitive), `restore_reader_application_id` (required on prod, must be empty on drill).
- `module.storage` uses `var.app_application_id` as the env principal. The prod bucket's read-only principals add `application_id:<restore_reader_application_id>`. `module.compute` renders `var.app_scw_*` into cloud-init, exactly where `module.iam`'s outputs went.
- CI passes them from GitHub environment secrets `APP_APPLICATION_ID`, `APP_SCW_ACCESS_KEY`, `APP_SCW_SECRET_KEY`, `RESTORE_READER_APPLICATION_ID` (prod and prod-plan only). The drill environments get the drill identity's values.
- Root outputs `scw_access_key`, `scw_secret_key`, `scw_app_key_expires_at` and `restore_reader_*` move to `bootstrap/ci`.

### 3. Migration with zero downtime

- **Prod keeps its current keys.** cloud-init runs once (ADR-0098), so a new key would never reach the running VM without a server replace. The operator imports the existing prod app and restore-reader resources (application, policy, API key) into `bootstrap/ci` with `terraform import`. bootstrap/ci config matches their current attributes, so the import plans no changes.
- **An imported API key carries no secret** (Scaleway returns it only at creation). The operator reads the current secrets from the prod state once (`terraform output -raw scw_secret_key`, `restore_reader_secret_key`) before the first release, and stores them as GitHub environment secrets. The rendered user-data is then byte-identical and the server plans no change.
- The env stack declares `removed { from = module.iam; lifecycle { destroy = false } }` and the same for `module.restore_reader`. The first CI release (ADR-0099) drops them from prod state without deleting anything. Drill state holds no IAM (the drill is destroyed), so the blocks are no-ops there.
- Drill has nothing to import: `module.app_drill` is created fresh.

### 4. CI permissions after the change

| Application | Before | After |
|---|---|---|
| `ci-prod` | prod project: Instances/ObjectStorage/DNS full; org: `IAMManager` | prod project: unchanged; org: `IAMReadOnly` **only while `ci_prod_iam_transition = true`** |
| `ci-drill` | drill project: Instances/ObjectStorage full; org: `IAMManager` | drill project: unchanged; no IAM |
| `ci-plan` | read-only prod project; org: `IAMReadOnly` | unchanged |

- **Transition.** Until the release that applies the `removed` blocks, prod state still contains IAM resources and every plan refreshes them. Refreshing reads IAM, so `ci-prod` keeps `IAMReadOnly` for that one release. After it, the operator sets `ci_prod_iam_transition = false` and re-applies `bootstrap/ci`.
- **`ci-plan` keeps `IAMReadOnly`.** `key-expiry.yml` lists the organization's API keys with it (ADR-0100 section 5). Read-only IAM cannot create applications, keys or policies; it exposes names, ids and expiry dates, not secrets.

### 5. Key rotation

- **Litestream app key.** `terraform apply -replace=module.app_<env>.scaleway_iam_api_key.app` in `bootstrap/ci` (laptop, break-glass key), then update `APP_SCW_*` in the matching GitHub environments, then refresh the host secret by hand (unchanged from `runbooks/deploy.md`). The first prod rotation also makes the bootstrap state hold the prod secret.
- **Restore-reader key.** Same pattern in `bootstrap/ci`; update `PROD_REPLICA_RO_*`.

## Consequences

- No CI credential can create IAM applications, keys or policies once the transition ends. A CI key leak is bounded by its project permission sets.
- Key rotation for app and restore-reader keys is a laptop step, no longer a pipeline step. It already needed break-glass handling (`runbooks/deploy.md`), so the operator workload barely changes.
- More secrets to maintain by hand in GitHub environments (four per environment).
- `prod-plan` gets `APP_SCW_SECRET_KEY` for prod, a write credential on the prod bucket. This adds no new exposure: `ci-plan` can already read the prod state, which contains the same key inside `cloud_init`. Plans need it so user-data renders identically.
- During the transition, two states manage the same IAM objects for one release (prod state and bootstrap/ci). Neither changes them, so there is no conflict.

## Alternatives considered

- **Keep IAMManager** (ADR-0100 status quo). Simplest; leaves organization takeover one leaked key away.
- **Rotate to fresh keys instead of importing.** Avoids reading secrets from prod state, but the running VM keeps the old key until a break-glass server replace.
- **Import blocks committed to the repo.** Declarative, but the import ids would live in a public repository, and the import is a one-time laptop step anyway.
