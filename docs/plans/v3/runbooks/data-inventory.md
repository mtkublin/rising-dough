# Runbook: data inventory and what the operator can see (T-D61, ADR-0078 §8)

**Context.** One list of every place user data or secrets live in v3, with protection, retention and who can read it. The last section is the plain statement of what the operator can technically see. Share that section with users. v4 (ADR-0079..0083) improves on this baseline; do not read it as a v4 promise.

"Operator" here means the single maintainer: root on the prod VM (via Tailscale SSH and the `operator` user with passwordless sudo), Scaleway organization admin, GitHub repository admin.

**Verified against the repo on 2026-11-16.** Where a row says "not verified", the repo does not show the fact and it must be checked on the real system. Re-run this review when any of these change: the compose or cloud-init templates, `terraform/modules/compute/user_data.tf`, the bucket policies, or the retention settings.

## 1. Ceilings that apply to everything below

| Setting | Value | Where |
|---|---|---|
| Maximum age of any copy of user data outside the live DB | 37 days (`backup_max_age_days`) | ADR-0078 §4, `docs/requirements.md` §6.5 |
| IP / user-agent retention | 90 days (`retention_personal_days`) | `src/budget_planner/services/retention.py` |
| Session lifetime | 14 days sliding, 30 days absolute | `config.py` (`session_lifetime_days`, `session_absolute_lifetime_days`) |

## 2. User data

| # | Location | Holds | Protection | Retention / expiry | Who can read |
|---|---|---|---|---|---|
| U1 | Live DB `/data/budget.db`, plus `-wal` and `-shm`, on the VM block volume (bind-mounted into the app container) | Everything: accounts, transactions, categories, plans, preferences, `users` incl. email and password hash, `audit_log`, `sessions`, `webauthn_credentials`, `auth_rate_limit` | Directory `/data` is `0700` uid 10001; app container is non-root and read-only except `/data`. `PRAGMA secure_delete = ON` zeroes deleted content (`db/connection.py`). **No application-level encryption.** Disk encryption at rest by the provider: not verified, not configured by us. TLS terminates at Caddy; Caddy to app is plain HTTP on the private Docker bridge. The 1 GiB swapfile on the VM is not encrypted by us and can hold process memory. | Until the user's data is deleted. Soft-deleted rows stay (ADR-0019). | App process; root on the VM (including the operator). Not other users (ADR-0061 authorization) |
| U2 | `/data/backups/budget.db.pre-migrate-*` (`VACUUM INTO` before a migration) | Full DB copy, plaintext | Same directory and modes as U1 | Pruned on every start: newest 3 **and** younger than 30 days (`backup_max_age_days - 7`) | Root; app uid |
| U3 | Litestream metadata `/data/.budget.db-litestream` | Replication position only (no row data) | As U1 | Managed by Litestream | Root |
| U4 | Litestream replica in Scaleway Object Storage (prod bucket, prefix `db/`) | Snapshots and WAL of U1. New generations are **age-encrypted** client-side (recipient set in `litestream.yml`); Litestream is pinned to 0.3.14 because 0.5.x has no age support (ADR-0078 §3 addendum) | age ciphertext plus provider SSE. Bucket policy is allow-list only (ADR-0091, ADR-0105): prod app application, operator, restore-reader (read-only), CI plan identity (metadata only, no objects). Bucket versioning on. **Status: T-D56 is code-complete; the cut-over to an encrypted generation is still pending (`tasks.md` marks it open).** Until `restore.md` "Cut-over to an encrypted replica" is done and the old generations are deleted, plaintext generations can still exist in the bucket. | `retention: 720h` (30 d) plus noncurrent-version expiry 7 d: worst case 37 d | Holders of the Litestream app key, the restore-reader key, or operator/org-admin credentials can fetch the objects. Reading content also needs the age identity (S3), except for plaintext generations |
| U5 | Copies on the drill host (`restore-from-prod`, restore drill): moved-aside DB, restored DB, pre-migration backups | Restored copy of prod data | Drill host is tailnet-only, no public 80/443 (ADR-0101). The helper deletes moved-aside copies and pre-migration backups on exit, success or failure (T-D57). The drill environment is destroyed after each run. | Minutes to the drill TTL (default 60 min), then VM destroy | Operator via tailnet SSH. The drill host holds the prod age identity and a read-only prod replica key (S3, S6) |
| U6 | `/data/pre-seed-<ts>/` on the prod VM | Moved-aside DB from the one-time seed ([`prod-db-seed.md`](prod-db-seed.md), done 2026-11-07) | As U1 | The runbook says delete after verification. Not verified that it was deleted: check `ls /data` on the host | Root |
| U7 | App container logs (structlog JSON to stdout, Docker `journald` driver) and host journald | Request id, path, status, event names. Value-bearing keys (`amount*`, `description`, `name`, `note*`, `memo`, `formula`, `q`, `search`, `email`, `password*`, `token*`, `secret*`, `*_json`) are redacted; the uvicorn access log drops query strings (T-D59) | Redaction is by key name only. A user value inside a free-text message is not caught. Journal retention: journald defaults, not set by the repo (not verified) | Journald defaults; not bounded by the 37 d ceiling by configuration | Root, members of `systemd-journal` |
| U8 | Caddy access log `/var/log/caddy/access.log` (host dir `0755`) | Method, path (query stripped), status, timing, client IP, user agent. `Cookie`, `Authorization` and `Set-Cookie` headers are deleted | Directory is world-readable on the host, but only root and the operator account exist on the VM | Caddy rolls at 20 MiB and keeps at most 7 files / 168 h. `logrotate` runs daily with 14 generations (`copytruncate`). The effective ceiling is 14 days; the shorter Caddy rule usually wins for rolled files | Any local user on the VM; root |
| U9 | `audit_log` table (inside U1, U2, U4) | Create/update/delete history with `prev_json` / `new_json` (financial values, names), actor, `ip`, `user_agent` | As U1. `/debug/audit-tail` is admin-only and shows another user's payloads as `[other-user]` (T-D54) | Rows are never deleted (ADR-0019). `ip` and `user_agent` are nulled after 90 days (T-D60) | App; root; the admin sees metadata of all rows, payloads of own rows only |
| U10 | `sessions` table (inside U1) | Session id stored as `sha256(token)` (not the cookie value), user id, timestamps, `ip`, `user_agent` | Hashed ids: a leaked DB or backup holds no usable cookie | Ended rows (expired or revoked) deleted after 90 days; live rows kept until they end | App; root |
| U11 | `users.password_hash` and `webauthn_credentials` (public key, credential id, sign count, label), inside U1 | Password hashes and passkey public keys | Hashes only, never the password. Public keys are not secrets | Until the user is removed (soft delete) | App; root |
| U12 | Browser: session cookie, CSRF cookie, HTTP cache | Session cookie and pages the user viewed | Cookies are signed with the cookie secret (S1). Every authenticated response is `Cache-Control: no-store`. Logout sends `Clear-Site-Data: "cache", "storage"` (T-D55); the session cookie is expired by logout itself | Cookie lifetime per section 1 | The user's device |
| U13 | Operator laptop: `data/budget.sqlite` (canonical local copy), `data/backups/` | Full real data, plaintext | Gitignored. Disk encryption on the laptop is assumed, not verifiable from the repo. Rule: never used by agents or tests (CLAUDE.md) | Until the operator deletes it. **Not covered by the 37 d ceiling.** ADR-0078 forbids ad-hoc copies outside runbooks, but this canonical local copy exists by design | Operator; anyone with the unlocked laptop |
| U14 | Operator laptop and git: `data/demo.sqlite` | Anonymized, scaled copy built by `just demo-build` | Tracked in git. Anonymized by `data/scripts/build_demo_db.py` | Kept in git history | Anyone with repo access |
| U15 | GHCR images | Application code only. No user data and no secrets baked in | Pull needs a `read:packages` PAT (S5). Images are cosign-verified on the host (ADR-0111) | Newest 20 `sha-*` tags kept ([`image-retention.md`](image-retention.md)) | Per repo visibility |

