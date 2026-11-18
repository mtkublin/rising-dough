# Drill environment: deploy a branch, TTL, teardown

Policy: ADR-0099 decision 3. The drill is the only place a non-`main` branch runs in the cloud. Prod is never touched by these workflows.

## Deploy a branch to drill

`drill.yml` starts only from `workflow_dispatch` (T-D98): no push or pull_request trigger. Two modes:

- **gate** (default), the PR merge gate: `gh workflow run drill.yml --ref <branch> -f mode=gate`. Applies, runs the tailnet `/ready` smoke, ALWAYS tears down (once apply was attempted) and posts commit status `drill-gate` on the dispatched SHA: `pending` at start, `success` only if apply AND smoke passed, else `failure`. The ref and sha are in the run summary. A teardown failure fails the workflow run but does not change the status; the sweeper (90 min `expires-at` tag) is the backstop.
- **explore**, to browse the drill: `gh workflow run drill.yml --ref <branch> -f mode=explore -f ttl_minutes=90` (`ttl_minutes` 15..480, default 60; `-f keep=false` destroys right after the smoke test; `-f boot_logs=true` for boot diagnostics). Never posts a status.

Pipeline: ci -> build -> terraform apply drill (server and tailnet key always replaced, so cloud-init picks up the new tag) -> smoke (the runner joins the tailnet as `tag:ci` and waits up to 10 min for `https://budget-planner-drill-<run id>.$TAILNET_DNS_NAME/ready`; a fresh boot takes ~3.5 min). There is no separate deploy step: the fresh VM already runs the built image (ADR-0099 amendment). Runs queue behind other drill work (concurrency group `drill`).

## Tailnet-only (ADR-0101)

The drill has no public DNS record and no public 80/443. Browse it from a device on the tailnet at `https://budget-planner-drill-<run id>.<tailnet>.ts.net` (certificate from tailscaled). Prerequisites: MagicDNS + HTTPS certificates enabled, ACL `tag:ci -> tag:drill:443` and your device allowed to `tag:drill:443`, `TAILNET_DNS_NAME` set in the drill environments (see `github-settings.md`). SSH stays tailnet-only too. Each run registers its own node name, `budget-planner-drill-<run id>` (ADR-0116, T-D139), so a run no longer collides with an earlier drill. A leftover node that still carries the run's name makes the new node register as `budget-planner-drill-<run id>-1`, and the certificate name will not match; remove the old node in the admin console (or wait for the ephemeral node to expire) first. Every destroy path (`drill.yml` teardown, `drill-destroy.yml`, `drill-sweeper.yml`) ends with a `tailnet-cleanup` job (T-D124) that runs `scripts/tailnet_drill_cleanup.py`: it gets an OAuth token from `TS_CLEANUP_CLIENT_ID` / `TS_CLEANUP_SECRET`, lists the tailnet devices and deletes every device named `budget-planner-drill` or `budget-planner-drill-<n>` (`<n>` is the numeric run id) that carries `tag:drill`. Other tags are never touched; no match is success; a failed delete or missing secrets is a `::warning::` only (the VM is already gone). Operator prerequisite: the `budget-planner-drill-cleanup` OAuth client and its two secrets (`github-settings.md` section 4). Without them, remove the node by hand (Machines > `budget-planner-drill-<run id>` > Remove) before the next dispatch.

## Approval (optional)

A manual dispatch is already a human action, so a required reviewer on the `drill` GitHub environment is optional (T-D96; recommended off for a single-maintainer repo, see `github-settings.md`). If one is configured, a run waiting for approval holds the `drill` concurrency group: approve or cancel it promptly. Teardown, sweeper and plan never wait (`drill-teardown`, `drill-plan`).

## PR gate

Every PR to `main` needs a passing `drill-gate` status on its head SHA (branch protection, `github-settings.md`). Dispatch the gate on the PR branch when the PR is otherwise ready: `gh workflow run drill.yml --ref <pr-branch> -f mode=gate`, and watch the `drill-gate` check on the PR. The status belongs to that exact commit: any new push (new head SHA) has no `drill-gate`, which blocks the merge again until the gate is re-dispatched. This is intended. PR CI is the separate `ci.yml` run (the gate run also runs `ci` and `build` for the dispatched ref).

## TTL and sweeper

The expiry is the server tag `expires-at=<RFC3339 UTC>` (Terraform var `drill_expires_at`). `drill-sweeper.yml` runs every 15 min, lists servers of the drill project via the Scaleway API and destroys the drill when the tag is expired, or when a server has no tag and is older than 8 h. It is a no-op if nothing is up. Re-dispatching `drill.yml` extends the TTL (new apply, new tag).

## Restore drill job layout (T-D133, ADR-0117)

