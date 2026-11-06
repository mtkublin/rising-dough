# Runbook — Deploy

Standard release of a new SHA to production.

## Context

v3 deploys land on the single Scaleway Stardust VM via a GitHub Actions pipeline that pushes a new container image to GHCR and SSHes into the host as the restricted `deploy` user to roll the `app` container forward. The pipeline is defined in `.github/workflows/build.yml` + `.github/workflows/deploy.yml`; the on-host shim is `/usr/local/bin/deploy-budget-planner` (ADR-0037 §3).

The happy-path contract: CI green → image signed by cosign → GHCR tag `sha-<short>` exists → operator approves the `prod` environment in GitHub → the deploy user pulls the tag, swaps the `app` service, and `/ready` returns 200 within 30 s.

## Preconditions

- Pre-merge CI (`.github/workflows/ci.yml`) is green on the merge commit.
- The merge commit is on `main`.
- Image `ghcr.io/<owner>/budget-planner:sha-<short>` exists in GHCR and is signed (keyless cosign, GitHub OIDC).
- Operator has access to the GitHub Actions environment named `prod` and 2FA active on their GitHub account.
- Prod host DNS (`<prod-host>`) still resolves to the Scaleway Flex IPv4 recorded in `terraform output prod_host_ipv4`.
- `budget-planner-prod-pl-waw` bucket is reachable from the host (Litestream health probe green in the last 5 min).

## Procedure

1. Confirm `build.yml` succeeded for the target commit:
   - `gh run list --workflow=build.yml --branch=main --limit=5`
   - Expect `completed · success` for the SHA you intend to deploy.
2. Trigger the deploy workflow:
   - Automatic trigger: `build.yml` success enqueues `deploy.yml` and parks it on the `prod` environment approval gate.
   - Manual trigger (re-deploy same SHA, e.g. after rolling back): `gh workflow run deploy.yml -f sha=<short-sha>`.
3. Approve the `prod` environment in the GitHub Actions UI (or `gh run approve <run-id>`). The approval line is the single human gate on prod.
4. Deploy step executes (CI runner, not the host):
   - Verifies the cosign signature on `ghcr.io/<owner>/budget-planner:sha-<short>`.
   - Opens an SSH session to the `deploy` user: `ssh deploy@<prod-host> "deploy sha-<short>"`.
   - The on-host shim pulls the new tag, writes the previous tag to `.previous-tag`, runs `docker compose up -d app`, and probes `/ready` up to 30 times at 1 s intervals.
   - The new container's entrypoint (`/app/docker-entrypoint.sh`, ADR-0071) runs `python -m budget_planner.db.startup_migrate` before uvicorn starts. When migrations are pending it first writes a backup to `/data/backups/budget.db.pre-migrate-<NNNN>-<ts>` (newest 3 kept, none older than `backup_max_age_days - 7` = 30 d) and then applies them, each in its own transaction. It logs `event="startup_migrations"`. Nothing is written when the schema is already current. The old container is stopped before the new one starts, so there is only ever one writer.
5. Watch the GitHub Actions step summary:
   - Successful run posts the deployed SHA + the compare link against the previous SHA.
   - Failed probe is auto-reverted by the shim (see Troubleshooting).

## Verification

Run from your workstation. All three must pass before the deploy is considered done.

```sh
# TLS + reachability + readiness.
curl -fsS "https://<prod-host>/ready" | jq .
# Expect: {"status":"ok","db":"ok","litestream":"ok", ...}

# Deployed revision matches target SHA (image label is written at build time).
ssh app@<prod-host> \
  "docker inspect --format='{{index .Config.Labels \"org.opencontainers.image.revision\"}}' budget-planner-app-1"
# Expect: <full SHA> matching the git revision deployed.

# Caddy still serving HTTPS with current cert.
curl -fsSI "https://<prod-host>/" | grep -i strict-transport-security
# Expect: Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

**One-time sign-out (T-D53a, migration `0015_session_hardening`)**: the deploy that first ships this migration revokes every live session, because session ids are now stored hashed. Every user (including the operator) signs in again once. Rolling back to an N-1 image has the same effect (old code cannot resolve hashed ids); no restore is needed.

Then record the deploy in the GitHub `prod` environment history (automatic — nothing to do). If this deploy ships a schema migration, confirm it was applied and backed up:

```sh
ssh app@<prod-host> \
  "sqlite3 /data/budget.db 'SELECT version, filename, applied_at FROM schema_migrations ORDER BY version DESC LIMIT 3;'"
