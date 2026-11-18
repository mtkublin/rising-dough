# Runbook — Rollback

> **SSH access (ADR-0094):** port 22 is closed to the internet. Join the tailnet (Tailscale app on your machine, see [`tailscale-ssh.md`](tailscale-ssh.md)) and use the MagicDNS names `budget-planner-prod` / `budget-planner-drill-<run id>`. Every host placeholder below means that name.

Revert production to the previously running image tag.

## Context

ADR-0111: Terraform declares the host state. The prod state records two image refs, `app_image_ref` (running) and `app_image_previous_ref` (the one before), both `<tag>@sha256:<digest>`. A rollback is one approved `terraform apply` that swaps them; the host agent cosign-verifies the target image, rewrites the compose file and restarts `app` within ~30 s, and the apply job waits for `/.well-known/bp-deploy-status.json` to report the new generation. A failed release already rolls back automatically inside its own apply job (see [`deploy.md`](deploy.md)); this runbook is for regressions found after a green release.

Rollback is the right move for prod-only regressions — the symptom appeared after a release and the previous image is known-good. For data corruption or restore-from-backup needs, use [`restore.md`](restore.md) instead. A rollback does **not** undo schema changes.

### Schema policy (ADR-0071 §4)

The image entrypoint applies pending migrations on every start. Rolling back starts the **older** image against the **newer** schema. The older image's runner finds nothing to apply. It logs `schema_ahead_of_image` with the versions it does not know and starts anyway. This only works because every migration must be **N-1 compatible** (expand-only: new tables, nullable/defaulted columns, indexes; no drops or renames in the same release that stops using them).

If the release you are leaving is flagged **"rollback requires restore"** in `docs/CHANGELOG.md`, `rollback` alone is not enough. Follow [`restore.md`](restore.md) § "Restore from the pre-migration backup" (or Litestream PITR to just before the deploy), **then** roll back the image. Writes made after the deploy are lost on that path.

## Preconditions

- State records a previous ref (empty only before the second release):
  ```sh
  gh run list --workflow=release.yml --limit=3   # the last green release's apply log prints both refs
  ```
  With the break-glass key: `terraform -chdir=terraform output -raw app_image_previous_ref`.
- The current situation is a code regression, not a data regression. If you are rolling back **because** of DB state, stop here and open `restore.md`.
- Operator has GitHub Actions `prod` approval rights (ADR-0099).

## Procedure

### Primary path — `rollback.yml` dispatch

1. `gh workflow run rollback.yml --ref main -f env=prod` (empty `target` = the previous ref recorded in state). Add `-f target=v1.2.3` to pin a known-good version, or `-f target=sha-<short>` / a git SHA; the workflow resolves it to its GHCR digest first.
2. Approve the `prod` environment when the apply parks. `rollback.yml` refuses `env=prod` unless the ref is `main` or a `v*` tag on `main` (ADR-0109).
3. The apply job prints `TF_VAR_app_image_ref` / `TF_VAR_app_image_previous_ref` and then waits for the host status. After a rollback the refs are swapped, so running `rollback.yml` again without a target rolls forward to the release you left.

`env=drill` can be dispatched from any ref (the drill is usually torn down; a rollback there only makes sense on an explore drill with `keep=true`).

### Break-glass path

Not a routine path. During a GitHub Actions outage, with explicit user go, follow [`break-glass.md`](break-glass.md) and log the reason and target in `docs/CHANGELOG.md`. The host-side equivalent is: pin the compose `image:` line to the known-good `tag@digest` and `docker compose up -d app`. The agent rewrites the compose file on its next run if the metadata still names another generation, so stop it first (`sudo systemctl stop bp-converge.timer`) and re-enable it once a normal apply has caught up.

## Verification

```sh
# App serves and reports ready.
curl -fsS "https://budget-planner-prod/ready" | jq .

# Host agent applied the rollback generation and runs the target ref.
curl -fsS "https://budget-planner-prod/.well-known/bp-deploy-status.json" | jq .
# Expect: state "ok", running_ref ".../budget-planner:<target tag>@sha256:..."

# Older image tolerated the newer schema (expected after a migrating release).
ssh operator@budget-planner-prod "docker logs budget-planner-app 2>&1 | grep -E 'schema_ahead_of_image|startup_migrations' | tail -2"

# Audit log is intact — rollback does not touch the DB.
ssh operator@budget-planner-prod \
  "sqlite3 /data/budget.db 'SELECT count(*), max(id) FROM audit_log;'"
```

Spot-check the user-facing symptom that triggered the rollback. If it still reproduces on the previous tag, you were rolling back the wrong thing — see Troubleshooting.

## Troubleshooting

- **"rollback: no target given and state records no previous ref"**: only one release has gone through ADR-0111 so far. Dispatch with an explicit `target` (`gh release list` for versions that ran in prod).
- **"rollback: host already runs …"**: the target equals the current ref; nothing to do, or you meant another target.
- **Status reports `state: failed`, `error: cosign_verify`**: the target image's signature does not match the `build.yml` identity. Do not bypass; pick another target and treat it as a supply-chain red flag.
- **Status reports `error: ready_timeout`**: the target image also fails `/ready`. This is a data-shaped incident, not a code regression. Stop. Switch to [`restore.md`](restore.md).
- **Status never reaches the new generation**: check the agent on the host: `ssh operator@budget-planner-prod 'sudo journalctl -u bp-converge.service -n 50 --no-pager'`.

## Rollback (of this rollback)

The refs were swapped, so the release you just left is now the recorded previous ref:

1. `gh workflow run rollback.yml --ref main -f env=prod` (or `-f target=<version you left>`).
2. Approve `prod`.
3. Verify `/ready`, the status file and the symptom you were originally debugging.
