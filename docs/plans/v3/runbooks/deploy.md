# Runbook — Deploy

> **SSH access (ADR-0094):** port 22 is closed to the internet. Join the tailnet (Tailscale app on your machine, see [`tailscale-ssh.md`](tailscale-ssh.md)) and use the MagicDNS names `budget-planner-prod` / `budget-planner-drill`. Every host placeholder below means that name.

Standard release of a new SHA to production.

## Context

v3 deploys land on the single Scaleway Stardust VM. Prod is released only by `.github/workflows/release.yml`, on push to `main` (ADR-0099): `ci` -> `build` (pushes the immutable `sha-<short>` image to GHCR, cosign-signed) -> `tf-apply-prod` -> `deploy-prod`. `deploy.yml` is a reusable (`workflow_call`) workflow with no triggers of its own; it SSHes into the host as the restricted `deploy` user to roll the `app` container forward. The on-host shim is `/usr/local/bin/deploy-budget-planner` (ADR-0037 §3).

The happy-path contract: merge to `main` -> CI green -> image built and signed -> `terraform apply prod` waits for the `prod` environment approval -> `deploy-prod` waits for the same approval -> the deploy user pulls the tag, swaps the `app` service, and `/ready` returns 200 within 30 s.

## Preconditions

- Pre-merge CI (`.github/workflows/ci.yml`) is green on the merge commit.
- The merge commit is on `main`.
- Image `ghcr.io/<owner>/budget-planner:sha-<short>` exists in GHCR and is signed (keyless cosign, GitHub OIDC).
- Operator has access to the GitHub Actions environment named `prod` and 2FA active on their GitHub account.
- Prod host DNS (`budget-planner-prod`) still resolves to the Scaleway Flex IPv4 recorded in `terraform output prod_host_ipv4`.
- `budget-planner-prod-pl-waw` bucket is reachable from the host (Litestream health probe green in the last 5 min).

## Procedure

1. Confirm the `release.yml` run for the target commit is green up to the approval gates:
   - `gh run list --workflow=release.yml --branch=main --limit=5`
   - Expect `ci` and `build` to be `success` for the merge commit you intend to deploy.
2. Approve the `prod` environment for `tf-apply-prod` and then for `deploy-prod`. Both jobs wait on the same required-reviewer gate (`gh run approve <run-id>` or the Actions UI). This is the single human gate on prod.
   - Re-deploying an already built SHA (e.g. after rolling back) is not a `deploy.yml` dispatch. Use `rollback.yml` with `image_sha` (see [`rollback.md`](rollback.md)).
3. Deploy job executes (CI runner, not the host):
   - Verifies the cosign signature on `ghcr.io/<owner>/budget-planner:sha-<short>`.
   - Opens an SSH session to the `deploy` user: `ssh deploy@budget-planner-prod "deploy sha-<short>"`.
   - The on-host shim pulls the new tag, writes the previous tag to `.previous-tag`, runs `docker compose up -d app`, and probes `/ready` up to 30 times at 1 s intervals.
   - The new container's entrypoint (`/app/docker-entrypoint.sh`, ADR-0071) runs `python -m budget_planner.db.startup_migrate` before uvicorn starts. When migrations are pending it first writes a backup to `/data/backups/budget.db.pre-migrate-<NNNN>-<ts>` (newest 3 kept, none older than `backup_max_age_days - 7` = 30 d) and then applies them, each in its own transaction. It logs `event="startup_migrations"`. Nothing is written when the schema is already current. The old container is stopped before the new one starts, so there is only ever one writer.
4. Watch the GitHub Actions step summary:
   - Successful run posts the deployed SHA + the compare link against the previous SHA.
   - Failed probe is auto-reverted by the shim (see Troubleshooting).

## Verification

Run from your workstation. All three must pass before the deploy is considered done.

