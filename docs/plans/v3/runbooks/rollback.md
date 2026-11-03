# Runbook — Rollback

Revert production to the previously running image tag.

## Context

Every successful deploy records the previous image tag to `/etc/budget-planner/.previous-tag` on the host before swapping (ADR-0037 §3). Rollback is a single command that re-applies that tag. Image layers for the previous SHA are kept both in the host's Docker cache and indefinitely in GHCR (untagged after a few deploys, but reachable by digest).

Rollback is the right move for prod-only regressions — the symptom appeared after a deploy and the previous SHA is known-good. For data corruption or restore-from-backup needs, use [`restore.md`](restore.md) instead. A rollback does **not** undo schema changes.

### Schema policy (ADR-0071 §4)

The image entrypoint applies pending migrations on every start. Rolling back starts the **older** image against the **newer** schema. The older image's runner finds nothing to apply. It logs `schema_ahead_of_image` with the versions it does not know and starts anyway. This only works because every migration must be **N-1 compatible** (expand-only: new tables, nullable/defaulted columns, indexes; no drops or renames in the same release that stops using them).

If the release you are leaving is flagged **"rollback requires restore"** in `docs/CHANGELOG.md`, `rollback` alone is not enough. Follow [`restore.md`](restore.md) § "Restore from the pre-migration backup" (or Litestream PITR to just before the deploy), **then** roll back the image. Writes made after the deploy are lost on that path.

## Preconditions

- A previous image tag exists on the host:
  ```sh
  ssh app@<prod-host> "cat /etc/budget-planner/.previous-tag"
  # Expect: non-empty, matches ^sha-[0-9a-f]{7,40}$ or ^v[0-9]+\.[0-9]+\.[0-9]+$
  ```
- The current situation is a code regression, not a data regression. If you are rolling back **because** of DB state, stop here and open `restore.md`.
- Operator has either GitHub Actions `prod` approval rights (preferred path) or SSH access as `app`/`deploy` (fallback path).

## Procedure

### Primary path — manual GitHub Actions dispatch

1. `gh workflow run rollback.yml` (no inputs — uses `.previous-tag`).
2. Approve the `prod` environment when it parks.
3. GHA step summary reports the SHA it reverted to.

### Fallback path — direct SSH (operator workstation)

Use when GitHub Actions is itself the problem (outage, token lockout, workflow mis-wired).

1. Confirm the previous tag:
   ```sh
   ssh app@<prod-host> "cat /etc/budget-planner/.previous-tag"
   ```
2. Invoke the restricted deploy shim via the `deploy` user:
   ```sh
   ssh deploy@<prod-host> "rollback"
   ```
3. The shim runs `TAG="$(cat .previous-tag)" docker compose up -d app`.

### Last-resort path — pin a specific older SHA

If `.previous-tag` is empty (first deploy ever, or someone wiped it), redeploy a known-good SHA explicitly through `deploy.yml`:

```sh
gh workflow run deploy.yml -f sha=<known-good-short-sha>
```

Only use a SHA you can see in `git log origin/main` and that was in `prod` previously (GHCR tag `sha-<short>` still exists).

## Verification

```sh
# App serves and reports ready.
curl -fsS "https://<prod-host>/ready" | jq .

# Running revision matches the rollback target.
ssh app@<prod-host> \
  "docker inspect --format='{{index .Config.Labels \"org.opencontainers.image.revision\"}}' budget-planner-app-1"

# Older image tolerated the newer schema (expected after a migrating release).
ssh app@<prod-host> "docker logs budget-planner-app 2>&1 | grep -E 'schema_ahead_of_image|startup_migrations' | tail -2"

# Audit log is intact — rollback does not touch the DB.
ssh app@<prod-host> \
  "sqlite3 /data/budget.db 'SELECT count(*), max(id) FROM audit_log;'"
```

Spot-check the user-facing symptom that triggered the rollback. If it still reproduces on the previous tag, you were rolling back the wrong thing — see Troubleshooting.

## Troubleshooting

- **`.previous-tag` is empty or missing**: use the "Last-resort path" above with an explicit SHA. After the rollback stabilises, record the recovery in `../phase-4-validation/README.md` so the next deploy writes a fresh `.previous-tag`.
- **`docker compose up -d app` fails on the rollback target**: image was GC'd from the local cache. Pull explicitly: `ssh app@<prod-host> "docker pull ghcr.io/<owner>/budget-planner:sha-<short>"` then retry. GHCR retention is indefinite for private images; the layer should still be fetchable.
- **Rollback target also fails `/ready`**: this is a data-shaped incident, not a code regression. Stop. Switch to [`restore.md`](restore.md).
- **Caddy returns 502 after rollback**: the `app` container restarted on a port other than 8000 (unexpected). `ssh app@<prod-host> "docker compose logs app --tail 100"` and triage from there.

## Rollback (of this rollback)

If the "previous" SHA is itself broken and the current SHA was better than the state we just rolled back to:

1. `gh workflow run deploy.yml -f sha=<current-sha-you-just-left>`.
2. Approve `prod`.
3. Verify `/ready` + the symptom you were originally debugging.
4. Treat the subsequent debugging as a code-only investigation; the DB has not moved.
