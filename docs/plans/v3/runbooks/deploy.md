# Runbook — Deploy

> **SSH access (ADR-0094):** port 22 is closed to the internet. Join the tailnet (Tailscale app on your machine, see [`tailscale-ssh.md`](tailscale-ssh.md)) and use the MagicDNS names `budget-planner-prod` / `budget-planner-drill-<run id>`. Every host placeholder below means that name.

Standard release of a new version to production (a published GitHub release).

## Context

v3 releases land on the single Scaleway Stardust VM. Prod is released only by `.github/workflows/release.yml`, when a GitHub release is published (ADR-0099, ADR-0109): `guard` (tag is SemVer `vMAJOR.MINOR.PATCH` and its commit is an ancestor of `origin/main`) -> `ci` -> `build` (pushes the immutable image to GHCR as `sha-<short>` and `vX.Y.Z`, cosign-signed) -> `tf-apply-prod`.

ADR-0111: Terraform declares the whole host state in instance metadata (`user_data` keys `cloud-init`, `bp-agent`, `bp-config`). The release is that one apply: it sets `app_image_ref = vX.Y.Z@sha256:<digest>` and records the ref it replaces as `app_image_previous_ref`. On the host, `bp-converge.timer` runs the agent every 30 s; it reads `bp-config`, cosign-verifies the image, writes the managed files (compose, Caddyfile, Litestream, registry auth), runs `docker compose pull` + `up -d`, probes `/ready` and publishes `/.well-known/bp-deploy-status.json`. Nothing SSHes into the host.

Merging to `main` builds nothing for prod, so prod can lag `main`. The happy-path contract: merge to `main` -> operator publishes release `vX.Y.Z` -> CI green -> image built and signed -> `terraform apply prod` waits for the `prod` environment approval (the only one) -> the same job waits until the host reports the new generation applied (default budget 10 min) -> done. If the host reports a failure or times out, the job re-applies with the refs swapped (automatic rollback), waits again, and still fails.

## Preconditions

- Pre-merge CI (`.github/workflows/ci.yml`) is green on the merge commit.
- The commit to release is on `main`, and the drill gate was green on the PR that merged it.
- Pick the next SemVer `vMAJOR.MINOR.PATCH` (no pre-release suffix). Tags are immutable (tag ruleset, `github-settings.md` section 3b); a wrong tag is superseded by a new version, never moved.
- Image `ghcr.io/<owner>/budget-planner:vX.Y.Z` exists in GHCR and is signed (keyless cosign, GitHub OIDC).
- Operator has access to the GitHub Actions environment named `prod` and 2FA active on their GitHub account.
- Prod host DNS (`budget-planner-prod`) still resolves to the Scaleway Flex IPv4 recorded in `terraform output prod_host_ipv4`.
- `budget-planner-prod-pl-waw` bucket is reachable from the host (Litestream health probe green in the last 5 min).

## Procedure

0. Cut the release (operator, from any checkout):
   ```sh
   gh release create vX.Y.Z --target main --title "vX.Y.Z" --generate-notes
   ```
   Publishing triggers `release.yml`. A draft does not. To re-run a failed release for the same tag: `gh workflow run release.yml --ref vX.Y.Z -f tag=vX.Y.Z` (the ref and the input must be the same tag).
1. Confirm the `release.yml` run for the tag is green up to the approval gates:
   - `gh run list --workflow=release.yml --limit=5`
   - Expect `guard`, `ci` and `build` to be `success`. `guard` fails if the tag is not SemVer or its commit is not on `main`.
2. Approve the `prod` environment once, for `tf-apply-prod` (review prompt in the Actions UI). This is the single human gate on prod.
   - Re-deploying an already built image (e.g. after rolling back) goes through `rollback.yml` with `target` (see [`rollback.md`](rollback.md)).
