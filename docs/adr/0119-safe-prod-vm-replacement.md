# ADR-0119: A Prod VM Replacement Is Safe Unattended

- **Status**: Proposed
- **Date**: 2026-11-18
- **Amends**: ADR-0071 (restore-before-start), ADR-0094 (Tailscale auth key), ADR-0111 (release wait), ADR-0118 (rollout)
- **Relates to**: ADR-0034, ADR-0099, ADR-0110, ADR-0114
- **Task**: T-D144

## Context

ADR-0118 (T-D143) replaces the prod VM on its next apply. So far prod has only been created once. A review on 2026-11-18 of what a normal prod release does when it replaces `scaleway_instance_server.app` found these gaps (the restore itself was proven by restore-drill run 44330551119, which restored prod generation `2901fbd3873a6696` through `restore-from-prod`):

1. **Tailscale.** `tailscale_tailnet_key.vm` is single-use, expires after 3600 s, and nothing replaces it with the server. The provider does not recreate an invalid single-use key by default. A new VM boots with a used, expired key, never joins the tailnet, and has no SSH (port 22 closed, ADR-0094). The old prod node is not ephemeral and keeps the name `budget-planner-prod`.
2. **Silent empty DB.** The compose `litestream-restore` runs `restore -if-db-not-exists -if-replica-exists`. A wrong bucket, path or region, or an empty bucket, exits 0. Migrations then create an empty DB, the admin bootstrap creates an admin, `/ready` is green, and Litestream replicates the empty DB as a new generation.
3. **No proof the data came back.** The release only waits for the host agent and `/ready`, and an empty DB passes both.
4. **Last writes.** Nothing stops the app before the old VM is destroyed. Whether Scaleway's power-off lets Docker send SIGTERM to Litestream, and whether Litestream ships the last WAL frames then, is unverified. At risk: up to one `sync-interval` (10 s) plus writes during the apply.
5. **Wait budget.** `host_release.py wait` defaults to 600 s. A fresh `STARDUST1-S` boot (package upgrade, Docker install, image pull, restore) has never been timed. A timeout triggers the automatic rollback, which only swaps the image ref.

## Decision

1. **Tailscale key follows the server.** A `terraform_data.vm_identity` holds the inputs that force a server replacement (type, image, zone, root volume type and size). `tailscale_tailnet_key.vm` gets `lifecycle { replace_triggered_by = [terraform_data.vm_identity] }`, so every replacement mints a fresh key. (The key cannot reference the server directly: the server's user_data uses the key.) After a replacement converges, the release job removes offline `budget-planner-prod*` nodes other than the new one, reusing `tailnet-cleanup.yml` with a prod mode. The new node then holds the plain name.
2. **An empty DB is allowed only by explicit choice.** New Terraform variable `allow_empty_db` (bool, default `false`; `true` on the drill, whose bucket starts empty). If `/data/budget.db` is missing, `litestream-restore` first lists the replica's generations. No generation and `allow_empty_db = false` → exit non-zero, so the app never starts. A listing or restore error is always non-zero. A prod first-ever boot (or a deliberate fresh start) needs a reviewed change that sets the variable for one apply.
3. **The host reports what it restored.** `litestream-restore` writes `/data/restore-report.json` (`restored`: true/false/skipped-db-present, `generation`, UTC time). The host agent adds `restore` to `bp-deploy-status.json` (no row counts or user data). When the plan replaces the server, the release job requires `restore.restored == true` before it calls the release good.
4. **Writes stop before the old VM goes.** Docker's stop of `litestream` on host shutdown is the primary path. Its stop grace is raised to 30 s, and the T-D144 drill proof measures it: write a row, destroy the VM through Terraform, restore, and check the row is present. If that proof fails, a `drain` flag in `bp-config` (agent stops `app`, waits one sync, reports `drained`) becomes a first apply before the replacing apply. This exception to ADR-0110's one approval per release applies only to releases that replace the VM.
5. **Longer wait on replacement.** The release job reads the plan JSON. When `scaleway_instance_server.app` is replaced, it waits up to 1800 s instead of 600 s and skips the automatic image rollback (a rollback cannot fix a failed first boot; the operator follows `disaster-recovery.md`).
6. **Operator checks stay in the runbook.** Before approving a replacing release, record prod row counts and max ids (`restore.md`). Afterwards compare them on the new host before closing the release.

## Consequences

- A prod VM replacement (ADR-0118, or any future type or image change) is one approved release. It fails closed instead of coming up empty or unreachable.
- The drill sets `allow_empty_db = true`. Its gate still passes on an empty bucket, and the restore drill keeps using `restore-from-prod`.
- `bp-deploy-status.json` gains a small `restore` object. It is public like the rest of the file, so it carries no counts.
- T-D143 is blocked on T-D144 for prod. The T-D143 drill gate can run first.
- Rejected:
  - Reusable or long-lived Tailscale keys: a leaked key would join any machine as `tag:prod`.
  - Removing `-if-replica-exists`: it breaks the drill and a first-ever boot.
  - Row counts in the public status file.
  - SSH from CI to prod for a drain: ADR-0111 removed that path.
