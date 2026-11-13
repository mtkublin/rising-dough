# Runbook: Scaleway key rotation (ADR-0100)

**Context.** The single org-admin key used by CI and the laptop leaked via plan output. Replace it with: (a) a break-glass org-admin key held only in the password manager, and (b) per-environment CI keys. Cadence below.

## Part 1: Rotate the leaked org-admin key NOW

1. Scaleway console > IAM > API keys > **Generate API key** for your user, description `break-glass <date>`, expiry 1 year, preferred project = prod project.
2. Save access key, secret key, organization id, project ids in the password manager (`Scaleway org-admin (break-glass)`). Do not paste them anywhere else.
3. Remove the old key from the laptop: delete `SCW_ACCESS_KEY` / `SCW_SECRET_KEY` (and any `AWS_*` copy) from `terraform/.env` and shell profiles. `terraform/.env` keeps no prod-write key from here on.
4. **Delete the old (leaked) key** in the console (IAM > API keys > delete). Note its access key id first; this is the only identifier.
5. Update the GitHub secrets that still hold the old key (repo level and every environment) to a temporary value only if CI must keep running until Part 2 is done; otherwise delete them. Part 2 replaces them.
6. Verify: `scw iam api-key list` with the new key works. Confirm the old key id no longer appears in the console list.

## Part 2: Create the CI keys (apply bootstrap/ci locally, once)

Prereqs: break-glass key exported (see [`break-glass.md`](break-glass.md) step 1). Apply `terraform/bootstrap` first if the drill bucket does not exist yet.

```sh
cd terraform/bootstrap
export TF_VAR_scaleway_project_id=<prod project> TF_VAR_scaleway_organization_id=<org> TF_VAR_drill_project_id=<drill project>
terraform init && terraform plan          # review: one new bucket + ACL, nothing else
terraform apply
git add terraform.tfstate && git commit -m "chore(T-D92): bootstrap drill state bucket"

cd ci
export TF_VAR_prod_project_id=<prod> TF_VAR_drill_project_id=<drill>
export TF_VAR_state_admin_principals='["user_id:<your user uuid>"]'
terraform init
# T-D103 / ADR-0104: import the existing prod IAM BEFORE the first apply (next section),
# otherwise apply creates a second prod app identity.
terraform plan          # review; do not commit its state
terraform apply
```

### Import the env-stack IAM into bootstrap/ci (T-D103, ADR-0104)

The prod app identity (Litestream) and the restore-reader move from the prod state to `bootstrap/ci`. Prod keeps its **current** keys: cloud-init runs once, so a new key would not reach the running VM. Run this once, after `terraform init` and before the first `terraform apply` in `bootstrap/ci`. Everything here only reads the prod state; nothing writes to it (the first CI release drops the resources from prod state with `removed` blocks).

1. Read the ids from the prod state (break-glass key exported, from `terraform/`):

   ```sh
   cd terraform
   terraform init -reconfigure -backend-config=envs/prod/backend.hcl
   for a in module.iam.scaleway_iam_application.app module.iam.scaleway_iam_policy.object_storage \
            'module.restore_reader[0].scaleway_iam_application.restore_reader' \
            'module.restore_reader[0].scaleway_iam_policy.restore_reader'; do
     echo "$a: $(terraform state show -no-color "$a" | awk '$1=="id"{print $3; exit}')"
   done
   terraform state show -no-color module.iam.scaleway_iam_api_key.app | awk '$1=="access_key"{print $3}'
   terraform state show -no-color 'module.restore_reader[0].scaleway_iam_api_key.restore_reader' | awk '$1=="access_key"{print $3}'
   ```

   Ids and access key ids are not secrets, but keep them out of the repo and of chats.

2. Import them (from `terraform/bootstrap/ci`, same `TF_VAR_*` as above):

   ```sh
   terraform import module.app_prod.scaleway_iam_application.app <app id>
   terraform import module.app_prod.scaleway_iam_policy.object_storage <policy id>
   terraform import module.app_prod.scaleway_iam_api_key.app <access key id>
   terraform import module.restore_reader.scaleway_iam_application.restore_reader <id>
   terraform import module.restore_reader.scaleway_iam_policy.restore_reader <id>
   terraform import module.restore_reader.scaleway_iam_api_key.restore_reader <access key id>
   ```