```sh
# TLS + reachability + readiness.
curl -fsS "https://budget-planner-prod/ready" | jq .
# Expect: {"status":"ok","db":"ok","litestream":"ok", ...}

# Deployed revision matches target SHA (image label is written at build time).
ssh app@budget-planner-prod \
  "docker inspect --format='{{index .Config.Labels \"org.opencontainers.image.revision\"}}' budget-planner-app-1"
# Expect: <full SHA> matching the git revision deployed.

# Caddy still serving HTTPS with current cert.
curl -fsSI "https://budget-planner-prod/" | grep -i strict-transport-security
# Expect: Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

**One-time sign-out (T-D53a, migration `0015_session_hardening`)**: the deploy that first ships this migration revokes every live session, because session ids are now stored hashed. Every user (including the operator) signs in again once. Rolling back to an N-1 image has the same effect (old code cannot resolve hashed ids); no restore is needed.

Then record the deploy in the GitHub `prod` environment history (automatic — nothing to do). If this deploy ships a schema migration, confirm it was applied and backed up:

```sh
ssh app@budget-planner-prod \
  "sqlite3 /data/budget.db 'SELECT version, filename, applied_at FROM schema_migrations ORDER BY version DESC LIMIT 3;'"
ssh app@budget-planner-prod "ls -l /data/backups/"
ssh app@budget-planner-prod "docker logs budget-planner-app 2>&1 | grep startup_migrations | tail -1"
# Expect: applied=[...new files...] and backup=/data/backups/budget.db.pre-migrate-...
```

Before deploying a release whose CHANGELOG entry says **"rollback requires restore"** (not N-1 compatible, ADR-0071 §4), note the UTC time. If you have to roll back, that timestamp is your restore point.

## Post-deploy smoke journey

Run after a green deploy (T-D43, human step; never in CI). One Playwright journey: admin sign-in (+ forced rotation), create a second user, forced rotation, virtual-authenticator passkey, add a transaction, data-isolation check on the admin `/ledger`, `/debug/audit-tail` audit check, then soft-delete the smoke user.

```sh
SMOKE_BASE_URL=https://budget-planner-prod \
SMOKE_ADMIN_EMAIL=<admin-email> \
SMOKE_ADMIN_PASSWORD=<terraform-captured-or-current-password> \
SMOKE_ADMIN_NEW_PASSWORD=<new admin password, 12+ chars> \
uv run pytest -m smoke tests/smoke -v --no-cov
```

Notes: the passkey step registers from Settings → Security (`/settings/security#passkeys`, ADR-0075); the test leaves one soft-deleted `smoke-<hex>@smoke.test` user and its data; it falls back to `SMOKE_ADMIN_NEW_PASSWORD` if the admin was already rotated. `BUDGET_WEBAUTHN_RP_ID` / `BUDGET_WEBAUTHN_ORIGIN` on the server must match `SMOKE_BASE_URL`. Details: [`../phase-4-validation/T-D43-smoke-journey.md`](../phase-4-validation/T-D43-smoke-journey.md).

## Memory check

The VM has 1 GB RAM plus a 1 GiB swapfile (T-D82, ADR-0032 amendment). Run on the VM after first boot and after deploys:

```sh
free -m                          # swap "used" should stay near 0
swapon --show                    # /swapfile, 1024M
sysctl vm.swappiness             # 10
docker stats --no-stream
sudo dmesg | grep -i oom         # expect no output
```

Resize to a larger type only if steady state exceeds about 700 MB or swap is used continuously. Resizing is manual and causes downtime.

## Troubleshooting