## 3. Secrets

The prod VM receives all of its secrets through Scaleway instance metadata. Terraform renders them into the `user_data` map (ADR-0111): `cloud-init`, `bp-agent`, `bp-config`. The values are wrapped in `sensitive()` in Terraform output, but they are plaintext in the metadata service and in Terraform state.

| # | Secret | Where it lives | Protection | Retention / rotation | Who can read |
|---|---|---|---|---|---|
| S1 | App cookie secret (`BUDGET_COOKIE_SECRET`); admin email and initial admin password (`BUDGET_PLANNER_ADMIN_*`) | `bp-config` -> `/etc/budget-planner/docker-compose.yml` (`0600` root); container environment (`docker inspect` shows it to root); Terraform state | File `0600`. Containers cannot reach the metadata API: the `DOCKER-USER` rule from `bp-metadata-guard.service` drops container traffic to `169.254.42.42` (ADR-0111 §6) | Cookie secret: until rotated (rotation signs everyone out). The initial admin password matters only until first login | Root on VM; metadata readers (S11); state readers |
| S2 | Litestream / app Scaleway API key (`SCW_ACCESS_KEY`, `SCW_SECRET_KEY`) | `bp-config` -> `/etc/budget-planner/litestream.env` (`0600`) and the compose file (`0600`); `cloud-init` metadata key (boot-time use); Terraform state; GitHub `APP_SCW_*` secrets | As S1. IAM scope: object storage of the env's bucket only (ADR-0092) | 1 year, [`key-rotation.md`](key-rotation.md) and `deploy.md` | Root on VM; metadata; state readers; GitHub environment admins |
| S3 | Litestream age **identity** (private key) | `bp-config` -> `/etc/budget-planner/litestream-age.key` (`0600`); Terraform state; the matching GitHub environment secret (see `github-settings.md`); operator password manager (master copy); the drill host receives the prod identity | Mounted read-only into the one-shot restore container only, not into the replicating sidecar | No rotation procedure yet. **Losing it makes encrypted generations unrecoverable** | Root on VM and drill host; state readers; GitHub environment admins; operator |
| S4 | Litestream age recipient (public key) | `litestream.yml`, Terraform variables | Public by design | - | Anyone with config access |
| S5 | GHCR pull PAT (`read:packages`) | `bp-config` -> `/root/.docker/config.json` (`0600`) and the agent's Docker config dir under `/var/lib/budget-planner/docker`; Terraform state; GitHub environment secret `GHCR_PULL_PAT` | Read-only package scope | Per PAT expiry | Root on VM; metadata; state; GitHub |
| S6 | Restore-reader key (read-only on the prod replica) | Drill host only: `/etc/budget-planner/restore-source.env` (`0600`); drill Terraform state; `bootstrap/ci` local state; GitHub drill environment secrets `PROD_REPLICA_RO_*` | Read-only on the prod bucket | 1 year (`key-rotation.md`) | Root on drill host; GitHub drill environment admins; operator |
| S7 | Tailscale single-use auth key (VM join) | `cloud-init` metadata key; `/run/tailscale-authkey` (tmpfs, `0600`) deleted after `tailscale up`; Terraform state | Single use; drill nodes are ephemeral | Consumed at first boot. Still readable from metadata and state until it expires | Metadata readers; state readers |
| S8 | Optional console password hash (`console_password_hash`) | `cloud-init` metadata key; `/etc/shadow` on the VM | Hash only; account is locked unless set for break-glass | Per operator | Root; metadata |
| S9 | Terraform state: prod (`budget-planner-tfstate-pl-waw`, key `prod/`) and drill (`budget-planner-tfstate-drill-pl-waw`, key `drill/`) | Scaleway Object Storage, one bucket per project. Holds **every sensitive input above** (S1..S8) in plaintext, because the compute module's `user_data` and variables are in state. No user data | Private bucket, versioned, allow-list policy (ADR-0091, ADR-0100, ADR-0105). Access is split by environment: the drill CI key gets 403 on the prod bucket. `use_lockfile` | Noncurrent versions expire after 90 days, so old secret values persist up to 90 days after a rotation | Operator/org admin; the CI identity of that environment. The read-only plan identity can read state, which includes secrets |
| S10 | `terraform/bootstrap/terraform.tfstate` (committed) and `terraform/bootstrap/ci/terraform.tfstate` (local, gitignored) | Bootstrap: bucket metadata only, no secrets, committed. `ci`: the **secret keys** of the CI identities, restore-reader and drill app key | `ci` state stays on the operator laptop on an encrypted disk; no off-laptop backup. Losing it breaks nothing (`key-rotation.md`) | Until the keys are rotated | Anyone with the operator's laptop session |
| S11 | Instance metadata service (`cloud-init`, `bp-agent`, `bp-config`) | Scaleway, reachable at `169.254.42.42` from the VM | Served on a privileged source port to root only; blocked from containers by `bp-metadata-guard`. Also readable through the Scaleway API by IAM members with instance read access on the project | Replaced on every apply | Root on VM; Scaleway org admin and project IAM members |
| S12 | Agent state `/var/lib/budget-planner` (`status.json`, `failure.json`, applied generation) | Generation hash, image refs, state, terse error code. Caddy serves `status.json` publicly at `/.well-known/bp-deploy-status.json` | No secrets and no paths by design (`bp_agent.build_status`) | Overwritten each run | Public (status only); root |
| S13 | GitHub environment secrets (`prod`, `prod-plan`, `drill`, `drill-teardown`, `drill-plan`) | See [`github-settings.md`](github-settings.md) section 2: CI Scaleway keys, app keys, age identity and recipient, GHCR PAT, Tailscale OAuth, `ADMIN_EMAIL`, SSH keys | Per environment, least privilege (ADR-0100). `prod` requires reviewer approval; `prod-plan` holds the read-only key | Per key; `key-rotation.md` cadence | GitHub repo/org admin (can exfiltrate by editing a workflow on an allowed branch); workflow runs of that environment |
| S14 | Operator password manager | Org-admin break-glass key, age identity (master copy), Tailscale and GitHub credentials | Operator's own vault | Yearly for the break-glass key | Operator |
| S15 | Operator laptop `terraform/.env` | Operator Scaleway key for bootstrap work only. `key-rotation.md` says it keeps no prod-write key | Gitignored | Per rotation | Operator |
| S16 | Drill boot-log uploads (`boot-logs/` in the drill bucket, drill only) | cloud-init log, journal, dmesg. Redacted for `tskey-`, age keys and `*PASSWORD/SECRET/TOKEN/_KEY` patterns; **not** for other free text | Drill bucket, same allow-list policy | Expire after 7 days (versions after 1 day) | Operator; drill bucket principals |
| S17 | Committed `terraform/envs/prod/terraform.tfvars.bak` | Operator input values: project and organization ids, admin email, public keys, principal ids. No secret values (its header says secrets go through env vars) | Tracked in git although its header says gitignored | In git history | Anyone with repo access |