3. `terraform plan`: expect **creates only** (the three CI apps, policies and keys; `module.app_drill`; the drill state bucket policy) and **no change** to anything under `module.app_prod` or `module.restore_reader`. If an imported resource shows an update or a replace, stop and compare the attributes; do not apply.
4. `terraform apply`.
5. The imported keys have no secret in the bootstrap state (Scaleway returns secrets only at creation). Read the current values once from the prod state and pipe them straight into GitHub (from `terraform/`, prod backend as in step 1):

   ```sh
   for e in prod prod-plan; do
     terraform output -raw scw_access_key | gh secret set APP_SCW_ACCESS_KEY --env "$e"
     terraform output -raw scw_secret_key | gh secret set APP_SCW_SECRET_KEY --env "$e"
   done
   for e in drill drill-teardown drill-plan; do
     terraform output -raw restore_reader_access_key | gh secret set PROD_REPLICA_RO_ACCESS_KEY --env "$e"
     terraform output -raw restore_reader_secret_key | gh secret set PROD_REPLICA_RO_SECRET_KEY --env "$e"
   done
   ```

   These outputs exist in the prod state until the first CI release; do this before it.
6. The remaining values come from `bootstrap/ci` outputs:

   | Secret | `prod`, `prod-plan` | `drill`, `drill-teardown`, `drill-plan` |
   |---|---|---|
   | `APP_APPLICATION_ID` | `app_application_ids["prod"]` | `app_application_ids["drill"]` |
   | `APP_SCW_ACCESS_KEY` / `APP_SCW_SECRET_KEY` | step 5 | `app_drill_access_key` / `app_drill_secret_key` |
   | `RESTORE_READER_APPLICATION_ID` | `restore_reader_application_id` | (not set) |

7. After the first prod release from `main` has applied (its plan shows `module.iam` and `module.restore_reader` as "will no longer be managed", nothing destroyed), drop ci-prod's transitional IAM read access: `terraform apply -var ci_prod_iam_transition=false` in `bootstrap/ci`, then re-run a prod plan (`terraform.yml` on a PR) to confirm it still succeeds.

The `ci` state contains the keys' secrets. Keep `terraform/bootstrap/ci/terraform.tfstate` out of git (already ignored); copy it into the password manager (secure note/attachment) or an encrypted backup.

Put the keys in GitHub (Settings > Environments > <env> > Environment secrets). Pipe outputs straight to the clipboard or `gh`, never echo to a shared terminal log:

| Environment | `SCW_ACCESS_KEY` / `SCW_SECRET_KEY` from outputs |
|---|---|
| `prod` | `ci_prod_access_key` / `ci_prod_secret_key` |
| `prod-plan` | `ci_plan_access_key` / `ci_plan_secret_key` |
| `drill` | `ci_drill_access_key` / `ci_drill_secret_key` |

```sh
terraform output -raw ci_prod_secret_key | gh secret set SCW_SECRET_KEY --env prod
terraform output -raw ci_prod_access_key | gh secret set SCW_ACCESS_KEY --env prod
```

Then **delete repo-level `SCW_ACCESS_KEY`/`SCW_SECRET_KEY`** so a missing environment secret fails instead of falling back. Also set the drill backend: `terraform -chdir=terraform init -reconfigure -backend-config=envs/drill/backend.hcl` (drill state was empty; nothing to migrate).

### Verify, then lock down prod state

1. Run the Terraform workflow on a PR: both plan legs (`drill`, `prod-plan`) must succeed. If the prod plan cannot lock, use `-lock=false` in that job (ADR-0100 section 3).
2. Trigger a drill (`restore-drill.yml`): it must init against the drill bucket and create/destroy.
3. Only then set `restrict_prod_state_bucket = true` and re-apply `bootstrap/ci` (with break-glass key and the admin principal listed). Re-run a prod plan.
4. Confirm isolation: the ci-drill key must get 403 on `s3://budget-planner-tfstate-pl-waw`.

## Cadence

| Key | Lifetime | Rotate |
|---|---|---|
| CI keys (prod, drill, plan) | 1 year | every 11 months or on the expiry alert |
| Org-admin break-glass | 1 year | yearly, and after every use that touched an untrusted machine |
| Litestream app key (per env, `bootstrap/ci` output `app_key_expires_at`) | 1 year | per `deploy.md` "Rotate the Litestream API key" |
| Restore-reader key (`bootstrap/ci`) | 1 year (Scaleway default) | `terraform apply -replace=module.restore_reader.scaleway_iam_api_key.restore_reader` in `bootstrap/ci`, then update `PROD_REPLICA_RO_*` in the drill environments |
| Tailscale OAuth clients | no expiry | yearly review; immediately on suspected leak |

## On an expiry alert

`key-expiry.yml` opens/updates the issue "Scaleway API key expiring soon" (weekly, threshold 30 days). For a CI key:

1. In `terraform/bootstrap/ci`: `terraform apply -replace=scaleway_iam_api_key.ci_<prod|drill|plan>` with the break-glass key. This creates a new key (new `expires_at`) and deletes the old one.
2. Update the matching environment secrets (table above).
3. Re-run the failed/next workflow to confirm; close the issue.
For a Litestream key follow `deploy.md`.

## Rollback

If new CI keys do not work, restore access with the break-glass key ([`break-glass.md`](break-glass.md)); do not re-create a shared admin key in GitHub.