3. The apply job (CI runner):
   - Resolves the refs: the ref in state becomes `app_image_previous_ref`; both are printed.
   - Applies. The plan shows an in-place `user_data` update on `scaleway_instance_server.app` (masked). Anything else (server replaced!) means stop and investigate.
   - Polls `https://<prod fqdn>/.well-known/bp-deploy-status.json` until `generation` equals `terraform output host_config_generation`, `state` is `ok` and `running_ref` is the new ref.
   - On the host the agent verifies the cosign signature, pulls, recreates `app` and probes `/ready`. The new container's entrypoint (`/app/docker-entrypoint.sh`, ADR-0071) runs `python -m budget_planner.db.startup_migrate` before uvicorn starts. When migrations are pending it first writes a backup to `/data/backups/budget.db.pre-migrate-<NNNN>-<ts>` (newest 3 kept, none older than `backup_max_age_days - 7` = 30 d) and then applies them, each in its own transaction. It logs `event="startup_migrations"`. Nothing is written when the schema is already current. Compose stops the old container before the new one starts, so there is only ever one writer.
4. Watch the GitHub Actions step summary:
   - A green run logged `converged: {...}` with the new generation.
   - A failed release shows `::warning::host did not converge on …; rolling back to …` and ends with `::error::release rolled back to …` (see Troubleshooting).

## Verification

Run from your workstation. All three must pass before the deploy is considered done.

```sh
# TLS + reachability + readiness.
curl -fsS "https://budget-planner-prod/ready" | jq .
# Expect: {"status":"ok","db":"ok","litestream":"ok", ...}

# Host agent reports the release applied (ADR-0111).
curl -fsS "https://budget-planner-prod/.well-known/bp-deploy-status.json" | jq .
# Expect: state "ok", running_ref ".../budget-planner:vX.Y.Z@sha256:...", previous_ref the release before.

# Caddy still serving HTTPS with current cert.
curl -fsSI "https://budget-planner-prod/" | grep -i strict-transport-security
# Expect: Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

**One-time sign-out (T-D53a, migration `0015_session_hardening`)**: the deploy that first ships this migration revokes every live session, because session ids are now stored hashed. Every user (including the operator) signs in again once. Rolling back to an N-1 image has the same effect (old code cannot resolve hashed ids); no restore is needed.

Then record the deploy in the GitHub `prod` environment history (automatic — nothing to do). If this deploy ships a schema migration, confirm it was applied and backed up:

```sh
ssh operator@budget-planner-prod \
  "sqlite3 /data/budget.db 'SELECT version, filename, applied_at FROM schema_migrations ORDER BY version DESC LIMIT 3;'"
ssh operator@budget-planner-prod "ls -l /data/backups/"
ssh operator@budget-planner-prod "docker logs budget-planner-app 2>&1 | grep startup_migrations | tail -1"
# Expect: applied=[...new files...] and backup=/data/backups/budget.db.pre-migrate-...
```

Before deploying a release whose CHANGELOG entry says **"rollback requires restore"** (not N-1 compatible, ADR-0071 §4), note the UTC time. If you have to roll back, that timestamp is your restore point.

## Post-deploy smoke journey

Run on a kept explore drill (T-D43), never against prod (decision 2026-11-18): on prod it would use the real admin account and leave a smoke user and data behind. One Playwright journey: admin sign-in (+ forced rotation), create a second user, forced rotation, virtual-authenticator passkey, add a transaction, data-isolation check on the admin `/ledger`, `/debug/audit-tail` audit check, then soft-delete the smoke user.

```sh
SMOKE_BASE_URL=https://budget-planner-drill-<run id>.<tailnet>.ts.net \
SMOKE_ADMIN_EMAIL=<drill admin email> \
SMOKE_ADMIN_PASSWORD=<drill admin password> \
SMOKE_ADMIN_NEW_PASSWORD=<new admin password, 12+ chars> \
uv run pytest -m smoke tests/smoke -v --no-cov
```

Notes: the passkey step registers from Settings → Security (`/settings/security#passkeys`, ADR-0075); the test leaves one soft-deleted `smoke-<hex>@smoke.test` user and its data (gone with the drill); it falls back to `SMOKE_ADMIN_NEW_PASSWORD` if the admin was already rotated. `BUDGET_WEBAUTHN_RP_ID` / `BUDGET_WEBAUTHN_ORIGIN` on the server must match `SMOKE_BASE_URL` (not set on the hosts yet: T-D135). Drill admin password: in `/etc/budget-planner/docker-compose.yml` on the drill VM; read it in your own terminal, never into a chat. Details: [`../phase-4-validation/T-D43-smoke-journey.md`](../phase-4-validation/T-D43-smoke-journey.md).

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