ssh app@<prod-host> "ls -l /data/backups/"
ssh app@<prod-host> "docker logs budget-planner-app 2>&1 | grep startup_migrations | tail -1"
# Expect: applied=[...new files...] and backup=/data/backups/budget.db.pre-migrate-...
```

Before deploying a release whose CHANGELOG entry says **"rollback requires restore"** (not N-1 compatible, ADR-0071 §4), note the UTC time. If you have to roll back, that timestamp is your restore point.

## Post-deploy smoke journey

Run after a green deploy (T-D43, human step; never in CI). One Playwright journey: admin sign-in (+ forced rotation), create a second user, forced rotation, virtual-authenticator passkey, add a transaction, data-isolation check on the admin `/ledger`, `/debug/audit-tail` audit check, then soft-delete the smoke user.

```sh
SMOKE_BASE_URL=https://<prod-host> \
SMOKE_ADMIN_EMAIL=<admin-email> \
SMOKE_ADMIN_PASSWORD=<terraform-captured-or-current-password> \
SMOKE_ADMIN_NEW_PASSWORD=<new admin password, 12+ chars> \
uv run pytest -m smoke tests/smoke -v --no-cov
```

Notes: the passkey step registers from Settings → Security (`/settings/security#passkeys`, ADR-0075); the test leaves one soft-deleted `smoke-<hex>@smoke.test` user and its data; it falls back to `SMOKE_ADMIN_NEW_PASSWORD` if the admin was already rotated. `BUDGET_WEBAUTHN_RP_ID` / `BUDGET_WEBAUTHN_ORIGIN` on the server must match `SMOKE_BASE_URL`. Details: [`../phase-4-validation/T-D43-smoke-journey.md`](../phase-4-validation/T-D43-smoke-journey.md).

## Troubleshooting

- **`cosign verify` fails on the runner**: image was built outside the expected GitHub OIDC identity or the signature is missing. Do **not** bypass. Re-run `build.yml` on the same SHA; if the signature still fails, treat as a supply-chain red flag and rotate `GHCR_PAT` + `DEPLOY_SSH_PRIVATE_KEY` before trying again.
- **SSH session rejected**: `deploy` user is key-restricted via `authorized_keys` with `command="/usr/local/bin/deploy-budget-planner"`. If the key does not match or `GITHUB_ACTIONS` IP is temporarily rate-limited by `fail2ban`, wait 10 min or SSH as `app` and `sudo fail2ban-client set sshd unbanip <gha-runner-ip>`.
- **`/ready` probe fails during deploy**: the shim auto-reverts to `.previous-tag` and exits non-zero. Deploy workflow step summary shows the probe response + the last 50 log lines. Investigate before retrying; usually either a migration failure or Litestream not yet healthy.
- **`startup_migrations_failed` in the app log**: the entrypoint exited 1 and uvicorn never started. The failing migration was rolled back in its own transaction, but earlier migrations in the same batch stay applied. Each one is N-1 compatible, so the auto-reverted previous image still runs. Fix the migration in a new release. Never edit an applied migration file, because the checksum guard rejects it.
- **`docker compose pull` 403s against GHCR**: `GHCR_PAT` expired. Rotate per `disaster-recovery.md` §Secrets and re-render `/etc/docker/config.json` via `terraform apply`.
- **Deploy succeeded but DNS still points elsewhere**: `terraform output prod_host_ipv4` vs `dig +short <prod-host>`. If they diverge, DNS was manually edited; reconcile via Terraform.

## Rollback

- Auto-rollback is built into the shim — a failing `/ready` probe reverts to `.previous-tag` without manual action.
- Manual rollback (last known-good SHA, e.g. after discovering a prod-only bug minutes after a green deploy): see [`rollback.md`](rollback.md). Shape: `gh workflow run rollback.yml` or `ssh deploy@<prod-host> "rollback"`.
