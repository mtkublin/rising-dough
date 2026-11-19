# ADR-0127: A Prod VM Replacement Is Safe Unattended

- **Status**: Proposed
- **Date**: 2026-11-18
- **Amends**: ADR-0071 (restore-before-start), ADR-0094 (Tailscale auth key), ADR-0111 (release wait), ADR-0118 (rollout)
- **Relates to**: ADR-0034, ADR-0099, ADR-0110, ADR-0114
- **Task**: T-D156

## Context

ADR-0118 (T-D143) replaces the prod VM on its next apply. So far prod has only been created once. A review on 2026-11-18 of what a normal prod release does when it replaces `scaleway_instance_server.app` found these gaps (the restore itself was proven by restore-drill run 44330551119, which restored prod generation `2901fbd3873a6696` through `restore-from-prod`):

1. **Tailscale.** `tailscale_tailnet_key.vm` is single-use, expires after 3600 s, and nothing replaces it with the server. The provider does not recreate an invalid single-use key by default. A new VM boots with a used, expired key, never joins the tailnet, and has no SSH (port 22 closed, ADR-0094). The old prod node is not ephemeral and keeps the name `budget-planner-prod`.
2. **Silent empty DB.** The compose `litestream-restore` runs `restore -if-db-not-exists -if-replica-exists`. A wrong bucket, path or region, or an empty bucket, exits 0. Migrations then create an empty DB, the admin bootstrap creates an admin, `/ready` is green, and Litestream replicates the empty DB as a new generation.
3. **No proof the data came back.** The release only waits for the host agent and `/ready`, and an empty DB passes both.
4. **Last writes.** Nothing stops the app before the old VM is destroyed. Whether Scaleway's power-off lets Docker send SIGTERM to Litestream, and whether Litestream ships the last WAL frames then, is unverified. At risk: up to one `sync-interval` (10 s) plus writes during the apply.
5. **Wait budget.** `host_release.py wait` defaults to 600 s. A fresh `STARDUST1-S` boot (package upgrade, Docker install, image pull, restore) has never been timed. A timeout triggers the automatic rollback, which only swaps the image ref.

## Decision

1. **Tailscale key follows the server.** `local.vm_spec` in `terraform/main.tf` holds every input that forces a server replacement (type, image, zone, root volume type and size), and the compute module takes those inputs only from it. The key's description ends with `vm <first 12 hex of sha256(vm_spec)>`. Tailscale keys cannot be updated in place, so a changed spec replaces the key in the same plan that replaces the server. (The key cannot reference the server: the server's user_data carries the key. `replace_triggered_by` on a new `terraform_data` was rejected because it does not fire when that resource is first created, which is exactly the T-D143 release.) Shipping this changes the key description once, which replaces the unused key in place; the running host does not use it again. After a replacement converges, `release.yml` calls `tailnet-cleanup.yml` with `env: prod`. Prod mode deletes `tag:prod` nodes named `budget-planner-prod[-n]` that are offline (`connectedToControl` false), and never an online one. It then renames the one online node to `budget-planner-prod` if Tailscale gave it a `-1` suffix. It runs in a new environment `prod-tailnet`: no reviewers (the release was already approved), deployment refs limited to `main` and `v*` tags, holding a separate OAuth client `budget-planner-prod-cleanup` (`devices:core` write, `tag:prod` only). The drill client stays `tag:drill` only. Like the drill mode, every problem is a warning: the release is already live, and an operator can remove the node by hand.
2. **An empty DB is allowed only by explicit choice.** New Terraform variable `allow_empty_db` (bool, default `false`; always `true` on the drill, whose bucket starts empty). The restore service runs `litestream-restore.sh` (a managed file, like the ADR-0114 entrypoint) instead of `restore -if-db-not-exists -if-replica-exists`. When `/data/budget.db` is missing, the script lists the replica's generations (a listing error is always fatal). No generation and the flag false → exit non-zero, so app and litestream never start. Otherwise it restores and checks the file is non-empty. A prod first-ever boot (or a deliberate fresh start) needs a reviewed change that sets the variable for one apply.
3. **The host reports what it restored.** The script writes `/data/restore-report.json`: `result` (`restored`, `empty` or `skipped-db-present`), `generation`, UTC time. Later runs (every `compose up`) keep an existing report, so it records how this host's database came to be. The host agent adds it as `restore` to `bp-deploy-status.json` (no row counts or user data). A missing or unreadable report is `null`. When the plan replaces the server, the release job requires `restore.result == "restored"` before it calls the release good. Any other value once the agent reports `ok` fails the job at once.
4. **Writes stop before the old VM goes.** *(Mechanism superseded by the 2026-11-19 amendment below: the rehearsal lost a row, and a drain cannot be a separate apply.)* Docker's stop of `litestream` on host shutdown is the primary path. Its stop grace is already 30 s (`stop_grace_period`, compose), and the T-D156 drill proof measures it: write a row, destroy the VM through Terraform, restore, and check the row is present. If that proof fails, a `drain` flag in `bp-config` (agent stops `app`, waits one sync, reports `drained`) becomes a first apply before the replacing apply. This exception to ADR-0110's one approval per release applies only to releases that replace the VM.
5. **Longer wait on replacement.** After the plan, `terraform.yml` pipes `terraform show -json plan.bin` into `host_release.py replaced`. The script prints only `replaced=true|false`; the plan JSON holds secrets and is never printed or uploaded. It is `true` when `module.compute.scaleway_instance_server.app` has both `delete` and `create` in its actions. Then the job waits up to 1800 s instead of 600 s (job timeout 50 min) and skips the automatic image rollback: a rollback cannot fix a failed first boot, so the operator follows `disaster-recovery.md`. The job exposes `server_replaced` for the cleanup in §1.
6. **Operator checks stay in the runbook.** Before approving a replacing release, record prod row counts and max ids (`restore.md`). Afterwards compare them on the new host before closing the release.

