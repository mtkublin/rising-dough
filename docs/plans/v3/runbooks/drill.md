# Drill environment: deploy a branch, TTL, teardown

Policy: ADR-0099 decision 3. The drill is the only place a non-`main` branch runs in the cloud. Prod is never touched by these workflows.

## Deploy a branch to drill

`drill.yml` starts only from `workflow_dispatch` (T-D98): no push or pull_request trigger. Two modes:

- **gate** (default), the PR merge gate: `gh workflow run drill.yml --ref <branch> -f mode=gate`. Applies, runs the tailnet `/ready` smoke, ALWAYS tears down (once apply was attempted) and posts commit status `drill-gate` on the dispatched SHA: `pending` at start, `success` only if apply AND smoke passed, else `failure`. The ref and sha are in the run summary. A teardown failure fails the workflow run but does not change the status; the sweeper (90 min `expires-at` tag) is the backstop.
- **explore**, to browse the drill: `gh workflow run drill.yml --ref <branch> -f mode=explore -f ttl_minutes=90` (`ttl_minutes` 15..480, default 60; `-f keep=false` destroys right after the smoke test; `-f boot_logs=true` for boot diagnostics). Never posts a status.

Pipeline: ci -> build -> terraform apply drill (server and tailnet key always replaced, so cloud-init picks up the new tag) -> smoke (the runner joins the tailnet as `tag:ci` and waits up to 10 min for `https://budget-planner-drill.$TAILNET_DNS_NAME/ready`; a fresh boot takes ~3.5 min). There is no separate deploy step: the fresh VM already runs the built image (ADR-0099 amendment). Runs queue behind other drill work (concurrency group `drill`).

## Tailnet-only (ADR-0101)

The drill has no public DNS record and no public 80/443. Browse it from a device on the tailnet at `https://budget-planner-drill.<tailnet>.ts.net` (certificate from tailscaled). Prerequisites: MagicDNS + HTTPS certificates enabled, ACL `tag:ci -> tag:drill:443` and your device allowed to `tag:drill:443`, `TAILNET_DNS_NAME` set in the drill environments (see `github-settings.md`). SSH stays tailnet-only too. If a stale node of the same name still exists the new node registers as `budget-planner-drill-1` and the certificate name will not match; wait for the old ephemeral node to expire or remove it in the admin console.

## Approval (optional)

A manual dispatch is already a human action, so a required reviewer on the `drill` GitHub environment is optional (T-D96; recommended off for a single-maintainer repo, see `github-settings.md`). If one is configured, a run waiting for approval holds the `drill` concurrency group: approve or cancel it promptly. Teardown, sweeper and plan never wait (`drill-teardown`, `drill-plan`).

## PR gate

Every PR to `main` needs a passing `drill-gate` status on its head SHA (branch protection, `github-settings.md`). Dispatch the gate on the PR branch when the PR is otherwise ready: `gh workflow run drill.yml --ref <pr-branch> -f mode=gate`, and watch the `drill-gate` check on the PR. The status belongs to that exact commit: any new push (new head SHA) has no `drill-gate`, which blocks the merge again until the gate is re-dispatched. This is intended. PR CI is the separate `ci.yml` run (the gate run also runs `ci` and `build` for the dispatched ref).

## TTL and sweeper

The expiry is the server tag `expires-at=<RFC3339 UTC>` (Terraform var `drill_expires_at`). `drill-sweeper.yml` runs every 15 min, lists servers of the drill project via the Scaleway API and destroys the drill when the tag is expired, or when a server has no tag and is older than 8 h. It is a no-op if nothing is up. Re-dispatching `drill.yml` extends the TTL (new apply, new tag).

## Early destroy

`gh workflow run drill-destroy.yml` (any ref). Destroy runs pass the placeholder `image_tag: sha-0000000`; it is only rendered into user-data, which a destroy plan never creates.

## Debugging a boot

Dispatch with `-f boot_logs=true` to set `boot_log_upload` (ADR-0094, T-D86): cloud-init logs, journal and dmesg are uploaded to the drill bucket under `boot-logs/`. Read them with the Scaleway console, or `aws s3 ls s3://<drill bucket>/boot-logs/ --endpoint-url https://s3.pl-waw.scw.cloud` using the drill credentials. The other break-glass vars (`break_glass_*`) are never set by the pipeline; see `break-glass.md`.

## Required in environment `drill`

Secrets: everything `terraform.yml` lists (SCW keys of `ci-drill`, `SCW_DEFAULT_PROJECT_ID` = drill project, Tailscale OAuth, `PROD_REPLICA_RO_*`, ...). Variable: `TAILNET_DNS_NAME` (tailnet MagicDNS suffix). The same secrets and variables live in `drill-teardown` and `drill-plan` (ungated). The sweeper needs `SCW_SECRET_KEY` with read access to instance servers in the drill project.

## Cost

A drill VM costs roughly EUR 4.5/month (well under EUR 0.01/h); the TTL and sweeper bound a forgotten drill to hours, not months.