`restore-drill.yml` (monthly, or dispatch) runs: `drill-lock` -> `image` (newest release, `host_release.py resolve-ref`) -> `apply` (`terraform.yml`, env `drill`) -> `restore-drill` (env `drill`, the only environment with `DEPLOY_SSH_PRIVATE_KEY`: join tailnet, wait for SSH, verify operator login, wait for the host agent status `ok`, restore, verify `/ready`, integrity, no extra DB copies; evidence artifact on failure) -> `destroy` (`terraform.yml`, `drill-teardown`, `always()` once apply was attempted) -> `verify-destroy` (state empty), `tailnet-cleanup` (reusable `tailnet-cleanup.yml`) and `report` (opens the `restore-drill` issue when image, apply, restore, destroy or verify-destroy failed or was cancelled; a drill-lock refusal opens none). Results: every run that reached `restore-drill` writes a restore-log entry to its job summary and comments it on the open `restore-log` issue (`restore-log` job, `drill-teardown`, `issues: write`; T-D41). See [`restore-log.md`](restore-log.md).

## Replacement rehearsal (T-D156, ADR-0122 §7)

Run it before any release that replaces the prod VM (T-D143 first), on the commit you will release, and only with operator go. Check that no drill-group run is queued or running first.

```sh
gh workflow run replace-rehearsal.yml --ref main
```

GitHub dispatches only workflows that exist on `main`; a new or changed rehearsal therefore runs after its PR merges.

About 40 minutes on one drill (DEV1-S): refuse an empty replica, seed on Block Storage, replace with `l_ssd` while a writer commits a row per second, then verify on the new host. It tears down and cleans the tailnet in all cases. The run summary shows the seeded generation, the writer's last committed row, the restored rows and the lost-row count (must be 0).

If it fails:
- `check-empty`: the restore guard let an empty replica through or never ran. Do not release.
- `seed` "server_replaced": an in-place change was planned as a replacement, or the reverse in `verify`. The release would wait or roll back wrongly.
- `verify` "tailnet settled": the cleanup did not see the old node offline or could not rename. Prod would warn only; fix before relying on it.
- `verify` "lost committed rows": the shutdown flush does not hold. Implement the ADR-0122 §4 drain fallback before the release.
- `verify` restore report or `--require-restore`: the replaced host did not restore the seeded generation. Do not release.

## Drill lock (T-D138)

Every drill workflow (`drill.yml`, `restore-drill.yml`, `drill-destroy.yml`, `drill-sweeper.yml`) starts with job `drill-lock` (ADR-0115); nothing else runs unless it passes. It fails with an explicit `::error::` when:

- another drill-group run is active (name, run id, URL are printed);
- a drill VM exists in the Scaleway drill project (`budget-planner-drill*`; prints `expires-at` and creation time). Expired but not yet swept: "run drill-destroy.yml first". Not expired: "drill VM ... is up until ... (kept explore drill?); run drill-destroy.yml or wait";
- an online `tag:drill` node exists in the tailnet.

`drill-destroy.yml` and `drill-sweeper.yml` only check for other active runs. Any API error or missing credential fails the lock (fail closed). The lock never destroys anything.

To use a drill while a kept explore drill is up: `gh workflow run drill-destroy.yml`, then dispatch. `force=true` (`drill.yml`, `restore-drill.yml`) skips the VM and tailnet checks and prints a warning; operator only, it can replace and destroy a running explore drill. The check runs inside the `drill` concurrency group, so no other run can create a VM meanwhile. A third dispatch still cancels an older pending run silently (GitHub); dispatch drills one at a time.

## Early destroy

`gh workflow run drill-destroy.yml` (any ref). Destroy runs pass the placeholder `image_tag: sha-0000000`; it is only rendered into user-data, which a destroy plan never creates.

## Debugging a boot

Dispatch with `-f boot_logs=true` to set `boot_log_upload` (ADR-0094, T-D86): cloud-init logs, journal and dmesg are uploaded to the drill bucket under `boot-logs/`. Read them with the Scaleway console, or `aws s3 ls s3://<drill bucket>/boot-logs/ --endpoint-url https://s3.pl-waw.scw.cloud` using the drill credentials. The other break-glass vars (`break_glass_*`) are never set by the pipeline; see `break-glass.md`.

## Required in environment `drill`

Secrets: everything `terraform.yml` lists (SCW keys of `ci-drill`, `SCW_DEFAULT_PROJECT_ID` = drill project, Tailscale OAuth, `PROD_REPLICA_RO_*`, ...). Variable: `TAILNET_DNS_NAME` (tailnet MagicDNS suffix). The same secrets and variables live in `drill-teardown` and `drill-plan` (ungated). The sweeper needs `SCW_SECRET_KEY` with read access to instance servers in the drill project.

## Cost

A drill VM costs roughly EUR 4.5/month (well under EUR 0.01/h); the TTL and sweeper bound a forgotten drill to hours, not months.