- **Status `error: cosign_verify`**: the image was built outside the expected GitHub OIDC identity (`build.yml` on this repo) or the signature is missing. Do **not** bypass. Dispatch `build.yml` from `main` or the `v*` tag (dispatch is main-or-tag-on-main only); if the signature still fails, treat it as a supply-chain red flag and rotate `GHCR_PULL_PAT` before trying again.
- **Status `error: ready_timeout`**: the new image never answered `/ready`; the job rolled back automatically. Read the app log (`ssh operator@budget-planner-prod 'docker logs budget-planner-app --tail 100'`). Usually a migration failure or Litestream not yet healthy.
- **Status never reaches the new generation**: the agent did not run or cannot read metadata. `ssh operator@budget-planner-prod 'systemctl status bp-converge.timer; sudo journalctl -u bp-converge.service -n 50 --no-pager'`. A `config_fetch` error means the metadata API answered non-200. After repeated failures the agent backs off (30 s doubling, max 15 min) per generation; a new apply resets it.
- **`startup_migrations_failed` in the app log**: the entrypoint exited 1 and uvicorn never started. The failing migration was rolled back in its own transaction, but earlier migrations in the same batch stay applied. Each one is N-1 compatible, so the auto-reverted previous image still runs. Fix the migration in a new release. Never edit an applied migration file, because the checksum guard rejects it.
- **`error: compose` with a 403 from GHCR**: `GHCR_PULL_PAT` expired. Rotate it per `disaster-recovery.md` §Secrets, update the secret in the `prod` environment, and release again: the apply writes new registry auth through the agent (no VM replacement).
- **Deploy succeeded but DNS still points elsewhere**: `terraform output prod_host_ipv4` vs `dig +short budget-planner-prod`. If they diverge, DNS was manually edited; reconcile via Terraform.

## Rollback

- Auto-rollback is built into the release job: a host failure re-applies the previous ref in the same approved run.
- Manual rollback (last known-good SHA, e.g. after discovering a prod-only bug minutes after a green deploy): see [`rollback.md`](rollback.md). Shape: `gh workflow run rollback.yml --ref main -f env=prod` (optionally `-f target=vX.Y.Z`).

## Rotate the Litestream API key (yearly, before expires_at)

Scaleway gives `scaleway_iam_api_key.app` a 1-year expiry (T-D74, ADR-0092). Terraform ignores that attribute; `key-expiry.yml` warns 30 days ahead. After expiry Litestream replication fails and backups stop. The key lives in `terraform/bootstrap/ci` (`module.app_<env>`, ADR-0104).

1. Read the date: `terraform -chdir=terraform/bootstrap/ci output app_key_expires_at`. Rotate at least 30 days before it (checklist F).
2. Replace the key in `bootstrap/ci` with the break-glass key: `terraform -chdir=terraform/bootstrap/ci apply -replace='module.app_<env>.scaleway_iam_api_key.app'`. Run it only with explicit user go, under [`break-glass.md`](break-glass.md), and log it in `docs/CHANGELOG.md`. Then update `APP_SCW_ACCESS_KEY` / `APP_SCW_SECRET_KEY` in the env's GitHub environments (`prod` + `prod-plan`, or the three drill ones) from outputs `app_<env>_access_key` / `app_<env>_secret_key`.
3. Impact: the key is rendered into `bp-config` (`/etc/budget-planner/litestream.env` and the compose environment). The next env-stack apply (a release, or `rollback.yml`/a re-run of the last release) shows an in-place `user_data` update; the agent rewrites the files and restarts `litestream` and `app`. Read the plan first. If it says the server is replaced, stop: that recreates the VM and takes the restore path (see `disaster-recovery.md`). Always read the plan through `just tf-plan-safe <env>` or `| python3 terraform/scripts/mask_plan.py`.
4. Wait for the status file to report the new generation (the apply job does this for prod).
5. Verify: `docker compose logs --tail=50 litestream` shows no auth errors, and a fresh Litestream snapshot or generation appears in the bucket.
6. Check `app_key_expires_at` is about one year ahead. Replace deletes the old key immediately, so there is no overlap window. Do steps 2 to 4 in one sitting; replication is paused only for that gap.

