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
terraform init && terraform plan          # review; do not commit its state
terraform apply
```

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
| Litestream app key (per env, `scw_app_key_expires_at`) | 1 year | per `deploy.md` "Rotate the Litestream API key" |
| Tailscale OAuth clients | no expiry | yearly review; immediately on suspected leak |

## On an expiry alert

`key-expiry.yml` opens/updates the issue "Scaleway API key expiring soon" (weekly, threshold 30 days). For a CI key:

1. In `terraform/bootstrap/ci`: `terraform apply -replace=scaleway_iam_api_key.ci_<prod|drill|plan>` with the break-glass key. This creates a new key (new `expires_at`) and deletes the old one.
2. Update the matching environment secrets (table above).
3. Re-run the failed/next workflow to confirm; close the issue.
For a Litestream key follow `deploy.md`.

## Rollback

If new CI keys do not work, restore access with the break-glass key ([`break-glass.md`](break-glass.md)); do not re-create a shared admin key in GitHub.
