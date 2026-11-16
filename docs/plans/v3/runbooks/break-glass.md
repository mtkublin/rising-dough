# Runbook: Break-glass (org-admin key)

**Context.** ADR-0099/ADR-0100: prod changes ship only from GitHub Actions on `main`. The org-admin Scaleway key is stored only in the operator's password manager. It is not in `terraform/.env`, not in GitHub, not in shell profiles. Using it is an exception that is logged.

## When allowed

- GitHub Actions is down or the `prod` environment cannot run, and the change is urgent (outage, security fix).
- A Terraform state lock is stuck and CI cannot clear it (see "Stuck lock").
- The CI credentials are broken (expired, deleted, policy drift) and must be re-issued: apply `terraform/bootstrap/ci`.
- Applying the bootstrap roots (`terraform/bootstrap`, `terraform/bootstrap/ci`), which CI never applies (ADR-0096).

Not allowed: convenience, "quick" prod edits, testing. Use the drill environment for experiments.

## Preconditions

- Password manager entry `Scaleway org-admin (break-glass)` holds access key, secret key, organization id, project ids.
- Work from `main` at the commit you intend to ship (the same one CI would run), clean tree.

## Procedure

1. **Fetch the key** into the current shell only. Never write it to a file.
   ```sh
   read -rs SCW_SECRET_KEY; export SCW_SECRET_KEY      # paste, Enter
   export SCW_ACCESS_KEY=SCWXXXXXXXXXXXXXXXXX
   export AWS_ACCESS_KEY_ID=$SCW_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$SCW_SECRET_KEY
   ```
2. **Scratch copy of the exact commit** (no local junk, no `.env`):
   ```sh
   SCRATCH=$(mktemp -d) && git archive HEAD terraform | tar -x -C "$SCRATCH"
   cd "$SCRATCH/terraform"
   ```
3. **Inputs** as `TF_VAR_*` environment variables (same names CI uses, ADR-0093), from the password manager. Never use a tfvars file with secrets.
4. **Init and plan, piped through the masker** (ADR-0098), saving the binary plan:
   ```sh
   terraform init -reconfigure -backend-config=envs/prod/backend.hcl
   terraform plan -out=tfplan -no-color 2>&1 | python3 <repo>/terraform/scripts/mask_plan.py
   ```
   Read the plan. Anything unexpected: stop.
5. **Apply the saved plan only** (never `apply` without a plan file):
   ```sh
   terraform apply tfplan
   ```
6. **Clean up**: `rm -rf "$SCRATCH"; unset SCW_ACCESS_KEY SCW_SECRET_KEY AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY`; close the shell.

## Stuck lock

State uses `use_lockfile` (an object `<key>.tflock` in the state bucket). First check no CI run is active (GitHub Actions UI). Then:

```sh
terraform force-unlock <LOCK_ID>          # the ID is printed in the failed run's error
```

If the ID is lost, delete the lock object `prod/terraform.tfstate.tflock` (or `drill/...`) with the admin key. Only force-unlock when you are sure no apply is running: unlocking during a live apply corrupts state. Versioning on the state bucket allows rollback of a bad state write.

## After use (mandatory)

1. Append a dated line to `docs/CHANGELOG.md` stating why break-glass was used, what was applied (plan summary, commit SHA), and who ran it. Land it through a normal PR.
2. If the change was not already on `main`, land it on `main` so the next CI run sees no drift.
3. **Rotate the org-admin key** if it touched a laptop with other tooling, appeared in any output, or per yearly cadence ([`key-rotation.md`](key-rotation.md)).
4. Confirm the next scheduled `terraform plan` in CI shows no unexpected diff.

## Revert to normal

Normal state = the laptop holds no prod-write key and CI applies via the `prod` environment. Verify: `env | grep -E 'SCW_|AWS_'` is empty and `grep -c SCW terraform/.env` is 0.

## Troubleshooting

- **403 on state bucket**: the admin principal must be in `state_admin_principals` of `terraform/bootstrap/ci` (bucket policy allow-list, ADR-0091). Fix by applying that stack with the admin key (the owner can still edit the bucket policy through the console).
- **Plan wants to recreate the instance**: stop; do not apply. See `deploy.md`/`disaster-recovery.md`.
