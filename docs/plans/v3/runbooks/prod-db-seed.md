# Runbook: one-time prod DB seed (T-D93)

**One-time exception (d) of ADR-0099.** Copies the operator's local
`data/budget.sqlite` onto the freshly provisioned prod VM, once. Do not use it
for routine data movement; afterwards the prod DB is the source of truth and
litestream (ADR-0034, age-encrypted per ADR-0078) is its backup.

Script: `scripts/prod_db_seed.sh` (via `just prod-db-seed <args>`).

## Preconditions

- Explicit in-session user go-ahead (CLAUDE.md: `data/budget.sqlite` is prod; an agent
  must not run this without it). The script only reads a snapshot of the local DB.
- Prod VM is up: `https://<fqdn>/ready` returns ready; app, litestream, caddy running.
- `ssh operator@budget-planner-prod` works over the tailnet (ADR-0094, `tailscale-ssh.md`),
  and `sudo` is passwordless.
- The VM DB is still the fresh bootstrap one (no accounts/transactions). The script
  aborts otherwise unless `--force-overwrite`.
- Local `sqlite3` is installed. Stop `just dev` against the local DB first, so the
  snapshot is quiescent.

## Steps

1. Dry run (local only: snapshot, integrity, counts, sha256; no network):
   `just prod-db-seed --dry-run`
   Check row counts and the migration version look right. Without `--source` this
   reads `data/budget.sqlite`.
2. Real run:
   `just prod-db-seed --yes-i-own-prod-data`
   Optional: `--host <tailnet-host>`, `--source <path>`, `--fqdn <site-name>`
   (default `budget.rising-dough.eu`; the name Caddy has a certificate for).
   Without the flag the script prints its plan and exits 2.
3. The script then: checks the remote DB is empty, scp's the snapshot to
   `/tmp/seed.db` (0600), verifies sha256 remotely, stops `app` and `litestream`,
   moves `/data/budget.db{,-wal,-shm}` and `.budget.db-litestream` to
   `/data/pre-seed-<ts>/`, installs the seed (uid 10001, 0600), starts litestream
   and app (entrypoint applies pending migrations, ADR-0071), waits for `/ready` (up to 180 s; ready = `https://<fqdn>/ready` pinned to loopback OK, or app container healthy and in-container `/ready` OK),
   and prints `litestream generations`.

### Bootstrap admin (ADR-0061, ADR-0069)

On first start the app runs `bootstrap_admin` against the seeded DB:

- Seed already has a live admin: no-op; log in with the existing credentials.
- Seed has no admin (typical for a v1/v2 local DB): the legacy owner user (id 1,
  owns the accounts) is promoted to admin and its email/password are set from
  `BUDGET_PLANNER_ADMIN_EMAIL` / `BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD`
  (`must_change_password` applies). If a user with that email already exists it is
  promoted instead. So your data stays attached to the admin account; no second
  empty admin is created.

## Verification

- Script ended with `/ready: ready` and a litestream generations listing with a new
  generation (re-run `sudo docker exec budget-planner-litestream litestream
  generations -config /etc/litestream.yml /data/budget.db` after a minute if empty).
- Log in at the prod URL; spot-check account balances and recent transactions
  against local.
- Later: the restore drill (`restore.md`) proves the replica restores the seeded data.

## Rollback

- Automatic: any failure after the stop restores the moved-aside files and restarts
  services (seed copy discarded).
- Manual, after a successful swap you want to undo:
  `ssh operator@<host>`, then `cd /etc/budget-planner && sudo docker compose stop app litestream`,
  remove `/data/budget.db*` and `/data/.budget.db-litestream`, move the contents of
  `/data/pre-seed-<ts>/` back to `/data/`, `sudo docker compose up -d litestream app`.
  The litestream replica will then contain a generation from the seeded DB too;
  that is harmless (restores use the latest generation).

## Cleanup

After verification only: `ssh operator@<host> sudo rm -rf /data/pre-seed-<ts>`
(the script prints the exact path). The local snapshot is removed automatically on
exit; `/tmp/seed.db` on the VM is moved into place or deleted. Record the seed in
`restore-log.md` if desired.

## Known issue fixed in T-D94

The first real run (2026-11-07) rolled back although the app was healthy: the
readiness probe used `https://localhost/ready`, but Caddy only has a certificate
for the site FQDN, so the TLS handshake with SNI `localhost` failed (`-k` does not
help). The probe now uses `--resolve <fqdn>:443:127.0.0.1` against the real FQDN
(`--fqdn`), with the container health plus in-container `/ready` as a second signal.
