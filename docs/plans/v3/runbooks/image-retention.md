# Runbook: GHCR image retention (T-D126, ADR-0099)

## Context
Every release and drill gate pushes a `sha-...` image, its untagged child manifests (provenance, SBOM) and cosign signature artifacts (`sha256-<digest>.sig`) to `ghcr.io/mtkublin/budget-planner`. `image-retention.yml` prunes them weekly (Monday 03:17 UTC) with `scripts/ghcr_retention.py`.

Keep: newest 20 `sha-*` versions; anything tagged `main` or `v*`; every version younger than 7 days; child manifests of kept images; signatures of kept images. Delete (older than 7 days): untagged versions, orphaned `.sig`/`.att`/`.sbom` artifacts, `sha-*` beyond the newest 20. Unrecognised tags are kept.

Assumption: prod's current and previous images are within the newest 20 `sha-*` (rollback depth 1; ~20 releases/drill gates would have to land between two weekly runs to break it). `main`/`v*` tags also protect the latest release.

## Preconditions
- Package `budget-planner` is linked to the repo with Actions role Write (package settings > Manage Actions access).
- Operator `gh` token has `read:packages` for the read-only check (`gh auth refresh -s read:packages`).

## Procedure
1. Dry run: Actions > image-retention > Run workflow with `dry_run` left true. Read the plan in the step summary (every `DELETE` line has a reason).
2. Optional: `gh api /users/mtkublin/packages/container/budget-planner` for visibility and version count.
3. One manual real run: dispatch with `dry_run=false`; confirm prod still pulls (`deploy.md` smoke) and `cosign verify` of the kept `main` image still works.
4. Enable the schedule: repo Settings > Secrets and variables > Actions > Variables: `IMAGE_RETENTION_ENABLED=true`. Remove it (or set anything else) to return to dry-run.

## Dry-run log
- 2026-11-18, run 44297239247 (`main`, `dry_run=true`): failed before printing a plan. `ghcr_retention.py` `main` -> `fetch_children` got `HTTP Error 404` from `https://ghcr.io/v2/<owner>/budget-planner/manifests/<digest>` for one of the kept versions (the token request itself succeeded). Likely a kept version whose digest is not served as a manifest with the requested `Accept` types, or a digest that was deleted but still listed. Fix: treat 404 as no children (or log the digest), then re-run the dry run. `IMAGE_RETENTION_ENABLED` stays unset.
  - Root cause: the failing digest was a cosign signature artifact (e.g. `sha256:11bb577c02f9…`, tag `sha256-2246e6f5….sig`), a plain OCI image manifest. The `Accept` header listed only index types, and GHCR returns `404 MANIFEST_UNKNOWN` ("Accept header does not support OCI manifests") in that case.
  - Fix: `Accept` now covers OCI index, OCI manifest, Docker manifest list and Docker manifest v2. If a kept digest still returns 404, its children are undetermined; the script prints a warning and deletes no untagged version in that run (tagged versions are classified by tag, so they stay safe). Any other HTTP error aborts before anything is deleted.
- 2026-11-18, run 44299557709 (branch `wi/docs/v3-remaining/RET`, `dry_run=true`): green. 59 versions kept, 0 to delete (all versions are younger than 7 days or protected; the oldest, `sha-075f986` and its signature and children, are kept as newest-20/children). Protected images confirmed kept: `v3.0.1`/`sha-4532791`/`latest` (`sha256:2246e6f5…`), `v3.0.0`/`sha-f41c6a2`, `main`/`sha-89ac3c2` (`sha256:85cb5808…`, prod rollback target), plus their signatures and untagged children. No warnings about undetermined children. Retention is still not enabled.

## Enabled
- 2026-11-18: `IMAGE_RETENTION_ENABLED=true` set by the operator, after the green dry run 44299557709. The first real scheduled run is Monday 2026-11-23 03:17 UTC. Check its step summary: `mode: APPLY`, only untagged or orphaned versions and `sha-*` beyond the newest 20 are deleted, and the next release still deploys.

## Verification
Step summary shows `mode: APPLY` and `deleted <id>` lines; the package version count drops; a new release still builds and deploys.

## Troubleshooting
- 403/404 on listing or delete: package not linked to the repo or Actions access is not Write.
- Plan refuses with "no versions found" / "kept nothing": nothing is deleted by design.

## Rollback
Deleted versions cannot be restored. Rebuild an image from its commit via `build.yml` if needed.