## Terraform plans and host state changes (T-D83, ADR-0098, ADR-0111)

- `user_data` embeds secrets and is marked sensitive. Run plans via `just tf-plan-safe drill|prod`, or pipe through `python3 terraform/scripts/mask_plan.py`. CI already does.
- `bp-config` and `bp-agent` changes are applied live: the provider rewrites the metadata in place and the agent converges within ~30 s. No reboot, no SSH.
- The `cloud-init` key still runs once. A change there (users, Tailscale, firewall, the agent loader and timer) plans as an in-place update but does nothing on the running VM until the server is replaced (`-replace=module.compute.scaleway_instance_server.app`). That is not a pipeline action: explicit user go, under [`break-glass.md`](break-glass.md). It recreates the VM; data restores from Litestream (see `disaster-recovery.md`).

## Releases that replace the VM (T-D156, ADR-0127)

A plan that replaces `module.compute.scaleway_instance_server.app` (instance type, image, zone or root volume change, e.g. ADR-0118) recreates the host and restores the database from Litestream. Read the plan; the replacement also shows a new `tailscale_tailnet_key.vm` (its description carries the VM spec hash).

Before cutting the release: a green `replace-rehearsal.yml` run on the release commit (`drill.md`, "Replacement rehearsal"; ADR-0127 §7).

Before approving the prod apply:

0. The host runs the drain-capable agent: `curl -fsS https://<host>/.well-known/bp-deploy-status.json | jq 'has("drain")'` prints `true`. If it prints `false`, release the agent in place first (ADR-0127 amendment 2, T-D158); the job checks this too and fails before the apply.
1. Litestream is current: `docker compose logs --tail=50 litestream` shows recent `write wal segment` lines and no errors.
2. Record the counts on the old host:
   `ssh operator@budget-planner-prod "sqlite3 /data/budget.db 'SELECT count(*), max(id), max(created_at) FROM audit_log;'"`
3. Expect a few minutes of downtime. Tell users if anyone else is active. The job drains the old host before it replaces it (T-D157, ADR-0127 amendment): `bp-drain` is set, the app stops, the status shows `"state": "drained"`, then the apply runs.

After the apply:

The release job detects the replacement from the plan (`host_release.py replaced`). It then waits up to 30 min, requires `restore.result == "restored"` in the host status, and does not roll the image back on failure. On success `release.yml` runs `tailnet-cleanup-prod`, which removes the old offline node and gives the new node the plain name.

1. `curl -fsS https://<host>/.well-known/bp-deploy-status.json | jq .restore` reports `"result": "restored"` and a generation (the job checked this too). `empty` on prod means the replica was empty and `allow_empty_db` was set; stop and investigate.
2. If the host never comes up, `litestream-restore` may have refused an empty replica ("refusing to start empty"). That is the guard working: check the bucket and credentials. Do not set `allow_empty_db` to get past it.
3. Compare the counts from step 2 on the new host (`restore.md`, Verification). The job drained the old host first, so the counts must match; any missing row is a failed restore or a failed drain.
4. If `tailnet-cleanup-prod` warned: remove the old offline `budget-planner-prod` node in the tailnet admin console, then rename the new node from `budget-planner-prod-1` to `budget-planner-prod`.
5. If the job failed on a replacement, there is no automatic rollback: follow `disaster-recovery.md`.
6. Stuck drain: if the job failed before the apply and the old host still shows `"state": "drained"`, the job's undrain step did not run or failed. Delete the key through the pipeline by re-running the release, or under `break-glass.md` with `python3 scripts/ci/scw_user_data.py delete --server <zone/id>` (it only ever touches `bp-drain`). The agent restarts the app within one 30 s timer run.