- **`cosign verify` fails on the runner**: image was built outside the expected GitHub OIDC identity or the signature is missing. Do **not** bypass. Dispatch `build.yml` on `main` for the same SHA (dispatch is `main`-only); if the signature still fails, treat as a supply-chain red flag and rotate `GHCR_PAT` + `DEPLOY_SSH_PRIVATE_KEY` before trying again.
- **SSH session rejected**: `deploy` user is key-restricted via `authorized_keys` with `command="/usr/local/bin/deploy-budget-planner"`. If the key does not match or `GITHUB_ACTIONS` IP is temporarily rate-limited by `fail2ban`, wait 10 min or SSH as `app` and `sudo fail2ban-client set sshd unbanip <gha-runner-ip>`.
- **`/ready` probe fails during deploy**: the shim auto-reverts to `.previous-tag` and exits non-zero. Deploy workflow step summary shows the probe response + the last 50 log lines. Investigate before retrying; usually either a migration failure or Litestream not yet healthy.
- **`startup_migrations_failed` in the app log**: the entrypoint exited 1 and uvicorn never started. The failing migration was rolled back in its own transaction, but earlier migrations in the same batch stay applied. Each one is N-1 compatible, so the auto-reverted previous image still runs. Fix the migration in a new release. Never edit an applied migration file, because the checksum guard rejects it.
- **`docker compose pull` 403s against GHCR**: `GHCR_PAT` expired. Rotate per `disaster-recovery.md` §Secrets and re-render `/etc/docker/config.json` via a break-glass prod apply (cloud-init runs once; see the Terraform plans section below).
- **Deploy succeeded but DNS still points elsewhere**: `terraform output prod_host_ipv4` vs `dig +short budget-planner-prod`. If they diverge, DNS was manually edited; reconcile via Terraform.

## Rollback

- Auto-rollback is built into the shim — a failing `/ready` probe reverts to `.previous-tag` without manual action.
- Manual rollback (last known-good SHA, e.g. after discovering a prod-only bug minutes after a green deploy): see [`rollback.md`](rollback.md). Shape: `gh workflow run rollback.yml --ref main -f env=prod`.

## Rotate the Litestream API key (yearly, before expires_at)

Scaleway gives `scaleway_iam_api_key.app` a 1-year expiry (T-D74, ADR-0092). Terraform ignores that attribute, so nothing warns you. After expiry Litestream replication fails and backups stop.

1. Read the date: `terraform -chdir=terraform output scw_app_key_expires_at`. Rotate at least 30 days before it (checklist F).
2. Replace the key: `terraform -chdir=terraform apply -replace='module.iam.scaleway_iam_api_key.app'`. This is not a pipeline action (`release.yml` never passes `-replace`). Run it only with explicit user go, under [`break-glass.md`](break-glass.md), and log it in `docs/CHANGELOG.md`.
3. Impact: the key is rendered into the instance `cloud_init` (`/etc/budget-planner/litestream.env`), so the plan also shows a `cloud_init` change on `scaleway_instance_server.app`. Read the plan first. If it says the server is replaced, stop: that recreates the VM and takes the restore path (see `disaster-recovery.md`). If it is an in-place update, cloud-init does not re-run on an existing VM (a `cloud_init` change only takes effect via `-replace=module.compute.scaleway_instance_server.app`, ADR-0098), so the host keeps the old key until step 4. Always read the plan through `just tf-plan-safe <env>` or `| python3 terraform/scripts/mask_plan.py`; the first plan after ADR-0098 may still print the old `cloud_init` unmasked once.
4. Refresh the host secret by hand over Tailscale SSH. Print the new values with `terraform output -raw scw_access_key` and `scw_secret_key`. Update `SCW_ACCESS_KEY` / `SCW_SECRET_KEY` in `/etc/budget-planner/litestream.env` (mode 0600). Then run `cd /etc/budget-planner && docker compose up -d --force-recreate litestream`.
5. Verify: `docker compose logs --tail=50 litestream` shows no auth errors, and a fresh Litestream snapshot or generation appears in the bucket.
6. Check `scw_app_key_expires_at` is about one year ahead. Replace deletes the old key immediately, so there is no overlap window. Do steps 2 to 4 in one sitting; replication is paused only for that gap.

## Terraform plans and cloud-init changes (T-D83, ADR-0098)

- `cloud_init` embeds secrets. Run plans via `just tf-plan-safe drill|prod`, or pipe through `python3 terraform/scripts/mask_plan.py`. CI already does.
- The first apply after ADR-0098 can show the OLD `cloud_init` once (state lacks the sensitive mark); mask it as above. That apply records the mark.
- cloud-init runs once. A user-data change (`cloud_init`) plans as `updated in-place` but does nothing on the running VM. To apply it, the server must be replaced (`-replace=module.compute.scaleway_instance_server.app`). That is not a pipeline action: explicit user go, under [`break-glass.md`](break-glass.md). It recreates the VM; data restores from Litestream (see `disaster-recovery.md`).
