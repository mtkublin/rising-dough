# Runbook — Disaster Recovery

Full re-provision from zero plus restore. Target end-to-end RTO: < 60 min (ADR-0032 §9).

## Context

Use this runbook when the production Scaleway Stardust VM is **gone** or must be considered compromised: Scaleway destroyed the instance, the operator ran `terraform destroy`, the disk is unrecoverable, or an intrusion means the host cannot be trusted. The DB itself lives in `s3://budget-planner-prod-pl-waw/db/` and is independent of the compute instance — Litestream makes the VM disposable (ADR-0034).

The recovery path is: `terraform apply` from the committed state → cloud-init renders the compose stack → Litestream restores `/data/budget.db` from the bucket on first boot → the app comes up on `/ready`.

This runbook also covers the "lost all admins" scenario (ADR-0061 §3): the DB is fine but no `is_admin = 1 AND deleted_at IS NULL` row exists. The admin-bootstrap routine re-promotes a user when provided a new email + initial password via Terraform.

Uptime monitor id (T-D44): record below once the monitor is created.

```
UptimeRobot monitor id: <TBD — fill in once T-D44 lands>
Betterstack heartbeat url: <TBD>
```

## Preconditions

- Local workstation has `terraform`, `ssh`, `scw` CLI, and `gh` installed.
- You have the Scaleway API credential pair with permissions to recreate the project resources (admin or project-admin IAM key, kept in the operator's password manager — distinct from the Litestream key).
- You have the **Litestream age identity** (`AGE-SECRET-KEY-1...`, from the password manager) and its `age1...` recipient. They are Terraform inputs (`litestream_age_identity`, `litestream_age_recipient`); cloud-init writes the identity to `/etc/budget-planner/litestream-age.key` (0600) and the `litestream-restore` service uses it to decrypt the replica (T-D56, ADR-0078 §3). **If the identity is lost, the replica is unrecoverable: there is no other copy of the key and no way around the encryption.**
- The Terraform state is reachable:
  - Primary: `s3://budget-planner-tfstate-pl-waw` (encrypted, versioned).
  - If the state bucket is also gone: use the latest state file snapshot the operator keeps offline. If none exists, see Troubleshooting ("state bucket also lost").
- The `main` branch of the repo is intact and the latest green image tag is present in GHCR (`ghcr.io/<owner>/budget-planner:sha-<short>`).
- You have the GHCR PAT (`GHCR_PAT`) and the deploy SSH key (`DEPLOY_SSH_PRIVATE_KEY`) stored in the operator's password manager — the GitHub Actions encrypted copies are useful too but assume we may be rebuilding without GHA access first.
- DNS zone for `<prod-host>` is still reachable (zone itself is managed by Terraform; records will be rewritten).

## Procedure

### 1. Decide the recovery point

- **Normal DR** (host lost, data intact): restore latest from Litestream.
- **Compromise suspected**: pick a point-in-time **before** the earliest sign of compromise. Record the chosen UTC timestamp.
- **Lost all admins only** (VM still fine): skip to §5.

### 2. Re-provision the VM via Terraform

```sh
cd terraform
terraform init -upgrade
terraform workspace select prod   # must already exist in state
terraform apply -var-file=envs/prod/terraform.tfvars
```

Terraform recreates:

- Scaleway project resources (IAM app for Litestream, security group, Flex IPv4).
- Stardust1-S instance in `pl-waw-2` (or the zone set in tfvars, ADR-0084) with cloud-init user-data.
- DNS A/AAAA records pointing `<prod-host>` at the new IP.
- `/etc/budget-planner/docker-compose.yml`, `/etc/litestream.yml`, Caddyfile, deploy user, `/usr/local/bin/deploy-budget-planner`.

Cloud-init boot sequence will:

1. Install docker + fail2ban + ufw.
2. Pull the pinned image tag.
3. `docker compose up -d` runs the one-shot `litestream-restore` service first (ADR-0071 §3): `litestream restore -if-db-not-exists -if-replica-exists` restores the latest replica into the empty `/data/budget.db` and chowns it to uid 10001. For a point-in-time recovery, do **not** rely on this: stop the stack after first boot and follow [`restore.md`](restore.md) with `-timestamp`.
4. Start `litestream` (replicator), then `app`, then `caddy`. The `app` and `litestream` services wait until `litestream-restore` has completed successfully.
5. The app container entrypoint applies any migrations the restored DB is missing. If the DB already has migrations applied, it first writes a pre-migration backup to `/data/backups/` (ADR-0071 §2).
6. The lifespan admin-bootstrap routine (ADR-0061 §3) runs with `BUDGET_PLANNER_ADMIN_EMAIL` + `BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD` from env. If the restored DB already has a live admin, this step does nothing.

Capture outputs:

```sh
terraform output -raw prod_host_ipv4
terraform output -raw admin_initial_password   # sensitive; sinks straight into a password manager
```

### 3. Wait for ACME + wire DNS

Caddy obtains a Let's Encrypt cert via HTTP-01 on first boot. First-boot cert issuance takes 30–90 s. If this is the first-ever provision for the hostname (DNS A record not propagated yet), expect up to 5 min while DNS converges.

```sh
dig +short <prod-host>   # must match terraform output prod_host_ipv4
curl -fsSI "https://<prod-host>/" | head -5   # 200 or 302 means Caddy + app are up
```

### 4. Verify the restored DB

```sh
ssh app@<prod-host> "sqlite3 /data/budget.db 'PRAGMA integrity_check;'"
# Expect: ok

ssh app@<prod-host> \
  "sqlite3 /data/budget.db 'SELECT count(*), max(id), max(created_at) FROM audit_log;'"
# Compare against the last known-good count from the previous week's drill
# (restore-log.md). Deltas should match the write rate up to the recovery point.

curl -fsS "https://<prod-host>/ready" | jq .
# Expect: {"status":"ok","db":"ok","litestream":"ok", ...}
```

Confirm Litestream is replicating back **to the same bucket** — if the bucket is the one we restored from, we are now writing a new generation into it (expected).

```sh
ssh app@<prod-host> \
  "docker compose -f /etc/budget-planner/docker-compose.yml logs litestream --tail 30"
# Expect "generation ..." + "write wal segment ..." lines within 30 s.
```

### 5. Lost-all-admins recovery (sub-flow)

Trigger only if the DB has zero live admins (ADR-0061 §3). The admin-bootstrap routine runs on every app start and re-promotes a user when told who it is.

1. Set / rotate the admin env vars in Terraform:
   ```hcl
   # envs/prod/terraform.tfvars
   admin_email = "<new-or-recovered-admin-email>"
   # No static password: random_password.admin_initial_password rerolls on apply.
   ```
2. `terraform apply -var-file=envs/prod/terraform.tfvars`.
3. Cloud-init re-renders `/etc/budget-planner/app.env` with the new `BUDGET_PLANNER_ADMIN_EMAIL` + fresh `BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD`.
4. `ssh deploy@<prod-host> "deploy sha-<current>"` (or trigger `deploy.yml` to roll the app container so the lifespan startup hook re-runs the bootstrap routine).
5. Capture `terraform output -raw admin_initial_password` into the password manager.
6. Log in as the new admin at `https://<prod-host>/auth/login`. The first login forces password rotation (`must_change_password = 1`).
7. Audit: `/debug/audit-tail` shows a `users.create` or `users.update` row with `actor='system-bootstrap'`.

**Note (ADR-0061 §3)**: the env var is read only at bootstrap. Rotating it without a redeploy is a no-op. The random password is regenerated by Terraform on each apply **only if** the `random_password` resource is replaced (its lifecycle keeps it stable otherwise); force it with `terraform apply -replace=random_password.admin_initial_password`.

### 6. Resume monitoring + close the loop

- Confirm the uptime monitor (T-D44) is green again.
- Confirm Scaleway cost alert (T-D45) is still armed.
- Append an entry to [`restore-log.md`](restore-log.md) with `env=prod-rebuild`, duration, and the recovery point used.
- Rotate `GHCR_PAT` and the Litestream IAM key if compromise was the trigger. See §Secrets.

## Verification (end-to-end)

```sh
# App healthy on prod hostname.
curl -fsS "https://<prod-host>/ready"

# TLS cert is from Let's Encrypt and valid for ≥ 60 days.
echo | openssl s_client -connect "<prod-host>:443" -servername "<prod-host>" 2>/dev/null \
  | openssl x509 -noout -dates -issuer

# DB integrity + audit log tail.
ssh app@<prod-host> "sqlite3 /data/budget.db 'PRAGMA integrity_check;'"
ssh app@<prod-host> \
  "sqlite3 /data/budget.db 'SELECT id, entity_type, operation, actor_user_id, created_at FROM audit_log ORDER BY id DESC LIMIT 10;'"

# Litestream writing new WAL segments.
ssh app@<prod-host> \
  "docker compose -f /etc/budget-planner/docker-compose.yml logs litestream --since 2m | grep -c 'write wal segment'"
# Expect: non-zero.

# Admin login works and admin surface is reachable.
# (manual browser step)
```

## Troubleshooting

- **Terraform plan fails with "resource already exists"**: previous `terraform destroy` was partial. Import the stray resource or delete it via `scw` CLI before re-applying.
- **State bucket also lost**: restore state from the latest offline snapshot (`terraform-state-YYYYMMDD.tar.gz` in the operator's encrypted backup). If no snapshot exists, re-adopt resources by writing `import` blocks against the live Scaleway resources before applying — slow (hours), but recoverable.
- **Caddy fails ACME challenge during cloud-init**: port 80 blocked by security group or DNS not yet resolving. Check `scw instance server list`, confirm security group allows `80/tcp`, confirm `dig +short <prod-host>` returns the new IPv4.
- **App came up with an empty DB instead of the restored data**: `litestream-restore` found no replica (wrong bucket / credential) and exited 0 under `-if-replica-exists`, so the entrypoint migrated a fresh DB. Check `docker compose logs litestream-restore`. Then stop `app` + `litestream`, move `/data/budget.db*` aside, fix the credential and run the restore manually per [`restore.md`](restore.md).
- **Restore fails with an age / "no identity matched" error**: the identity supplied to Terraform does not match the recipient the replica was encrypted to. Check `age-keygen -y <identity file>` against the `age1...` recipient in `litestream.yml`, fix the variable and re-run the restore manually per [`restore.md`](restore.md).
- **Litestream restore returns "no snapshots found"**: the IAM key cloud-init rendered cannot read the bucket. SSH as `app`, re-source the credential, and run the restore manually (see [`restore.md`](restore.md) steps 5–7).
- **Admin bootstrap did not run**: check `docker compose logs app --tail 100` for the `system-bootstrap` audit entry. If missing, the lifespan hook short-circuited because at least one admin was found. Confirm with `SELECT count(*) FROM users WHERE is_admin=1 AND deleted_at IS NULL;`.
- **New admin email never arrives at login**: ADR-0061 §3 — the env var is read only at startup. Re-run `deploy.yml` (or `docker compose restart app`) after Terraform apply.
- **Deploy pipeline cannot push images after DR**: `GHCR_PAT` or `DEPLOY_SSH_PRIVATE_KEY` was rotated as part of recovery and GitHub Actions secrets still hold the old value. Update the GHA secrets and re-run.

## Secrets rotation checklist (when DR was triggered by suspected compromise)

- [ ] Rotate `SCW_ACCESS_KEY` + `SCW_SECRET_KEY` (Litestream IAM app — bucket-scoped only).
- [ ] Rotate `GHCR_PAT`.
- [ ] Rotate `DEPLOY_SSH_PRIVATE_KEY` (and update `authorized_keys` on the new host via Terraform cloud-init).
- [ ] Rotate the operator SSH key for the `app` user if the previous host was reachable.
- [ ] Rotate the admin password (force via `terraform apply -replace=random_password.admin_initial_password`).
- [ ] Rotate Scaleway project-admin API key the operator uses for Terraform.
- [ ] Confirm bucket versioning kept pre-compromise versions reachable; export them before changing bucket policy if forensic is needed.

## Rollback

DR is itself a rollback. If the re-provisioned host is worse than the broken host it replaced (and the broken host is still reachable), do not destroy anything; keep the broken host for forensic + flip DNS back manually via `scw dns record update`. Open an incident ticket and escalate the decision instead of iterating on `terraform apply`.
