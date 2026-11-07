# Drill environment: deploy a branch, TTL, teardown

Policy: ADR-0099 decision 3. The drill is the only place a non-`main` branch runs in the cloud. Prod is never touched by these workflows.

## Deploy a branch to drill

- Push a branch named `<name>-deploy`, or
- `gh workflow run drill.yml --ref <branch> -f ttl_minutes=60` (`ttl_minutes` 15..480; `-f keep=false` destroys right after the smoke test).

Pipeline: ci -> build -> terraform apply drill (server and tailnet key always replaced, so cloud-init picks up the new tag) -> smoke (waits up to 10 min for `$DRILL_URL/ready`; a fresh boot takes ~3.5 min). There is no separate deploy step: the fresh VM already runs the built image (ADR-0099 amendment). Runs queue behind other drill work (concurrency group `drill`).

## PR gate

Every PR to `main` runs build -> apply -> smoke -> teardown. Teardown runs even if apply or smoke failed (as long as apply was attempted). PR CI is the separate `ci.yml` run. The server also carries a 120 min `expires-at` tag as a backstop.

## TTL and sweeper

The expiry is the server tag `expires-at=<RFC3339 UTC>` (Terraform var `drill_expires_at`). `drill-sweeper.yml` runs every 15 min, lists servers of the drill project via the Scaleway API and destroys the drill when the tag is expired, or when a server has no tag and is older than 8 h. It is a no-op if nothing is up. Re-dispatching `drill.yml` extends the TTL (new apply, new tag).

## Early destroy

`gh workflow run drill-destroy.yml` (any ref). Destroy runs pass the placeholder `image_tag: sha-0000000`; it is only rendered into user-data, which a destroy plan never creates.

## Debugging a boot

Dispatch with `-f boot_logs=true` to set `boot_log_upload` (ADR-0094, T-D86): cloud-init logs, journal and dmesg are uploaded to the drill bucket under `boot-logs/`. Read them with the Scaleway console, or `aws s3 ls s3://<drill bucket>/boot-logs/ --endpoint-url https://s3.pl-waw.scw.cloud` using the drill credentials. The other break-glass vars (`break_glass_*`) are never set by the pipeline; see `break-glass.md`.

## Required in environment `drill`

Secrets: everything `terraform.yml` lists (SCW keys of `ci-drill`, `SCW_DEFAULT_PROJECT_ID` = drill project, Tailscale OAuth, `PROD_REPLICA_RO_*`, ...). Variable: `DRILL_URL`. The sweeper needs `SCW_SECRET_KEY` with read access to instance servers in the drill project.

## Cost

A drill VM costs roughly EUR 4.5/month (well under EUR 0.01/h); the TTL and sweeper bound a forgotten drill to hours, not months.