## 4. What the operator can technically see in v3

Plain statement, no softening.

- **Everything in the database.** With root on the VM (Tailscale SSH, `operator` user, passwordless sudo) the operator can open `/data/budget.db` or its copies and read every user's accounts, transactions, descriptions, balances, email addresses, audit history, IP addresses and user agents. SQLite is not encrypted. The ADR-0061 isolation protects users from each other and from the admin web UI (T-D54), not from the person with host access.
- **Everything the app handles in transit through the host.** Caddy terminates TLS on the host, so plaintext requests, including passwords at login, pass through processes the operator controls. The operator can change the deployed image or config with one approved `terraform apply`, so a malicious or mistaken release could capture data. Cosign verification proves the image came from this repo's `build.yml`, not that the code is harmless.
- **Every host secret.** Root on the VM, the Scaleway console/API (instance metadata), Terraform state and GitHub environment secrets each expose the cookie secret, the Scaleway object-storage key, the age identity and the registry token. With the cookie secret the operator can forge a valid session cookie; with the age identity plus the Litestream or restore-reader key the operator can decrypt the backups.
- **Backups.** Someone holding only a bucket credential sees ciphertext once the encrypted generation exists (T-D56 cut-over). The operator holds the identity, so the age layer hides nothing from the operator. Until the cut-over is complete, older plaintext generations may exist for up to 37 days.
- **Logs.** The operator can read the redacted app logs, the Caddy access log (paths, status, client IP, user agent) and journald. These do not contain query strings, cookies or amounts by design, but they show who was active and when.
- **What the admin UI hides.** The admin UI shows other users' audit metadata only, never their payloads. Role changes, password resets and removals are audited ([`user-admin.md`](user-admin.md)). Host access bypasses all app-level audit.
- **Third parties.** Scaleway, as infrastructure provider, can in principle read the VM disk, memory and bucket contents; the replica is protected from it only by the age layer. GitHub holds secrets and code; it never receives user data.