7. **Rehearse the replacement on the drill before the release.** `replace-rehearsal.yml` (dispatch only, `drill` concurrency group, drill lock first) runs the T-D143 transition on one drill and fails on any gap:
   1. **Fail closed.** Apply with `drill_allow_empty_db = false` on the drill's empty bucket. Over tailnet SSH: `litestream-restore` exited non-zero with "refusing to start empty", and there is no `/data/budget.db` and no report.
   2. **Seed.** Re-apply on the same VM (Block Storage root, `drill_root_volume_type = "sbs_volume"`, as prod today) with the flag true. The plan must not replace the server (`server_replaced == false`). The app starts empty (report `empty`). Marker rows are written through the app container, and the job waits until Litestream has shipped them, recording the generation from `/data/.budget.db-litestream/generation`.
   3. **Replace.** Apply with `drill_root_volume_type = "l_ssd"`. That changes `vm_spec`, so a new key and `cloud_init` force a server replacement, exactly as T-D143 does on prod; `server_replaced` must be `true`. While the apply runs, a writer inserts one marker row per second through the app container until the old host goes away, and records the last committed row.
   4. **Verify.** The cleanup removes the offline old node and renames the new one (the drill's certificate needs the plain name). The status must report `restore.result == "restored"` with the seeded generation. Every row the writer saw committed must be present (shutdown flush, §4), and `PRAGMA integrity_check` must be `ok`.
   5. Teardown and the drill tailnet cleanup always run.

   The drill-only Terraform variables `drill_root_volume_type` (default `l_ssd`) and `drill_allow_empty_db` (default `true`) exist only for this. Prod ignores both (`l_ssd`, `allow_empty_db`). The rehearsal does not replace the `drill-gate` status. Gaps it cannot close: the STARDUST1-S boot time and power-off (the drill is DEV1-S), the `tag:prod` cleanup client, and the size of prod's data.

## Consequences

- A prod VM replacement (ADR-0118, or any future type or image change) is one approved release. It fails closed instead of coming up empty or unreachable.
- The drill sets `allow_empty_db = true`. Its gate still passes on an empty bucket, and the restore drill keeps using `restore-from-prod`.
- `bp-deploy-status.json` gains a small `restore` object. It is public like the rest of the file, so it carries no counts.
- T-D143 is blocked on T-D156 for prod, and its release on a green `replace-rehearsal.yml` run on the release commit. GitHub dispatches only workflows present on `main`, so the rehearsal runs after the merge and before the release is cut (merging does not release, ADR-0099).
- Rejected:
  - Reusable or long-lived Tailscale keys: a leaked key would join any machine as `tag:prod`.
  - Removing `-if-replica-exists`: it breaks the drill and a first-ever boot.
  - Row counts in the public status file.
  - SSH from CI to prod for a drain: ADR-0111 removed that path.

## Amendment 2026-11-19: drain before the replacing apply (T-D157)

**Status:** proposed, with the rest of this ADR. Supersedes the mechanism in Decision 4. The goal there (no committed write lost when the old VM goes) stands.

**Why.** The rehearsal from `main` (run 44513330068) proved the restore guard, the detection, the restore of the seeded generation and the tailnet rename. It also lost one committed row: the writer saw row 65 committed, and the new host had rows 1–64. The writer never saw the app stop. Its SSH session died with the host, so the destroy did not give the app and Litestream a clean stop. Decision 4's primary path (Docker stops `litestream` on host shutdown) does not hold.

Decision 4's fallback cannot be built as written. `bp-config` is a key of the server's own `user_data`, so a Terraform apply of the new commit carries the replacement in the same apply. There is no "first apply" of the new code that only drains.

**Decision.**

1. **Trigger: a transient metadata key, set by CI in the same approved job.** After the plan and `Detect VM replacement`, when `replaced == true`, `terraform.yml` sets the `user_data` key `bp-drain` on the *current* server through the Scaleway Instance API (`PATCH /instance/v1/zones/{zone}/servers/{id}/user_data/bp-drain`, `text/plain`, auth `X-Auth-Token`). The value is a request id: the run id plus the attempt. The server id (`<zone>/<uuid>`) comes from the plan: `host_release.py replaced` also prints the prior state's id of the replaced server. It prints only that, never other plan values. A Terraform output would not exist in state before the first release that carries it. The job already holds the env's write credentials, so this needs no second approval (ADR-0110 stays one approval per release). It is not Terraform-declared, but it only ever lives on a server the same job is about to destroy.
2. **Agent: drain wins over converge.** Each run first reads `bp-drain`; a 404 means no drain. When the key is present, the agent:
   - stops only `app` (`docker compose stop app`), so writes end and Caddy keeps serving the status file;
   - requires `litestream` running, waits 30 s (three times `sync-interval`), and requires it running again;
   - writes `/var/lib/budget-planner/drained` (holding the request id);
   - publishes `state: "drained"` with `drain: {request, at}`.

   A repeated run for the same request does nothing more. Any failure publishes `state: "failed"` with a `drain_*` error code.
3. **CI waits, then applies.** `host_release.py wait-drained` polls the status until `state == "drained"` with the same request id, with a 300 s timeout. On success the replacing apply runs from the saved plan. If the drain times out or fails, or the apply fails while the old server still exists, CI deletes `bp-drain` (DELETE, 404 tolerated) and fails the job. Nothing is applied after a failed drain.
4. **Undrain.** With the key gone and the `drained` marker present, the agent skips the converged shortcut. `docker inspect` still reports the image of a stopped container, so without this the drained host would look converged. The agent runs the normal apply (`compose up -d`, `/ready` probe), then removes the marker.
5. **Downtime.** The app is down from the drain to `/ready` on the new host. That is about 1 minute of drain plus the boot and restore (about 4 minutes on the drill, up to the 1800 s wait). That is the price of no lost writes, and only replacing releases pay it.
6. **Proof.** `replace-rehearsal.yml` is unchanged. Its replacing apply goes through `terraform.yml`, so the drill drains first. Its pass conditions stay the same: 0 lost committed rows, and the writer ends with "app gone" (the drain stops the app) rather than a dropped SSH session. T-D143's release needs that green run.

**Rejected.**
- Two Terraform applies, the first from the released tag with `drain = true`. It needs a second approval and a checkout of the old tag in CI, and the first plan has to be proven to touch only `bp-config`.
- A manual drain by the operator. It happens outside the pipeline, against ADR-0099/ADR-0111.
- Relying on a graceful stop during the destroy. The rehearsal measured it, and it loses writes.

## Amendment 2026-11-19 (2): the drain-capable agent ships before the first replacing release (T-D158)

**Status:** proposed, with the rest of this ADR. Adds to the T-D157 amendment; its Decisions 1 to 6 stand.

**Why.** Release v3.0.6 (run 44539030541) was the first replacing prod release. The job detected the replacement, set `bp-drain` on the prod server and waited 300 s, but the status stayed `state: "ok"` and had no `drain` field: prod runs the pre-T-D157 agent, which does not read `bp-drain`. The job failed safely. The undrain step deleted the key, `terraform apply` never ran and the app was never stopped; prod stayed on v3.0.5. The loader fetches `bp-agent` from metadata on every 30 s run, but the new agent only reaches metadata through the apply, and in a replacing release that apply is the replacement itself. The rehearsal could not catch this: the drill host already ran the new agent.

**Decision.**

1. **Release order.** A host must run the drain-capable agent before a release replaces it. The agent ships in place: an in-place apply updates `bp-agent`, and the loader runs the new agent within one timer run.
2. **Capability check before the drain.** `terraform.yml` reads the current status before it sets `bp-drain`. Every drain-capable agent publishes a `drain` field (`null` when not draining). When the field is missing, the job fails at once, before the key is set and before the apply: "host agent cannot drain; release the agent in place first (ADR-0127 amendment 2)". It replaces the 300 s timeout for this case.
3. **T-D143 goes out in two releases.**
   - Release A: prod's root volume type is pinned to `sbs_volume`, the type it runs on now (Block Storage, the provider default before ADR-0118). The plan is an in-place `user_data` update, so the new agent reaches prod. The drill keeps `drill_root_volume_type`. If the plan still shows a replacement, the capability check stops the job before the apply.
   - Release B: prod goes to `l_ssd` (ADR-0118). This replacement drains as in the T-D157 amendment.
4. **Proof.** Release A converges in place and the prod status shows `"drain": null`. Release B: the job logs `drained`, the restore report is `restored`, and the `audit_log` counts recorded on the old host before approval match on the new host.

**Rejected.**
- `terraform apply -target` on `bp-agent` alone. It is not a pipeline action (ADR-0099), and a targeted apply is a partial state change outside the plan the operator reads.
- Draining by hand over SSH. It is outside the pipeline (ADR-0099, ADR-0111), as in the T-D157 amendment.
- Letting a replacement go ahead without a drain when the agent cannot drain. The rehearsal measured that path, and it loses writes.