What v3 does not promise: that the operator cannot read user data, that deleted data is gone from every copy before 37 days, or that logs never contain a user value. v4 (ADR-0079..0083) is where the first of those is addressed.

## 5. Verification

Run quarterly, and after any change to the locations above. Record the date at the bottom.

1. On the VM: `sudo ls -l /etc/budget-planner /data /data/backups /var/log/caddy`. Secret files are `0600`, `/data` is `0700`. No `/data/pre-seed-*` or other ad-hoc copy remains.
2. On the VM: `sudo iptables -S DOCKER-USER | grep 169.254.42.42` shows a DROP rule, and `sudo docker exec budget-planner-caddy wget -qO- -T 3 http://169.254.42.42/` fails.
3. Confirm the purge ran: `sudo journalctl --since "2 days ago" | grep retention_purge` shows counts only.
4. Bucket: list `s3://<bucket>/db/` and confirm objects of the current generation begin with `age-encryption.org/v1`; once the cut-over is complete, confirm no plaintext generation remains. Confirm the lifecycle rule is 7 days and the policy lists only the principals from `github-settings.md`.
5. Compare section 4 with reality; update this file when a statement stops being true.

## 6. Open items found while writing this

- T-D56 cut-over to the encrypted generation is not done (`tasks.md` shows it as partial): plaintext generations may still sit in the prod bucket.
- The age identity has no rotation or escrow procedure beyond the password-manager copy.
- Local `data/budget.sqlite` on the laptop is outside the 37 d ceiling; say so in `requirements.md` §6.5 or remove the copy.
- Journald retention is unset, and the Caddy and logrotate rules disagree (7 files / 168 h vs 14 days). Pick one number.
- Terraform state holds plaintext secrets and its plan identity can read them (accepted in ADR-0078 §3; revisit in v4).
- `terraform/envs/prod/terraform.tfvars.bak` is tracked in git although its header says gitignored.

## Rollback

Docs only. Revert the commit.

Last reviewed: 2026-11-16.
